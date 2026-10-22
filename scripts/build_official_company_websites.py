#!/usr/bin/env python3
"""Snapshot official issuer-disclosed company websites for read-only matching.

The snapshot is versioned so a live company request never depends on three
large upstream feeds. A disclosed website is not proof of domain ownership or
safety. Only exact eight-digit ID, full company name and explicit HTTPS pass.
"""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.company_website_crosswalk import CROSSWALK, normalized_host  # noqa: E402

OUTPUT = ROOT / "src" / "official_company_website_snapshot.json"
SOURCES = (
    ("TWSE listed company basic data", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
     "https://data.gov.tw/dataset/18419", "營利事業統一編號", "公司名稱", "網址", "公司代號"),
    ("TWSE public company basic data", "https://openapi.twse.com.tw/v1/opendata/t187ap03_P",
     "https://data.gov.tw/dataset/28567", "營利事業統一編號", "公司名稱", "網址", "公司代號"),
    ("TPEX OTC company basic data", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
     "https://data.gov.tw/dataset/25036", "UnifiedBusinessNo.", "CompanyName", "WebAddress", "SecuritiesCompanyCode"),
)


def safe_website(value):
    raw = str(value or "").strip()
    if not raw or re.search(r"\s", raw):
        return None
    try:
        parsed = urlsplit(raw)
        if (parsed.scheme.lower() != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.fragment):
            return None
        normalized_host(raw)
    except ValueError:
        return None
    return raw


def probed_https_website(value):
    """Use an issuer's reported host only when HTTPS stays on that same host."""
    raw = str(value or "").strip()
    if not raw or re.search(r"\s", raw):
        return None
    candidate = raw if "://" in raw else "https://" + raw
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.fragment:
            return None
        expected_host = normalized_host("https://" + (parsed.hostname or ""))
        secure = parsed._replace(scheme="https").geturl()
        if not safe_website(secure):
            return None
        result = subprocess.run(
            ["curl", "-L", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{url_effective}",
             "--max-time", "10", secure], capture_output=True, text=True, timeout=12)
        status, final = result.stdout.strip().split(" ", 1)
        if result.returncode or not status.startswith(("2", "3")) or not safe_website(final):
            return None
        if normalized_host(final) != expected_host:
            return None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return secure


def make_snapshot(feeds, curated_rows, retrieved_at, *, focus_ids=frozenset(), probe=probed_https_website):
    curated = {row["uniform_number"]: row for row in curated_rows}
    seen = {}
    conflicts = set()
    source_counts = []
    for source, source_url, dataset_url, id_key, name_key, site_key, code_key in SOURCES:
        rows = feeds[source_url]
        if not isinstance(rows, list) or not 100 <= len(rows) <= 5000:
            raise ValueError(f"Unexpected official feed size: {source}")
        accepted = 0
        for row in rows:
            uniform = str(row.get(id_key) or "").strip()
            name = unicodedata.normalize("NFKC", str(row.get(name_key) or "")).strip()
            reported = row.get(site_key)
            website = safe_website(reported)
            normalized_from = None
            if not website and uniform in focus_ids:
                website = probe(reported)
                if website:
                    normalized_from = str(reported).strip()
            code = str(row.get(code_key) or "").strip()
            if not re.fullmatch(r"[0-9]{8}", uniform) or not name or not code or not website:
                continue
            candidate = {
                "uniform_number": uniform, "company_name": name,
                "website_url": website, "identity_source_url": source_url,
                "website_source_url": source_url, "source_dataset_url": dataset_url,
                "source_name": source, "source_record_id": code,
                "source_class": "official_issuer_disclosure",
                "match_basis": "official_disclosure_exact_uniform_and_full_name",
                "verified_on": retrieved_at[:10],
            }
            if normalized_from:
                candidate["reported_website_url"] = normalized_from
                candidate["match_basis"] = "official_disclosure_exact_id_name_and_same_host_https_probe"
            if uniform in curated:
                existing = curated[uniform]
                if (unicodedata.normalize("NFKC", existing["company_name"]).strip() != name
                        or normalized_host(existing["website_url"]) != normalized_host(website)):
                    conflicts.add(uniform)
                continue
            old = seen.get(uniform)
            if old and (old["company_name"] != name or
                        normalized_host(old["website_url"]) != normalized_host(website)):
                conflicts.add(uniform)
                continue
            seen.setdefault(uniform, candidate)
            accepted += 1
        source_counts.append({"source": source, "source_url": source_url,
                              "input_rows": len(rows), "eligible_rows": accepted})
    if conflicts:
        raise ValueError(f"Official website conflicts require manual review: {len(conflicts)} IDs")
    return {"generated_at": retrieved_at, "publication_scope": "read_only_company_website_projection",
            "sources": source_counts,
            "records": [seen[key] for key in sorted(seen)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-focus", action="store_true",
                        help="Probe non-HTTPS issuer URLs only for published tei-development company IDs")
    options = parser.parse_args()
    feeds = {}
    for _, url, *_ in SOURCES:
        req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./9.2", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as response:
            feeds[url] = json.load(response)
    curated = json.loads(CROSSWALK.read_text(encoding="utf-8"))
    focus_ids = set()
    if options.development_focus:
        from scripts.audit_graph_coverage_dev import is_development_target
        from scripts.audit_p0_data_chain import development_environment, query
        if not is_development_target(development_environment()):
            raise RuntimeError("Refusing to read company IDs from a non-Development database")
        focus_ids = set(json.loads(query("""select coalesce(json_agg(value),'[]'::json)
            from public.entity_identifiers i join public.entities e on e.id=i.entity_id
            where i.namespace='tw:uniform_number' and e.entity_type='Company'
              and e.publication_status='published';""")))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot = make_snapshot(feeds, curated, now, focus_ids=focus_ids)
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"generated_at": now, "official_https_pairs": len(snapshot["records"]),
                      "curated_pairs": len(curated), "source_counts": snapshot["sources"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
