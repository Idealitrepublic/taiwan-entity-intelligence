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

MANIFEST = Path(__file__).with_name('asset_issuer_reviews.json')
SOURCE_NAME = '財產申報公司識別覆核 / Asset issuer identity review'
REGISTER_NAME = '申報對象官方登記識別 / Official counterparty register'


def build_review_bundle(manifest, assets, *, politician_id, retrieved_at, registry_snapshots):
    """Only a pinned, manually reviewed set is eligible; no fuzzy search here."""
    politician_id = uuid_string(politician_id)
    retrieved_at = timestamp(retrieved_at)
    rows = manifest['rows']
    if (len(rows) != 12 or len({row['asset_id'] for row in rows}) != 12 or
            manifest['publication_scope'] !=
            'identity Evidence only; no canonical merge, asset FK update or ownership Relationship'):
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


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
