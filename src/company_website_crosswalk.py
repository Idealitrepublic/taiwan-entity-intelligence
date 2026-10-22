"""Small, reviewed company-ID to official-domain crosswalk.

Only a verified official ID/name pair may use a curated domain. An absent row
means unknown, not that a company has no website. This is not a crawler.
"""
from functools import lru_cache
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import unicodedata


CROSSWALK = Path(__file__).with_name("company_website_crosswalk.json")
OFFICIAL_SNAPSHOT = Path(__file__).with_name("official_company_website_snapshot.json")


def _host(url):
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Official company website and provenance must use HTTPS")
    host = parsed.hostname.lower().removeprefix("www.")
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host):
        raise ValueError("Official company website must have a public domain")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("An IP address is not an official company domain")
    if host.endswith((".local", ".localhost", ".internal", ".invalid", ".test", ".example")):
        raise ValueError("Reserved domains cannot be official company websites")
    return host


def normalized_host(url):
    return _host(url)


@lru_cache(maxsize=1)
def reviewed_websites():
    manual = json.loads(CROSSWALK.read_text(encoding="utf-8"))
    snapshot = json.loads(OFFICIAL_SNAPSHOT.read_text(encoding="utf-8"))
    rows = manual + snapshot.get("records", []) if isinstance(manual, list) and isinstance(snapshot, dict) else None
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
        is_disclosure = row.get("source_class") == "official_issuer_disclosure"
        if (not isinstance(name, str) or not name.strip() or uniform in by_uniform
                or (not is_disclosure and domain in used_domains)
                or not row.get("match_basis") or not row.get("verified_on")):
            raise ValueError("Duplicate or incomplete company website proof")
        official_host = {"openapi.twse.com.tw", "tpex.org.tw"}
        if is_disclosure and (not row.get("source_record_id") or
                              website_source_host not in official_host or
                              identity_source_host != website_source_host):
            raise ValueError("Issuer disclosure requires an official row locator")
        if (not is_disclosure and website_source_host != domain
                and not website_source_host.endswith("." + domain)):
            raise ValueError("Website proof must be on the reviewed company domain")
        if (not is_disclosure and identity_source_host != domain
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
