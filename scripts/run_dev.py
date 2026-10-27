#!/usr/bin/env python3
"""Start the local server without sourcing .env.local in a shell."""

import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def read_local_env(path):
    if not path.exists():
        return {}
    if path.stat().st_mode & 0o077:
        raise RuntimeError(".env.local permissions must be 0600 or stricter")
    values = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not KEY.fullmatch(key.strip()):
            if line.startswith(("postgres://", "postgresql://")):
                raise RuntimeError(f"Bare database URL at .env.local line {number}; add TEI_DEV_DATABASE_URL= without printing the value")
            raise RuntimeError(f"Invalid .env.local format at line {number}; value suppressed")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def require_development_public_target(env):
    """Keep a missing local setting from falling back to Production reads."""
    from urllib.parse import urlsplit

    url = env.get("TEI_ENTITY_SUPABASE_URL") or env.get("SUPABASE_URL") or ""
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "canqjiokrtcxkwblhmml.supabase.co"
            or parsed.username or parsed.password or parsed.port or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment
            or not (env.get("TEI_ENTITY_ANON_KEY") or env.get("SUPABASE_ANON_KEY"))):
        raise RuntimeError("Local public reads require an explicit tei-development URL and anon key")
    private_url = env.get("TEI_PRIVATE_SUPABASE_URL")
    if private_url and private_url.rstrip("/") != url.rstrip("/"):
        raise RuntimeError("Local public and private Supabase targets must both be tei-development")
    if private_url and env.get("TEI_PRIVATE_SUPABASE_ANON_KEY") != (
            env.get("TEI_ENTITY_ANON_KEY") or env.get("SUPABASE_ANON_KEY")):
        raise RuntimeError("Local private access must use the same public anon key")


def main():
    try:
        local = read_local_env(ROOT / ".env.local")
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else "Unable to read .env.local; value suppressed", file=sys.stderr)
        raise SystemExit(1) from None
    env = os.environ.copy()
    env.update(local)
    try:
        require_development_public_target(env)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    os.execve(sys.executable, [sys.executable, str(ROOT / "app.py")], env)


if __name__ == "__main__":
    main()
