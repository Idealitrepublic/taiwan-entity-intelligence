#!/usr/bin/env python3
"""Encrypt a Development pg_dump and its matching local sync evidence bundle.

No database URL, password, key, source row or decrypted dump is printed or
written inside the repository. This never connects to Production.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEV_REF = "canqjiokrtcxkwblhmml"
PROD_REF = "rztdbdurkjfrirsrrhtu"
SYNC_FILES = (
    "data/judicial_jlist_snapshot.json", "data/public_sync_state.json",
    "data/public_evidence.jsonl", "data/public_sync_status.json",
    "data/judicial_company_index.json", "reports/data_health.json",
)


def database_environment(value):
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    user = unquote(parsed.username or "")
    direct = host == f"db.{DEV_REF}.supabase.co" and user == "postgres"
    pooler = (host.endswith(".pooler.supabase.com") and
              user == f"postgres.{DEV_REF}")
    if (parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname or
            not parsed.path.strip("/") or not parsed.password or
            parsed.port not in (None, 5432, 6543) or not (direct or pooler) or
            PROD_REF in host or PROD_REF in user):
        raise ValueError("Only a password-protected tei-development database URL is accepted")
    return {"PGHOST": parsed.hostname, "PGPORT": str(parsed.port or 5432),
            "PGUSER": user,
            "PGPASSWORD": unquote(parsed.password),
            "PGDATABASE": unquote(parsed.path.lstrip("/")),
            "PGSSLMODE": "require"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def executable(name):
    found = shutil.which(name)
    if not found and name in ("pg_dump", "pg_restore"):
        candidate = Path(f"/opt/homebrew/opt/libpq/bin/{name}")
        found = str(candidate) if candidate.exists() else None
    if not found:
        raise RuntimeError(f"Required local tool unavailable: {name}")
    return found


def validate_destination(path):
    path = path.expanduser().resolve()
    if path == Path("/") or path == Path.home() or path == ROOT or path.is_relative_to(ROOT):
        raise ValueError("Backup destination must be a dedicated directory outside this repository")
    if not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError("Backup destination must already exist with owner-only permissions (0700)")
    return path


def encrypt_stream(command, output, recipient, *, env=None):
    """Stream plaintext directly into age; never create a plaintext dump file."""
    with output.open("wb") as target:
        target.flush()
        age = subprocess.Popen([executable("age"), "-r", recipient], stdin=subprocess.PIPE,
                               stdout=target, stderr=subprocess.DEVNULL)
        source = subprocess.Popen(command, stdout=age.stdin, stderr=subprocess.DEVNULL, env=env)
        age.stdin.close()
        source_ok = source.wait() == 0
        age_ok = age.wait() == 0
    output.chmod(0o600)
    if not source_ok or not age_ok or not output.stat().st_size:
        raise RuntimeError("Encrypted backup stream failed; no archive was published")


def encrypt_sync_bundle(output, recipient, hashes):
    with output.open("wb") as target:
        age = subprocess.Popen([executable("age"), "-r", recipient], stdin=subprocess.PIPE,
                               stdout=target, stderr=subprocess.DEVNULL)
        try:
            with tarfile.open(fileobj=age.stdin, mode="w|") as archive:
                for relative in SYNC_FILES:
                    archive.add(ROOT / relative, arcname=relative, recursive=False)
                manifest = json.dumps({"files": hashes}, sort_keys=True).encode()
                info = tarfile.TarInfo("manifest.json")
                info.mode = 0o600
                info.size = len(manifest)
                archive.addfile(info, io.BytesIO(manifest))
        finally:
            age.stdin.close()
        if age.wait() != 0:
            raise RuntimeError("Evidence bundle encryption failed")
    output.chmod(0o600)


def verify_archive(path, identity):
    if not path.name.endswith(".dump.age"):
        return verify_bundle(path, identity)
    age = subprocess.Popen([executable("age"), "-d", "-i", str(identity), str(path)],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    consumer = subprocess.Popen([executable("pg_restore"), "--list"], stdin=age.stdout,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    age.stdout.close()
    consumer_ok = consumer.wait() == 0
    age_ok = age.wait() == 0
    good = consumer_ok and age_ok
    if not good:
        raise RuntimeError("Encrypted archive verification failed")


def verify_bundle(path, identity):
    """Decrypt to a stream and verify exact members and content hashes."""
    age = subprocess.Popen([executable("age"), "-d", "-i", str(identity), str(path)],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    actual = {}
    expected = None
    try:
        with tarfile.open(fileobj=age.stdout, mode="r|") as archive:
            for member in archive:
                if not member.isfile() or member.name not in (*SYNC_FILES, "manifest.json"):
                    raise RuntimeError("Unexpected backup member")
                stream = archive.extractfile(member)
                if member.name == "manifest.json":
                    expected = json.load(stream).get("files")
                else:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                    if member.name in actual:
                        raise RuntimeError("Duplicate backup member")
                    actual[member.name] = digest.hexdigest()
    except (tarfile.TarError, json.JSONDecodeError, EOFError) as exc:
        raise RuntimeError("Evidence bundle could not be decoded") from exc
    finally:
        age.stdout.close()
        age_ok = age.wait() == 0
    if not age_ok or not isinstance(expected, dict) or actual != expected:
        raise RuntimeError("Evidence bundle hash verification failed")
    return actual


def backup(destination, url, recipient, identity):
    destination = validate_destination(destination)
    if not recipient.startswith("age1") or len(recipient) < 30:
        raise ValueError("Use an age public recipient; do not provide a private key")
    if not identity.is_file() or identity.stat().st_mode & 0o077:
        raise ValueError("age identity must be an existing owner-only file (0600)")
    pg_env = {**os.environ, **database_environment(url)}
    source_paths = {name: ROOT / name for name in SYNC_FILES}
    if any(not path.is_file() for path in source_paths.values()):
        raise RuntimeError("Matching judicial snapshot, state, Evidence, status, index and health are required")
    before = {name: sha256(path) for name, path in source_paths.items()}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix="tei-backup-", dir=destination) as staging_name:
        staging = Path(staging_name)
        dump = staging / "development.dump.age"
        evidence = staging / "sync-evidence.tar.age"
        encrypt_stream([executable("pg_dump"), "--format=custom", "--no-password"],
                       dump, recipient, env=pg_env)
        encrypt_sync_bundle(evidence, recipient, before)
        if {name: sha256(path) for name, path in source_paths.items()} != before:
            raise RuntimeError("Sync files changed during backup; retry after ingestion stops")
        verify_archive(dump, identity)
        verify_archive(evidence, identity)
        manifest = {"created_at": datetime.now(timezone.utc).isoformat(),
                    "project_ref": DEV_REF, "scope": "database logical archive plus local sync artifacts",
                    "encrypted_files": {name: sha256(staging / name) for name in
                                        ("development.dump.age", "sync-evidence.tar.age")},
                    "source_sha256": before, "archive_verified": True,
                    "isolated_restore_rehearsal": False}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (staging / "manifest.json").chmod(0o600)
        final = destination / f"tei-development-{stamp}"
        if final.exists():
            raise RuntimeError("Backup destination already exists")
        staging.rename(final)
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("TEI_DEV_DATABASE_URL") or ""
    recipient = os.environ.get("TEI_BACKUP_AGE_RECIPIENT") or ""
    identity = Path(os.environ.get("TEI_BACKUP_AGE_IDENTITY") or "/nonexistent")
    try:
        output = backup(args.output_dir, url, recipient, identity)
    except (ValueError, RuntimeError) as exc:
        print(f"Backup not completed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"backup": str(output), "project_ref": DEV_REF,
                      "archive_verified": True, "isolated_restore_rehearsal": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
