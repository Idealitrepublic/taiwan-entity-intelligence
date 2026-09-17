"""Deployment-safe runtime configuration for public and user-owned data paths."""
from __future__ import annotations

import os

from .public_config import SUPABASE_PUBLISHABLE_KEY

DEFAULT_SUPABASE_URL = "https://rztdbdurkjfrirsrrhtu.supabase.co"


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
    return url.rstrip("/"), key or ""


def private_supabase_config() -> tuple[str, str]:
    """Require an explicitly paired environment for authenticated writes."""
    url = os.environ.get("TEI_PRIVATE_SUPABASE_URL")
    key = os.environ.get("TEI_PRIVATE_SUPABASE_ANON_KEY")
    if not url or not key:
        return "", ""
    return url.rstrip("/"), key
