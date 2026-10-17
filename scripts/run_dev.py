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


def main():
    try:
        local = read_local_env(ROOT / ".env.local")
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else "Unable to read .env.local; value suppressed", file=sys.stderr)
        raise SystemExit(1) from None
    env = os.environ.copy()
    env.update(local)
    os.execve(sys.executable, [sys.executable, str(ROOT / "app.py")], env)


if __name__ == "__main__":
    main()
