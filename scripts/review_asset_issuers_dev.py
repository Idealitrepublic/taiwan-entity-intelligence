#!/usr/bin/env python3
"""Save twelve reviewed counterparty identifications to Development Evidence.

No asset/Company FK, financial fact, Entity or Relationship is modified. A
fresh encrypted Development backup and pinned official originals gate writes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import development_environment, capacity_guard_sql  # noqa: E402
from scripts.ops_backup import DEV_REF, sha256  # noqa: E402
from scripts.ops_restore_drill import query  # noqa: E402
from src.asset_issuer_review import MANIFEST, build_review_bundle, manifest_digest  # noqa: E402
from src.entities.models import stable_id, uuid_string  # noqa: E402


def load_registry_snapshots(folder):
    if folder.resolve().is_relative_to(ROOT) or folder.stat().st_mode & 0o077:
        raise ValueError('Use an owner-only source directory outside Git')
    result = {}
    for item in json.loads((folder / 'manifest.json').read_text()):
        if not item['file'].startswith('moea-'):
            continue
        if Path(item['file']).name != item['file']:
            raise ValueError('Invalid source filename')
        raw = (folder / item['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Official registry snapshot hash changed')
        rows = json.loads(raw)
        if len(rows) != 1:
            raise ValueError('Official identifier is not unique')
        row = rows[0]
        uniform = str(row['Business_Accounting_NO'])
        if uniform in result:
            raise ValueError('Duplicate registry identifier snapshot')
        result[uniform] = {'row': row, 'sha256': item['sha256'], 'source_url': item['source_url']}
    return result


def check_backup(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    created = datetime.fromisoformat(manifest['created_at'])
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if (manifest.get('project_ref') != DEV_REF or not manifest.get('archive_verified') or
            not 0 <= age < 86400):
        raise ValueError('A verified Development encrypted backup less than 24 hours old is required')
    for name, digest in manifest['encrypted_files'].items():
        if Path(name).name != name or sha256(directory / name) != digest:
            raise ValueError('Encrypted backup hash mismatch')


def asset_query():
    return """SELECT jsonb_build_object(
      'published_assets',(SELECT count(*) FROM public.asset_declarations WHERE publication_status='published'),
      'relationships',(SELECT count(*) FROM public.relationships WHERE status='published'),
      'rows',(SELECT jsonb_agg(t) FROM (
       SELECT a.*,e.source_url,e.source_locator->>'pdf_sha256' pdf_sha256
       FROM public.asset_declarations a JOIN public.evidence_records e ON e.id=a.primary_evidence_id
       WHERE a.publication_status='published' AND e.publication_status='published' AND e.status='active'
       AND a.company_name IS NOT NULL ORDER BY a.id) t));"""


def publication_sql(bundle, assets):
    payload = json.dumps(bundle, ensure_ascii=False).replace("'", "''")
    commands = ["BEGIN; SET LOCAL standard_conforming_strings=on; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='45s';",
                capacity_guard_sql()]
    # Do not publish a review against a declaration withdrawn/changed in the
    # interval after the read-only preparation. Only lock the twelve targets.
    for item in bundle['evidence']:
        asset_id = item['source_locator'].get('asset_declaration_id')
        if not asset_id:
            continue
        asset = assets[asset_id]
        commands.append("DO $$BEGIN IF NOT EXISTS(SELECT 1 FROM public.asset_declarations WHERE "
                        f"id='{uuid_string(asset_id)}' AND primary_evidence_id='{uuid_string(asset['primary_evidence_id'])}' "
                        f"AND politician_id='{uuid_string(asset['politician_id'])}' "
                        "AND publication_status='published' FOR SHARE) THEN "
                        "RAISE EXCEPTION 'Declaration changed during review'; END IF; END$$;")
    commands.extend(["SET LOCAL ROLE service_role;", f"SELECT public.tei_ingest_bundle('{payload}'::jsonb);"])
    for item in bundle['evidence']:
        commands.append("UPDATE public.evidence_records SET publication_status='published' "
                        f"WHERE id='{uuid_string(item['id'])}' AND publication_status='draft' AND status='active';")
    ids = ','.join("'" + uuid_string(item['id']) + "'" for item in bundle['evidence'])
    commands.append("DO $$BEGIN IF (SELECT count(*) FROM public.evidence_records WHERE "
                    f"id IN ({ids}) AND publication_status='published' AND status='active') <> {len(bundle['evidence'])} "
                    "THEN RAISE EXCEPTION 'Review Evidence must be active; withdrawn records cannot be resurrected'; END IF; END$$;")
    commands.extend([capacity_guard_sql(), 'SET CONSTRAINTS ALL IMMEDIATE; COMMIT;'])
    return '\n'.join(commands)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot_directory', type=Path)
    parser.add_argument('--filing-pdf', type=Path, required=True)
    parser.add_argument('--apply-dev', action='store_true')
    parser.add_argument('--backup-directory', type=Path)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    if args.filing_pdf.resolve().is_relative_to(ROOT) or sha256(args.filing_pdf) != manifest['filing_sha256']:
        parser.error('Pinned official filing hash mismatch; original required outside Git')
    snapshots = load_registry_snapshots(args.snapshot_directory)
    env = development_environment()
    before = query(env, asset_query())
    assets = {row['id']: row for row in before['rows']}
    politician_id = stable_id('entity', 'tw:legislative_yuan:legislator_number', '00082')
    now = datetime.now(timezone.utc).isoformat()
    bundle = build_review_bundle(manifest, assets, politician_id=politician_id,
                                 retrieved_at=now, registry_snapshots=snapshots)
    if args.apply_dev:
        if not args.backup_directory:
            parser.error('--apply-dev requires --backup-directory')
        check_backup(args.backup_directory)
        result = subprocess.run(['psql', '-Xq', '-v', 'ON_ERROR_STOP=1'], env=env,
                                input=publication_sql(bundle, assets), text=True, capture_output=True, timeout=90)
        if result.returncode:
            raise RuntimeError('Development identity Evidence publication rolled back; connection details suppressed')
    after = query(env, asset_query())
    if after != before:
        raise RuntimeError('Asset facts or Relationship counts changed; investigate before declaring acceptance')
    receipt = {'project': 'tei-development', 'applied': args.apply_dev,
               'manifest_sha256': manifest_digest(manifest), 'reviewed_rows': 12,
               'distinct_registered_counterparties': 9, 'evidence_records': len(bundle['evidence']),
               'evidence_ids': [row['id'] for row in bundle['evidence']],
               'company_entities_created': 0, 'asset_fk_updates': 0, 'ownership_edges_created': 0,
               'before_after_asset_rows': before['published_assets'],
               'before_after_relationships': before['relationships'],
               'scope': 'Counterparty registration identified; original holding link is NOT approved.'}
    (args.snapshot_directory / 'review_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt | {'evidence_ids': 'retained in private receipt'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
