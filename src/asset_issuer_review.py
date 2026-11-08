"""Row-scoped official issuer/provider identification, separate from holdings.

The reviewed manifest does not supply identifiers missing from a declaration.
It records independently checked registry identities as additional Evidence;
it cannot create Companies, ownership Relationships, or change declaration FKs.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from src.entities.models import evidence_from_projection, timestamp, uuid_string
from src.entities.models import Entity, stable_id

MANIFEST = Path(__file__).with_name('asset_issuer_reviews.json')
SOURCE_NAME = '財產申報公司識別覆核 / Asset issuer identity review'
REGISTER_NAME = '申報對象官方登記識別 / Official counterparty register'
APPROVAL_NAME = '財產申報公司識別核准 / Asset issuer resolution approval'
IDENTITY_ONLY_SCOPE = 'identity Evidence only; no canonical merge, asset FK update or ownership Relationship'
APPROVED_SCOPE = 'row-scoped official issuer identity; STOCK rows link to issuer and publish ASSET_OWNERSHIP; INSURANCE rows link only to provider'


def build_review_bundle(manifest, assets, *, politician_id, retrieved_at, registry_snapshots):
    """Only a pinned, manually reviewed set is eligible; no fuzzy search here."""
    politician_id = uuid_string(politician_id)
    retrieved_at = timestamp(retrieved_at)
    rows = manifest['rows']
    if (len(rows) != 12 or len({row['asset_id'] for row in rows}) != 12 or
            manifest['publication_scope'] not in (IDENTITY_ONLY_SCOPE, APPROVED_SCOPE)):
        raise ValueError('Expected the twelve reviewed declarations and identity-only scope')
    issuers = {item['source_label']: item for item in manifest['issuers']}
    if (len(manifest['issuers']) != 9 or len(issuers) != 9 or
            len({(i['namespace'], i['value']) for i in issuers.values()}) != 9):
        raise ValueError('Ambiguous counterparty identifier')
    bundle = {key: [] for key in ('entities', 'identifiers', 'evidence', 'entity_evidence',
                                 'relationships', 'relationship_evidence', 'legacy_map')}
    registers = {}
    for label, issuer in issuers.items():
        parsed = urlsplit(issuer['source_url'])
        host = parsed.hostname
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('Official registry URL must be credential-free HTTPS')
        namespace, value = issuer['namespace'], issuer['value']
        if namespace == 'tw:uniform_number':
            if (not re.fullmatch(r'[0-9]{8}', value) or issuer['jurisdiction'] != 'tw' or
                    host != 'findbiz.nat.gov.tw' or parsed.path != f'/fts/company/{value}'):
                raise ValueError('Taiwan registry identity mismatch')
            snapshot = registry_snapshots.get(value)
            if (not snapshot or snapshot['row'].get('Business_Accounting_NO') != value or
                    snapshot['row'].get('Company_Name') != issuer['official_name'] or
                    not re.fullmatch(r'[a-f0-9]{64}', snapshot['sha256'])):
                raise ValueError('Official MOEA snapshot/name/identifier mismatch')
            access = {'download_sha256': snapshot['sha256'], 'download_source_url': snapshot['source_url']}
            if urlsplit(snapshot['source_url']).hostname != 'data.gcis.nat.gov.tw':
                raise ValueError('MOEA snapshot must retain its official download URL')
        elif namespace == 'us:sec:cik':
            if (not re.fullmatch(r'[0-9]{10}', value) or value == '0' * 10 or
                    issuer['jurisdiction'] != 'us' or host != 'www.sec.gov' or
                    f'/edgar/data/{int(value)}/' not in urlsplit(issuer['source_url']).path):
                raise ValueError('SEC issuer identity mismatch')
            # Direct SEC bulk endpoints returned 403. Never pretend a web-read
            # identity extract is a downloaded, hashed official JSON snapshot.
            access = {'direct_bulk_api_status': 403,
                      'source_access': 'official_page_identity_fields_via_web',
                      'raw_download_sha256': None}
        else:
            raise ValueError('Unreviewed identifier namespace')
        register = evidence_from_projection(
            source_name=REGISTER_NAME, source_record_id=f'{namespace}:{value}',
            source_class='Official Registry', source_url=issuer['source_url'],
            source_locator={'identifier_namespace': namespace, 'identifier_value': value,
                            'official_name': issuer['official_name'], 'jurisdiction': issuer['jurisdiction'],
                            'source_access': issuer['source_access'], **access},
            title=f"官方公司識別 / Official issuer identity：{issuer['official_name']}",
            summary=f'{namespace} {value}；僅識別登記法人，不證明申報人持股、股別或目前持有狀態。',
            observed_at=retrieved_at, retrieved_at=retrieved_at)
        registers[label] = register
        bundle['evidence'].append(register.to_dict())
        bundle['entity_evidence'].append({'entity_id': politician_id, 'evidence_id': register.id,
                                         'fact_type': 'asset_counterparty_register_context'})

    for row in rows:
        asset = assets.get(row['asset_id'])
        if not asset or (asset['politician_id'] != politician_id or asset['publication_status'] != 'published' or
                asset['asset_type'] != row['asset_type'] or asset['company_name'] != row['company_name'] or
                asset['primary_evidence_id'] != row['declaration_evidence_id'] or
                asset['pdf_sha256'] != manifest['filing_sha256']):
            raise ValueError('Declaration row changed; manual review required')
        issuer = issuers[row['company_name']]
        expected_role = 'insurance_provider' if row['asset_type'] == 'INSURANCE' else 'stock_issuer'
        if issuer['role'] != expected_role or row['asset_type'] not in ('INSURANCE', 'STOCK'):
            raise ValueError('Insurance and equity issuer roles must remain distinct')
        if row['company_name'] != issuer['official_name'] and not issuer.get('alias_source_url') and issuer['jurisdiction'] == 'tw':
            raise ValueError('Taiwan shorthand needs an independent official alias source')
        if issuer.get('alias_source_url') and urlsplit(issuer['alias_source_url']).hostname not in (
                'www.twse.com.tw', 'wwwc.twse.com.tw', 'investoredu.twse.com.tw'):
            raise ValueError('Shorthand alias must be backed by the official stock exchange')
        register = registers[row['company_name']]
        proof = evidence_from_projection(
            source_name=SOURCE_NAME, source_record_id=f"asset:{row['asset_id']}:issuer-review",
            source_class='Derived Data', source_url=asset['source_url'],
            source_locator={'asset_declaration_id': row['asset_id'],
                'declaration_evidence_id': asset['primary_evidence_id'],
                'declaration_pdf_sha256': manifest['filing_sha256'],
                'register_evidence_id': register.id, 'registry_source_url': issuer['source_url'],
                'official_name': issuer['official_name'], 'source_company_name': row['company_name'],
                'identifier_namespace': issuer['namespace'], 'identifier_value': issuer['value'],
                'role': expected_role, 'matching_method': 'manual_row_scoped_official_registry_review',
                'identity_confidence': 'HIGH', 'identifier_present_in_declaration': False,
                'security_class': None, 'ownership_relationship_published': False,
                'alias_source_url': issuer.get('alias_source_url'),
                'reviewed_on': manifest['reviewed_on'],
                'scope': 'counterparty registration identity only; original holding link remains unresolved'},
            title=f"申報對象識別 / Counterparty identity：{asset['company_name']}",
            summary=(f"{asset['company_name']} → {issuer['official_name']}；{issuer['namespace']} {issuer['value']}；"
                     + ('角色為保險提供者，不是公司持股。' if expected_role == 'insurance_provider' else
                        '股票發行人身分覆核；原件未列識別碼，不推定股別或目前持有狀態。')
                     + '原申報與金額不變，未新增正式持股關係。'),
            observed_at=retrieved_at, retrieved_at=retrieved_at)
        bundle['evidence'].append(proof.to_dict())
        bundle['entity_evidence'].append({'entity_id': politician_id, 'evidence_id': proof.id,
                                         'fact_type': 'asset_counterparty_identity_review'})
    return bundle


def build_approved_link_bundle(manifest, assets, *, politician_id, retrieved_at,
                               registry_snapshots, existing_companies):
    """Build evidence-backed issuer Entities and row-scoped links for the 12 reviewed rows.

    STOCK produces a HIGH ASSET_OWNERSHIP edge based on the declaration row plus
    its reviewed issuer identity. INSURANCE links only to the identified provider.
    The declaration Evidence and every reported amount/quantity remain unchanged.
    """
    if manifest.get('publication_scope') != APPROVED_SCOPE:
        raise ValueError('The manifest must explicitly authorize this bounded link review')
    base = build_review_bundle(manifest, assets, politician_id=politician_id,
                               retrieved_at=retrieved_at,
                               registry_snapshots=registry_snapshots)
    bundle = base
    issuers = {item['source_label']: item for item in manifest['issuers']}
    company_by_issuer = {}
    for label, issuer in issuers.items():
        key = (issuer['namespace'], issuer['value'])
        existing = existing_companies.get(key)
        if existing:
            if (existing.get('entity_type') != 'Company' or
                    existing.get('canonical_name') != issuer['official_name'] or
                    existing.get('publication_status') != 'published'):
                raise ValueError('Existing exact identifier maps to a different or unpublished Company')
            company_id = uuid_string(existing['id'])
        else:
            company_id = stable_id('entity', issuer['namespace'], issuer['value'])
            source = 'MOEA/GCI Company Registry' if issuer['jurisdiction'] == 'tw' else 'US SEC EDGAR'
            source_id = f"{issuer['namespace']}:{issuer['value']}"
            entity = Entity(company_id, 'Company', issuer['official_name'],
                            issuer['official_name'], source, source_id,
                            'EXACT', 'published')
            bundle['entities'].append(entity.to_dict())
            bundle['identifiers'].append({'entity_id': company_id,
                'namespace': issuer['namespace'], 'value': issuer['value']})
        company_by_issuer[label] = company_id

    prior_reviews = {item['source_locator']['asset_declaration_id']: item
                     for item in base['evidence']
                     if item['source_name'] == SOURCE_NAME}
    registries = {item['source_record_id']: item for item in base['evidence']
                  if item['source_name'] == REGISTER_NAME}
    for issuer in issuers.values():
        register = registries[f"{issuer['namespace']}:{issuer['value']}"]
        company_id = company_by_issuer[issuer['source_label']]
        bundle['entity_evidence'].append({'entity_id': company_id,
            'evidence_id': register['id'], 'fact_type': 'company_registration_identity'})

    for row in manifest['rows']:
        asset = assets[row['asset_id']]
        issuer = issuers[row['company_name']]
        company_id = company_by_issuer[row['company_name']]
        register = registries[f"{issuer['namespace']}:{issuer['value']}"]
        prior = prior_reviews[row['asset_id']]
        role = 'insurance_provider' if row['asset_type'] == 'INSURANCE' else 'stock_issuer'
        approval = evidence_from_projection(
            source_name=APPROVAL_NAME,
            source_record_id=f"asset:{row['asset_id']}:issuer-approval:v1",
            source_class='Derived Data', source_url=asset['source_url'],
            source_locator={
                'asset_declaration_id': row['asset_id'],
                'declaration_evidence_id': asset['primary_evidence_id'],
                'company_entity_id': company_id,
                'source_company_name': row['company_name'],
                'official_name': issuer['official_name'],
                'identifier_namespace': issuer['namespace'],
                'identifier_value': issuer['value'],
                'register_evidence_id': register['id'],
                'prior_review_evidence_id': prior['id'],
                'role': role,
                'matching_method': 'manual_row_scoped_official_registry_review',
                'decision': 'approved',
                'identity_confidence': 'HIGH',
                'security_class': None,
                'current_holding_reverified': False,
                'reviewed_on': manifest['reviewed_on'],
                'scope': ('Declared issuer identity only; security class is not identified; '
                          'this does not re-verify the current holding.' if role == 'stock_issuer'
                          else 'Insurance provider identity only; no ownership Relationship.')},
            title=f"財產申報對象核准識別 / Approved declaration counterparty：{row['company_name']}",
            summary=(f"{row['asset_type']} 申報列以逐列覆核連至 {issuer['official_name']}，"
                     f"官方識別碼 {issuer['namespace']} {issuer['value']}。"
                     + ('依申報股票名稱、股數與官方發行人身分建立 HIGH 信心發行人層級持股關係；'
                        '不推定股別，也不代表目前持有狀態經重新查證。'
                        if role == 'stock_issuer' else
                        '僅標示保險提供者，不建立持股或事業投資關係。')),
            observed_at=asset['observed_at'], retrieved_at=retrieved_at)
        bundle['evidence'].append(approval.to_dict())
        bundle['entity_evidence'].extend([
            {'entity_id': company_id, 'evidence_id': approval.id,
             'fact_type': 'asset_counterparty_identity_approval'},
            {'entity_id': politician_id, 'evidence_id': approval.id,
             'fact_type': 'asset_counterparty_identity_approval'}])
        bundle.setdefault('asset_links', []).append({
            'asset_id': row['asset_id'], 'company_entity_id': company_id,
            'company_identity_evidence_id': approval.id,
            'relationship_id': None})

        if role == 'insurance_provider':
            if row['asset_type'] != 'INSURANCE':
                raise ValueError('Only declared insurance rows may identify insurance providers')
            continue
        if row['asset_type'] != 'STOCK':
            raise ValueError('Only reviewed STOCK rows are approved for ownership publication')
        declaration_date = asset['source_locator'].get('declaration_date')
        if not declaration_date:
            raise ValueError('The original declaration does not provide a relationship date')
        relationship_id = stable_id('relationship', 'asset_declaration', row['asset_id'])
        bundle['relationships'].append({
            'id': relationship_id, 'source_entity_id': politician_id,
            'target_entity_id': company_id, 'relationship_type': 'ASSET_OWNERSHIP',
            'primary_evidence_id': asset['primary_evidence_id'],
            'start_date': declaration_date, 'end_date': None, 'date_precision': 'day',
            'observed_at': asset['observed_at'], 'amount': asset.get('amount'),
            'currency': asset.get('currency'), 'percentage': None,
            'quantity': asset.get('quantity'), 'quantity_unit': asset.get('quantity_unit'),
            'source_role': 'STOCK', 'confidence': 'HIGH', 'status': 'published'})
        bundle['relationship_evidence'].extend([
            {'relationship_id': relationship_id, 'evidence_id': asset['primary_evidence_id'],
             'support_type': 'supports'},
            {'relationship_id': relationship_id, 'evidence_id': approval.id,
             'support_type': 'supports'},
            {'relationship_id': relationship_id, 'evidence_id': register['id'],
             'support_type': 'context'}])
        # Keep the first review immutable and attach a new, explicitly scoped
        # approval version that the database can independently validate.
        bundle['asset_links'][-1]['relationship_id'] = relationship_id
    if len(bundle['asset_links']) != 12 or len(bundle['relationships']) != 6:
        raise ValueError('Expected exactly twelve reviewed links and six STOCK relationships')
    return bundle


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
