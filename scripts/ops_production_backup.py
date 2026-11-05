#!/usr/bin/env python3
"""Explicitly authorized, read-only encrypted backup of the original Production DB.

Connection values are read only from the child environment/ignored .env.local.
No Development evidence, plaintext dump, connection string or password is saved.
This command never restores, migrates, resets or deploys anything.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ops_backup import (  # noqa: E402
    PROD_REF, encrypt_stream, executable, sha256, validate_destination, verify_archive,
)


def production_environment(value):
    """Reject every target except the original Production project, fail closed."""
    parsed = urlsplit(value)
    host, user = (parsed.hostname or '').lower(), unquote(parsed.username or '')
    direct = host == f'db.{PROD_REF}.supabase.co' and user == 'postgres'
    pooler = host.endswith('.pooler.supabase.com') and user == f'postgres.{PROD_REF}'
    if (parsed.scheme not in ('postgres', 'postgresql') or not (direct or pooler)
            or not parsed.password or parsed.path != '/postgres'
            or parsed.port not in (None, 5432) or parsed.fragment):
        raise ValueError('Only the original Production direct/session connection is accepted')
    base = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    return {**base, 'PGHOST': host, 'PGPORT': str(parsed.port or 5432),
            'PGUSER': user, 'PGPASSWORD': unquote(parsed.password), 'PGDATABASE': 'postgres',
            'PGSSLMODE': 'require', 'PGCONNECT_TIMEOUT': '15',
            'PGOPTIONS': '-c default_transaction_read_only=on',
            'PGAPPNAME': 'tei-authorized-readonly-backup'}


def backup(destination, url, recipient, identity):
    env = production_environment(url)
    destination = validate_destination(destination)
    if not recipient.startswith('age1') or len(recipient) < 30:
        raise ValueError('An age public recipient is required')
    if not identity.is_file() or identity.stat().st_mode & 0o077:
        raise ValueError('An existing owner-only age identity is required')
    # Verify the role has read-only transactions before invoking pg_dump.
    connection = subprocess.run([executable('psql'), '-XqAt', '-v', 'ON_ERROR_STOP=1',
                                 '-c', 'show transaction_read_only'], env=env,
                                capture_output=True, text=True, timeout=30)
    if connection.returncode or connection.stdout.strip() != 'on':
        raise RuntimeError('Read-only Production connection verification failed')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with tempfile.TemporaryDirectory(prefix='tei-production-backup-', dir=destination) as temporary:
        staging = Path(temporary)
        dump = staging / 'production.dump.age'
        encrypt_stream([executable('pg_dump'), '--format=custom', '--no-password',
                        '--lock-wait-timeout=15000'], dump, recipient, env=env)
        verify_archive(dump, identity)
        manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'project_ref': PROD_REF,
                    'scope': 'full logical database archive; no Development sync artifacts',
                    'transaction_read_only': True, 'archive_verified': True,
                    'isolated_restore_rehearsal': False,
                    'encrypted_files': {'production.dump.age': sha256(dump)}}
        path = staging / 'manifest.json'
        path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        path.chmod(0o600)
        final = destination / f'tei-production-{stamp}'
        if final.exists():
            raise RuntimeError('Backup destination already exists')
        staging.rename(final)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--local-env', action='store_true')
    args = parser.parse_args()
    try:
        if args.local_env:
            ignored = subprocess.run(['git', 'check-ignore', '-q', '.env.local'], cwd=ROOT,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ignored.returncode:
                raise RuntimeError('Local environment must be ignored by Git')
            from scripts.run_dev import read_local_env
            os.environ.update(read_local_env(ROOT / '.env.local'))
        output = backup(args.output_dir, os.environ.get('TEI_PROD_DATABASE_URL', ''),
                        os.environ.get('TEI_BACKUP_AGE_RECIPIENT', ''),
                        Path(os.environ.get('TEI_BACKUP_AGE_IDENTITY') or '/nonexistent'))
    except Exception as error:
        print(json.dumps({'result': 'FAIL', 'error_type': type(error).__name__,
                          'details': 'Connection and credential values suppressed'}))
        return 1
    print(json.dumps({'result': 'PASS', 'project_ref': PROD_REF, 'backup': str(output),
                      'transaction_read_only': True, 'archive_verified': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
