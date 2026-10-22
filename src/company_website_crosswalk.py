"""Small, reviewed company-ID to official-domain crosswalk.

Only a verified official ID/name pair may use a curated domain. An absent row
means unknown, not that a company has no website. This is not a crawler.
"""
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import unicodedata


CROSSWALK = Path(__file__).with_name("company_website_crosswalk.json")


def _host(url):
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Official company website and provenance must use HTTPS")
    return parsed.hostname.lower().removeprefix("www.")


@lru_cache(maxsize=1)
def reviewed_websites():
    rows = json.loads(CROSSWALK.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Company website crosswalk must be a list")
    by_uniform = {}
    used_domains = set()
    for row in rows:
        uniform = row.get("uniform_number")
        if not isinstance(uniform, str) or not re.fullmatch(r"[0-9]{8}", uniform):
            raise ValueError("Company website requires an eight-digit identifier")
        name = row.get("company_name")
        domain = _host(row.get("website_url"))
        identity_source_host = _host(row.get("identity_source_url"))
        website_source_host = _host(row.get("website_source_url"))
        if (not isinstance(name, str) or not name.strip() or uniform in by_uniform
                or domain in used_domains or not row.get("match_basis") or not row.get("verified_on")):
            raise ValueError("Duplicate or incomplete company website proof")
        if website_source_host != domain and not website_source_host.endswith("." + domain):
            raise ValueError("Website proof must be on the reviewed company domain")
        if (identity_source_host != domain
                and not identity_source_host.endswith("." + domain)
                and identity_source_host != "job.taiwanjobs.gov.tw"):
            raise ValueError("Identity proof must come from the company or an official registry")
        by_uniform[uniform] = {**row, "domain": domain}
        used_domains.add(domain)
    return by_uniform


def verified_website(uniform, official_name):
    row = reviewed_websites().get(uniform)
    if not row or unicodedata.normalize("NFKC", official_name or "").strip() != row["company_name"]:
        return None
    return dict(row)
