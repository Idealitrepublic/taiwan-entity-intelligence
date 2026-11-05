#!/usr/bin/env python3
"""Rehearse an encrypted Development archive in a new, socket-only local PG cluster.

Never restores into an existing database, logs SQL/dump content, or changes the
source. Supabase-managed services and original ownership/ACLs are out of scope.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ops_backup import database_environment, executable, verify_archive  # noqa: E402


def pg_tool(name):
    found = shutil.which(name)
    for directory in ('/opt/homebrew/opt/postgresql@18/bin', '/opt/homebrew/opt/libpq/bin'):
        candidate = Path(directory) / name
        if not found and candidate.is_file():
            found = str(candidate)
    if not found:
        raise RuntimeError(f'Required local tool unavailable: {name}')
    return found


def query(env, sql, *, read_only=True):
    child = {**env, 'PGCONNECT_TIMEOUT': '15'}
    if read_only:
        child['PGOPTIONS'] = ('-c default_transaction_read_only=on -c statement_timeout=60000 '
                              '-c search_path=pg_catalog,public,extensions,auth,tei_private')
    result = subprocess.run([executable('psql'), '-XqAt', '-v', 'ON_ERROR_STOP=1'],
                            input=sql, text=True, capture_output=True, env=child, timeout=90)
    if result.returncode:
        raise RuntimeError('Database verification failed; connection and SQL details suppressed')
    return json.loads(result.stdout) if read_only else None


def sql_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def restore_error_category(stderr):
    """Classify without exposing SQL, rows or credentials in the dump error."""
    value = stderr.decode('utf-8', errors='replace').lower()
    missing = re.search(r'error:  (role|schema|function|type|relation) "([a-z_][a-z0-9_.]*)" does not exist', value)
    if missing:
        return 'missing local prerequisite ' + missing.group(1) + ': ' + missing.group(2)
    for needle, label in (
            ('already exists', 'local prerequisite object already exists'),
            ('does not exist', 'missing local prerequisite object'),
            ('permission denied', 'local permission denied'),
            ('could not open extension control file', 'local extension unavailable'),
            ('violates foreign key', 'foreign key violation'),
            ('invalid input', 'invalid archived value')):
        if needle in value:
            return label
    return 'unclassified archive restore failure'


def normalize_constraint(row):
    """Allow only the two observed PG17/18 equivalent AND-parenthesization forms."""
    known = {'relationships_percentage_check': ('percentage', '100'),
             'resolution_candidates_score_check': ('score', '1')}
    field, upper = known.get(row['conname'], ('', ''))
    if field:
        left = f'({field} >= (0)::numeric) AND ({field} <= ({upper})::numeric)'
        last = f"({field} <> 'NaN'::numeric)"
        variants = (f'CHECK ((({left}) AND {last}))', f'CHECK (({left} AND {last}))')
        if row.get('definition') in variants:
            row = {**row, 'definition': variants[0]}
    return row


def snapshot(env):
    tables = query(env, "select json_agg(tablename order by tablename) from pg_tables where schemaname='public'")
    counts = []
    for name in tables:
        literal = name.replace("'", "''")
        counts.append(f"select '{literal}' as name, count(*) as rows from public.{sql_identifier(name)}")
    result = query(env, """select json_build_object(
      'rows',(select json_object_agg(name,rows) from (""" + ' union all '.join(counts) + """) t),
      'columns',(select json_agg(t order by table_name,ordinal_position) from
        (select table_name,column_name,ordinal_position,data_type,udt_schema,udt_name,
                character_maximum_length,numeric_precision,numeric_scale,datetime_precision,
                is_nullable,column_default,is_identity,identity_generation
         from information_schema.columns where table_schema='public') t),
      'indexes',(select json_agg(t order by indexname) from
        (select indexname,indexdef from pg_indexes where schemaname='public') t),
      'policies',(select json_agg(t order by tablename,policyname) from
        (select tablename,policyname,permissive,roles,cmd,qual,with_check from pg_policies where schemaname='public') t),
      'rls',(select json_agg(t order by relname) from
        (select relname,relrowsecurity,relforcerowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace
         where n.nspname='public' and c.relkind='r') t),
      'constraints',(select json_agg(t order by table_name,conname) from
        (select c.relname table_name,k.conname,k.contype,k.convalidated,
                pg_get_constraintdef(k.oid) definition
         from pg_constraint k join pg_class c on c.oid=k.conrelid
         join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and k.contype<>'n') t),
      'functions',(select json_agg(t order by signature) from
        (select p.oid::regprocedure::text signature,md5(pg_get_functiondef(p.oid)) definition_hash
         from pg_proc p join pg_namespace n on n.oid=p.pronamespace
         where n.nspname in ('public','auth','tei_private') and p.prokind in ('f','p')
           and not exists(select 1 from pg_depend d where d.classid='pg_proc'::regclass
             and d.objid=p.oid and d.deptype='e')) t),
      'triggers',(select json_agg(t order by table_name,tgname) from
        (select c.relname table_name,g.tgname,g.tgenabled,md5(pg_get_triggerdef(g.oid)) definition_hash
         from pg_trigger g join pg_class c on c.oid=g.tgrelid
         join pg_namespace n on n.oid=c.relnamespace
         where n.nspname='public' and not g.tgisinternal) t),
      'migrations',(select json_agg(t order by version) from
        (select version,name from supabase_migrations.schema_migrations) t))""")
    result['constraints'] = [normalize_constraint(row) for row in result['constraints']]
    # PostgreSQL source/local collations may sort identifiers differently.
    for key, value in result.items():
        if isinstance(value, list):
            result[key] = sorted(value, key=lambda row: json.dumps(row, sort_keys=True))
    return result


def validate_archive(folder):
    folder = folder.expanduser().resolve()
    if folder.is_relative_to(ROOT) or not folder.is_dir() or folder.stat().st_mode & 0o077:
        raise ValueError('Use an owner-only backup directory outside the repository')
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest.get('project_ref') != 'canqjiokrtcxkwblhmml' or not manifest.get('archive_verified'):
        raise ValueError('Only a verified tei-development archive is accepted')
    if set(manifest.get('encrypted_files', {})) != {'development.dump.age', 'sync-evidence.tar.age'}:
        raise ValueError('Incomplete encrypted archive manifest')
    for name, digest in manifest['encrypted_files'].items():
        path = folder / name
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest or path.stat().st_mode & 0o077:
            raise ValueError('Encrypted archive integrity or permissions failed')
    return folder


def drill(folder, source_url, identity):
    folder = validate_archive(folder)
    if not identity.is_file() or identity.stat().st_mode & 0o077:
        raise ValueError('An owner-only age identity is required')
    # Remove ambient PG service/connection options before defining either target.
    base = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    source = {**base, **database_environment(source_url)}
    before = snapshot(source)
    verify_archive(folder / 'development.dump.age', identity)
    verify_archive(folder / 'sync-evidence.tar.age', identity)
    with tempfile.TemporaryDirectory(prefix='tei-restore-', dir='/private/tmp') as temporary:
        home = Path(temporary)
        home.chmod(0o700)
        cluster, socket = home / 'cluster', home / 'socket'
        socket.mkdir(mode=0o700)
        local = {**base, 'PGHOST': str(socket), 'PGPORT': '5432',
                 'PGUSER': 'tei_restore', 'PGDATABASE': 'postgres', 'PGSSLMODE': 'disable'}
        def run(command):
            result = subprocess.run(command, env=local, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=180)
            if result.returncode:
                raise RuntimeError('Isolated PostgreSQL command failed; sensitive output suppressed')
        run([pg_tool('initdb'), '-D', str(cluster), '-U', 'tei_restore', '-A', 'trust', '--no-locale', '-E', 'UTF8'])
        started = False
        try:
            options = f"-c listen_addresses='' -c unix_socket_directories={socket} -c unix_socket_permissions=0700"
            run([pg_tool('pg_ctl'), '-D', str(cluster), '-l', '/dev/null', '-o', options, '-w', 'start'])
            started = True
            query(local, """create role anon; create role authenticated; create role service_role bypassrls;
                create role supabase_auth_admin; create role supabase_storage_admin;
                create role supabase_admin; create role authenticator;
                create schema auth; create schema supabase_migrations; create schema tei_private;
                create schema extensions; create extension pgcrypto with schema extensions;
                create extension "uuid-ossp" with schema extensions; create extension pg_trgm with schema public;""",
                  read_only=False)
            age = subprocess.Popen([executable('age'), '-d', '-i', str(identity),
                                    str(folder / 'development.dump.age')], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
            restore = subprocess.Popen([executable('pg_restore'), '--dbname=postgres', '--no-owner',
                                         '--no-privileges', '--exit-on-error', '--schema=public',
                                         '--schema=auth', '--schema=supabase_migrations', '--schema=tei_private'],
                                        stdin=age.stdout, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, env=local)
            age.stdout.close()
            try:
                _, restore_error = restore.communicate(timeout=300)
                restore_code = restore.returncode
                age_code = age.wait(timeout=30)
            finally:
                for process in (restore, age):
                    if process.poll() is None:
                        process.kill()
                        process.wait()
            if restore_code or age_code:
                raise RuntimeError('Isolated application-schema restore failed: ' + restore_error_category(restore_error))
            restored, after = snapshot(local), snapshot(source)
            if before != after or before != restored:
                differences = [key for key in before if before[key] != restored.get(key)]
                details = []
                for key, identity_key in (('constraints', 'conname'), ('functions', 'signature')):
                    original = {row[identity_key]: row for row in before.get(key, [])}
                    actual = {row[identity_key]: row for row in restored.get(key, [])}
                    changed = [name for name in original.keys() | actual.keys() if original.get(name) != actual.get(name)]
                    if changed:
                        details.append(key + '=' + ','.join(sorted(changed)[:12]))
                raise RuntimeError('Source changed or restored metadata/count mismatch: ' + ','.join(differences) + '; ' + '; '.join(details))
            query(local, 'grant usage on schema public,auth to anon; grant select on all tables in schema public to anon;',
                  read_only=False)
            anonymous = query(local, """set role anon; select json_build_object(
                'entities',(select count(*) from public.entities),
                'relationships',(select count(*) from public.relationships),
                'evidence',(select count(*) from public.evidence_records),
                'workspaces',(select count(*) from public.investigation_workspaces),
                'saved_items',(select count(*) from public.workspace_items));""")
            expected = query(source, """select json_build_object(
                'entities',(select count(*) from public.entities where publication_status='published'),
                'relationships',(select count(*) from public.relationships where status='published'),
                'evidence',(select count(*) from public.evidence_records where publication_status='published' and status='active'),
                'workspaces',0,'saved_items',0);""")
            if anonymous != expected:
                raise RuntimeError('Restored anonymous visibility or private RLS boundary mismatch')
            return {'result': 'PASS', 'project_ref': 'canqjiokrtcxkwblhmml',
                    'target': 'disposable local PostgreSQL, Unix socket only',
                    'tables': len(restored['rows']), 'migrations': len(restored['migrations']),
                    'indexes': len(restored['indexes']), 'rls_policies': len(restored['policies']),
                    'constraints': len(restored['constraints']), 'functions': len(restored['functions']),
                    'triggers': len(restored['triggers']),
                    'row_counts': restored['rows'], 'anonymous': anonymous,
                    'scope': 'application schemas; excludes managed services and original ownership/ACLs'}
        finally:
            if started:
                run([pg_tool('pg_ctl'), '-D', str(cluster), '-m', 'immediate', '-w', 'stop'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir', required=True, type=Path)
    parser.add_argument('--local-env', action='store_true', help='Load owner-only .env.local inside this child process')
    args = parser.parse_args()
    try:
        if args.local_env:
            from scripts.run_dev import read_local_env
            os.environ.update(read_local_env(ROOT / '.env.local'))
        result = drill(args.backup_dir, os.environ.get('TEI_DEV_DATABASE_URL', ''),
                       Path(os.environ.get('TEI_BACKUP_AGE_IDENTITY') or '/nonexistent'))
    except Exception as error:
        # Only our fixed diagnostics are safe; never echo driver/URL exceptions.
        detail = str(error) if type(error) is RuntimeError else 'Sensitive exception details suppressed'
        print(json.dumps({'result': 'FAIL', 'error_type': type(error).__name__, 'detail': detail}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
