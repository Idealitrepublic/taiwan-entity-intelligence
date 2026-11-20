"""Bounded, evidence-versioned repair of the 45 quarantined roster observations."""
import re
from urllib.parse import urlsplit

from src.entities.models import evidence_from_projection, stable_id, timestamp


def build_plan(review, baseline):
    originals = {row['id']: row for row in baseline['records']}
    rows = review['records']
    if len(originals) != 45 or len(rows) != 45 or {r['entity_id'] for r in rows} != set(originals):
        raise ValueError('Review must cover exactly the original 45 distinct entities')
    if len({r['entity_id'] for r in rows}) != 45:
        raise ValueError('Duplicate reviewed entity')
    plan = []
    for row in rows:
        old = originals[row['entity_id']]
        if row['old_name'] != old['display_name'] or row['original_evidence_id'] != old['evidence_id']:
            raise ValueError('Original identity or evidence changed')
        if row['source'] != old['source'] or row['source_id'] != old['source_id']:
            raise ValueError('Source identity changed')
        if row['result'] == 'PENDING':
            continue
        if row['result'] != 'CONFIRMED':
            raise ValueError('Unsupported review result')
        name, proof = row['corrected_name'], row['proof']
        # Only restore missing glyphs, never alter the surrounding name or merge entities.
        if not re.fullmatch(re.escape(row['old_name']).replace(r'\?', '.+?'), name):
            raise ValueError('Correction changes characters beyond the missing glyph')
        if re.search(r'[?\ufffd]', name) or len(name) > 500:
            raise ValueError('Unresolved name')
        url = urlsplit(proof['source_url'])
        if (url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.gov.tw')
                or url.username or url.password):
            raise ValueError('An official government source is required')
        if proof.get('name_found') is not True or proof.get('anchor_found') is not True:
            raise ValueError('Name and source-context verification required')
        if proof.get('file_sha256') and not re.fullmatch('[a-f0-9]{64}', proof['file_sha256']):
            raise ValueError('Invalid original-file digest')
        when = timestamp(proof['retrieved_at'])
        status = row['publication_status']
        if status not in ('published', 'draft') or (row.get('hold') and status != 'draft'):
            raise ValueError('Historical hold must remain private')
        locator = {'reviewed_entity_id': row['entity_id'], 'original_evidence_id': old['evidence_id'],
                   'original_name': row['old_name'], 'corrected_name': name,
                   'original_source_locator': row['original_source_locator'], 'verification': proof,
                   'review_note': row['note'], 'identity_scope': 'SOURCE_SCOPED; no cross-roster merge'}
        evidence = evidence_from_projection(
            source_name='官方團體名稱逐筆覆核 / Official civil name review',
            source_record_id=row['entity_id'], source_class='Official Registry',
            source_url=proof['source_url'], source_locator=locator,
            title='官方名稱覆核：' + name,
            summary=row['note'] + ' 本證據僅核對名稱，不認證現行營運或跨來源同一身分。',
            observed_at=when, retrieved_at=when, publication_status=status).to_dict()
        plan.append({'entity_id': row['entity_id'], 'old_name': row['old_name'], 'name': name,
                     'source': row['source'], 'source_id': row['source_id'],
                     'original_evidence_id': old['evidence_id'], 'publication_status': status,
                     'evidence': evidence,
                     'entity_source_id': stable_id('entity-source', 'civil-name-review', evidence['id'])})
    return plan
