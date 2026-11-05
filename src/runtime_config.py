"""Deployment-safe runtime configuration for public and user-owned data paths."""
from __future__ import annotations

import base64
import binascii
import json
import os

from .public_config import SUPABASE_PUBLISHABLE_KEY

DEFAULT_SUPABASE_URL = "https://rztdbdurkjfrirsrrhtu.supabase.co"


def public_key_or_empty(key: str) -> str:
    """Reject recognizable privileged credentials; Supabase verifies signatures.

    This is a configuration guard, not authentication or JWT verification.
    Only Supabase publishable keys and legacy anon JWTs belong in public paths.
    """
    if (not key or key.startswith('sb_secret_') or
            key == os.environ.get('SUPABASE_SERVICE_ROLE_KEY')):
        return ''
    if key.startswith('sb_publishable_'):
        return key if len(key) > len('sb_publishable_') else ''
    if key.count('.') == 2:
        try:
            payload = key.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        except (ValueError, binascii.Error, UnicodeError):
            return ''
        if not isinstance(claims, dict) or claims.get('role') != 'anon':
            return ''
        return key
    return ''


def public_supabase_config() -> tuple[str, str]:
    """Return browser-safe credentials for RLS-bound public reads."""
    url = (os.environ.get("TEI_ENTITY_SUPABASE_URL")
           or os.environ.get("SUPABASE_URL")
           or DEFAULT_SUPABASE_URL)
    key = (os.environ.get("TEI_ENTITY_ANON_KEY")
           or os.environ.get("SUPABASE_ANON_KEY")
           or os.environ.get("VITE_SUPABASE_ANON_KEY"))
    if not key and url.rstrip("/") == DEFAULT_SUPABASE_URL:
        key = SUPABASE_PUBLISHABLE_KEY
    return url.rstrip("/"), public_key_or_empty(key or "")


def private_supabase_config() -> tuple[str, str]:
    """Require an explicitly paired environment for authenticated writes."""
    url = os.environ.get("TEI_PRIVATE_SUPABASE_URL")
    key = os.environ.get("TEI_PRIVATE_SUPABASE_ANON_KEY")
    key = public_key_or_empty(key or '')
    if not url or not key:
        return "", ""
    return url.rstrip("/"), key
