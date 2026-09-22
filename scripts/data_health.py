#!/usr/bin/env python3
"""Read-only, bounded cross-source benchmark. No ingestion or DB writes."""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_health import SOURCES, metric, severity  # noqa: E402
from src.runtime_config import public_supabase_config  # noqa: E402
from src.sources.judicial_index import load_index, VERIFIED_CASES  # noqa: E402
from src.cloud_company import COMPANY_API, DIRECTOR_API, _moea_rows  # noqa: E402
from src.sources.procurement import lookup_awards  # noqa: E402

SAMPLE = (
    ("23060248", "全家便利商店股份有限公司"),
    ("22099131", "台灣積體電路製造股份有限公司"),
    ("96979933", "中華電信股份有限公司"),
)


def public_rows(table, filters=None, limit=100):
    """Indexed equality filters only; never request unbounded dataset counts."""
    url, key = public_supabase_config()
    if not key:
        raise RuntimeError("public Supabase key unavailable")
    query = {"select": "*", "limit": str(limit), **(filters or {})}
    address = f"{url}/rest/v1/{table}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(address, headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError(f"{table} did not return rows")
    return payload


def probe(name, fn):
    try:
        return fn(), None
    except Exception as exc:
        return None, type(exc).__name__


def benchmark(now=None):
    now = now or datetime.now(timezone.utc)
    output = []
    company_hits, director_hits, awards, penalty_rows = 0, 0, [], []
    error_counts = {name: 0 for name in SOURCES}
    observations = {name: [] for name in SOURCES}
    for uniform, company in SAMPLE:
        rows, err = probe("company_registration", lambda: _moea_rows(COMPANY_API, uniform, 1))
        error_counts["company_registration"] += bool(err)
        company_hits += bool(rows)
        if rows:
            observations["company_registration"].append({"id": uniform, "source_url": COMPANY_API, "retrieved_at": now.isoformat(), "provenance": "MOEA API"})
        rows, err = probe("directors", lambda: _moea_rows(DIRECTOR_API, uniform, 100))
        error_counts["directors"] += bool(err)
        director_hits += bool(rows)
        if rows:
            observations["directors"].extend({"id": f"{uniform}:{i}", "source_url": DIRECTOR_API, "retrieved_at": now.isoformat(), "provenance": "MOEA API"} for i, _ in enumerate(rows))
        result, err = probe("procurement", lambda: lookup_awards(uniform, limit=100))
        error_counts["procurement"] += bool(err or result and result.get("status") != "ok")
        if result and result.get("status") == "ok":
            awards.append(result)
            observations["procurement"].extend(result["records"])
        rows, err = probe("labor_penalties", lambda: public_rows(
            "source_records", {"company_name": "eq." + company, "dataset": "eq.penalties"}, 100))
        error_counts["labor_penalties"] += bool(err)
        if rows is not None:
            penalty_rows.extend(rows)
    sample_count = len(SAMPLE)
    output.append(metric("company_registration", observed=company_hits, expected=sample_count,
                         rows=observations["company_registration"], identity="id", timestamp=now.isoformat(),
                         errors=error_counts["company_registration"], scope="3 fixed valid-company identifiers; live MOEA", now=now))
    output.append(metric("directors", observed=director_hits, expected=sample_count,
                         rows=observations["directors"], identity="id", timestamp=now.isoformat(),
                         errors=error_counts["directors"], scope="same 3 identifiers; presence only", now=now))
    output.append(metric("procurement", observed=len(awards), expected=sample_count,
                         rows=observations["procurement"], identity="id", timestamp=None,
                         errors=error_counts["procurement"], scope="same 3 identifiers; mirror response, not award recall",
                         note="Notice source may lack retrieved_at/provenance; official PCC URL is a search entry.", now=now))
    output.append(metric("labor_penalties", observed=len(penalty_rows), expected=None,
                         rows=penalty_rows, identity="id", timestamp=max((row.get("indexed_at") or "" for row in penalty_rows), default=None),
                         errors=error_counts["labor_penalties"], scope="indexed company-name reads; national recall unknown",
                         note="Source records may mix penalty types; dataset-level count is deliberately omitted after timeout.", now=now))

    index = load_index()
    known = json.loads(Path(VERIFIED_CASES).read_text(encoding="utf-8"))["records"]
    jids = {row.get("jid") for row in index.get("records", [])}
    matched = sum(row.get("jid") in jids for row in known)
    sync = json.loads((ROOT / "data/public_sync_status.json").read_text(encoding="utf-8"))
    output.append(metric("judiciary", observed=matched, expected=len(known),
                         rows=index.get("records", []), identity="jid", timestamp=index.get("generated_at"),
                         errors=len(sync.get("errors") or []), scope="3 official known-case JIDs; not historical recall",
                         note="Prior sync status contains an error; historical index remains incomplete.", now=now))

    for name, table, filters in (
        ("politicians", "entities", {"entity_type": "eq.Politician"}),
        ("political_contributions", "relationships", {"relationship_type": "eq.POLITICAL_CONTRIBUTION_TO"}),
        ("asset_declarations", "asset_declarations", {}),
    ):
        rows, err = probe(name, lambda table=table, filters=filters: public_rows(table, filters, 100))
        output.append(metric(name, observed=len(rows) if rows is not None else None, expected=1,
                             rows=rows, identity="id", timestamp=None, errors=int(bool(err)),
                             scope="public published-data presence floor (>=1); not population coverage",
                             note="Draft adapter acceptance is not published live coverage.", now=now))
    output.append(metric("entity_resolution", observed=None, expected=None, errors=0,
                         scope="private resolution_candidates excluded by RLS",
                         note="Public anon role cannot audit private candidate precision; run a privileged offline export separately.", now=now))
    return {
        "generated_at": now.isoformat(), "benchmark_version": 1,
        "read_only": True, "sample_uniform_numbers": [item[0] for item in SAMPLE],
        "metrics": [{**item, "severity": severity(item)} for item in output],
    }


