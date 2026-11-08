#!/usr/bin/env python3
"""Read-only, bounded identity/asset/judicial acceptance against Development.

No source retry, identity merge or publication is performed. Output contains
public fact locators and aggregate integrity counts, never connection values.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import development_environment  # noqa: E402
from scripts.ops_restore_drill import query  # noqa: E402
from scripts.sync_judicial_window import inspect_checkpoint  # noqa: E402
from scripts import sync_public_sources as sync  # noqa: E402

SQL = """
SELECT jsonb_build_object(
 'published_entities',(SELECT count(*) FROM public.entities WHERE publication_status='published'),
 'published_relationships',(SELECT count(*) FROM public.relationships WHERE status='published'),
 'published_evidence',(SELECT count(*) FROM public.evidence_records WHERE publication_status='published' AND status='active'),
 'same_names',(SELECT coalesce(jsonb_agg(t),'[]') FROM (
   SELECT canonical_name,count(*) entities,count(distinct entity_type) types
   FROM public.entities WHERE publication_status='published'
   AND entity_type IN ('Company','Person','Politician','GovernmentOfficial')
   GROUP BY canonical_name HAVING count(*)>1) t),
 'identifier_conflicts',(SELECT count(*) FROM (
   SELECT namespace,value FROM public.entity_identifiers WHERE confidence='EXACT'
   GROUP BY namespace,value HAVING count(distinct entity_id)>1) t),
 'resolution_candidates',(SELECT count(*) FROM public.resolution_candidates),
 'unsafe_accepted_candidates',(SELECT count(*) FROM public.resolution_candidates
   WHERE status='accepted' AND confidence NOT IN ('EXACT','HIGH')),
 'broken_published_relationships',(SELECT count(*) FROM public.relationships r
   LEFT JOIN public.entities s ON s.id=r.source_entity_id
   LEFT JOIN public.entities t ON t.id=r.target_entity_id
   LEFT JOIN public.evidence_records e ON e.id=r.primary_evidence_id
   WHERE r.status='published' AND (s.publication_status IS DISTINCT FROM 'published'
    OR t.publication_status IS DISTINCT FROM 'published' OR e.publication_status IS DISTINCT FROM 'published'
    OR e.status IS DISTINCT FROM 'active' OR e.source_record_id IS NULL
    OR e.source_url IS NULL OR e.retrieved_at IS NULL)),
 'broken_published_assets',(SELECT count(*) FROM public.asset_declarations a
   LEFT JOIN public.entities p ON p.id=a.politician_id
   LEFT JOIN public.evidence_records e ON e.id=a.primary_evidence_id
   LEFT JOIN public.relationships r ON r.id=a.relationship_id
   WHERE a.publication_status='published' AND
   (p.publication_status IS DISTINCT FROM 'published' OR p.entity_type IS DISTINCT FROM 'Politician'
    OR e.publication_status IS DISTINCT FROM 'published' OR e.status IS DISTINCT FROM 'active'
    OR e.source_url IS NULL OR e.retrieved_at IS NULL
    OR (a.relationship_id IS NOT NULL AND (a.company_entity_id IS NULL OR r.status IS DISTINCT FROM 'published')))),
 'assets',(SELECT coalesce(jsonb_agg(t),'[]') FROM (
   SELECT a.id,a.asset_type,a.company_name,a.company_entity_id,a.relationship_id,
   a.declaration_year,a.primary_evidence_id,e.source_url,e.source_locator->>'pdf_sha256' pdf_sha256,
   e.source_locator->>'uniform_number' uniform_number,
   e.source_locator->>'company_match_method' company_match_method
   FROM public.asset_declarations a JOIN public.evidence_records e ON e.id=a.primary_evidence_id
   WHERE a.publication_status='published' ORDER BY a.id) t),
 'asset_link_identifier_mismatches',(SELECT count(*) FROM public.asset_declarations a
   JOIN public.evidence_records e ON e.id=a.primary_evidence_id
   WHERE a.publication_status='published' AND a.company_entity_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM public.entity_identifiers i WHERE i.entity_id=a.company_entity_id
    AND i.namespace='tw:uniform_number' AND i.confidence='EXACT'
    AND i.value=e.source_locator->>'uniform_number'))
);
"""


def summarize(database, checkpoint, *, snapshot_hashes):
    failures = [key for key in ('identifier_conflicts', 'unsafe_accepted_candidates',
        'broken_published_relationships', 'broken_published_assets',
        'asset_link_identifier_mismatches') if database.get(key) != 0]
    assets = database['assets']
    named = [row for row in assets if row.get('company_name')]
    unresolved = [row for row in named if not row.get('company_entity_id')]
    if checkpoint['pending_jids'] or checkpoint['completed_batches'] != checkpoint['total_batches']:
        failures.append('judicial_ingestion_incomplete')
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'project': 'tei-development', 'read_only': True,
        'integrity': 'FAIL' if failures else 'PASS', 'failures': failures,
        'task_completion': 'FAIL' if failures else
                           ('PARTIAL' if unresolved or checkpoint['upstream_unavailable_jids'] else 'PASS'),
        'database': database,
        'asset_summary': {'published': len(assets), 'company_named': len(named),
            'exact_linked': sum(bool(row.get('company_entity_id')) for row in named),
            'unresolved': len(unresolved),
            'unresolved_by_type': dict(Counter(row['asset_type'] for row in unresolved)),
            'note': 'Insurance is a contract, not issuer equity ownership. Names alone cannot create ownership edges.'},
        'judicial': checkpoint,
        'snapshot_sha256': snapshot_hashes,
        'scope': 'Published Development integrity and the saved JList window; not national identity precision/recall or historical judicial coverage.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = (sync.STATE, sync.JUDICIAL_SNAPSHOT, sync.EVIDENCE)
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    checkpoint = inspect_checkpoint()
    database = query(development_environment(), SQL)
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    if before != after:
        raise RuntimeError('Source changed during acceptance; repeat under a stable snapshot')
    result = summarize(database, checkpoint, snapshot_hashes=after)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('project', 'integrity', 'task_completion', 'failures')}))
    return 1 if result['integrity'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