def markdown(report, db_audit=None):
    def fmt(value):
        return "unknown" if value is None else str(value)

    lines = ["# Data Health — DATA Phase 6", "", f"Generated: {report['generated_at']}",
             "", "This is a read-only, fixed-sample benchmark, **not national coverage**.",
             "Unknown values are not zero. Political rows test public publication presence, not adapter fixtures.",
             "", "| Source | Scope | Coverage | Freshness h | Errors | Duplicate | Provenance | Severity |",
             "|---|---|---:|---:|---:|---:|---:|---|"]
    for item in report["metrics"]:
        lines.append("| " + " | ".join(fmt(item[key]).replace("|", "/") for key in
                     ("source", "scope", "coverage", "freshness_hours", "error_count", "duplicate_rate", "provenance_rate", "severity")) + " |")
    lines.extend(["", "## Findings and disposition", "",
                  "- **High — publicly visible political data absent:** public presence probes returned zero, so draft ingestion has not yet become verified public coverage. Do not publish or mutate the shared Production database from this audit; review official source batches, RLS and publication separately. This release gate remains open.",
                  "- **High — judicial sync failure:** the checked-in status has an HTTP error although older `last_sync` exists. This report counts the error and never treats the timestamp as proof of a clean latest attempt. The sync now preserves the last usable index on failure; historical judiciary coverage remains a documented gap.",
                  "- **Medium — procurement/penalty provenance:** live mirror and legacy source records may lack per-row retrieval time, original record URL or provenance. Missing fields remain visible as unknown/partial; they are not fabricated.",
                  "- **Unknown — private resolution candidates:** anonymous read access is intentionally denied. Precision/recall from labeled tests does not establish live population quality.",
                  ""])
    if db_audit:
        lines.extend(["## Privileged, read-only database cross-check", "",
                      f"Audited: {db_audit['audited_at']} against {db_audit['project_ref']}; this is a separate snapshot, not refreshed by the public benchmark.",
                      "All publication states were counted using `scripts/data_health_remote.sql`:", ""])
        for name, count in db_audit["all_states_counts"].items():
            lines.append(f"- `{name}`: {count} rows across all states.")
        lines.extend(["", "DATA Phase 1–4 migrations absent from that database: " +
                      ", ".join(db_audit["missing_migration_versions"]) + ".",
                      "The master/contribution ingestion entrypoints are absent; the older asset entrypoint exists. Anon RLS is publication-filtered but cannot explain zero rows across all states.",
                      "Preview has no Supabase override in Vercel environment variables and falls back to this same public project. Therefore Preview cannot gain independent data without an isolated database.", ""])
    lines.extend(["## Reproduce and rollback", "",
                  "Run `python scripts/data_health.py --json reports/data_health.json --markdown docs/DATA_HEALTH.md`. For all-state database counts, rerun read-only `scripts/data_health_remote.sql` and refresh `reports/data_health_db_audit.json` before regeneration. No schema/data migration is included. Rollback removes the benchmark code and generated artifacts; Production is unchanged.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--db-audit", type=Path, default=ROOT / "reports/data_health_db_audit.json")
    args = parser.parse_args()
    report = benchmark()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        audit = json.loads(args.db_audit.read_text(encoding="utf-8")) if args.db_audit.is_file() else None
        args.markdown.write_text(markdown(report, audit), encoding="utf-8")
    print(json.dumps({"severity": {m["source"]: m["severity"] for m in report["metrics"]},
                      "report": str(args.markdown or args.json or "stdout")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
