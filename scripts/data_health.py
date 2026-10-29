#!/usr/bin/env python3
"""Read-only, bounded cross-source benchmark. No ingestion or DB writes."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_health import SOURCES, age_hours, metric, ratio, severity  # noqa: E402
from src.runtime_config import public_supabase_config  # noqa: E402
from src.sources.judicial_index import load_index, VERIFIED_CASES  # noqa: E402
from src.cloud_company import COMPANY_API, DIRECTOR_API, _moea_rows  # noqa: E402
from src.sources.procurement import lookup_awards  # noqa: E402

SAMPLE = (
    ("23060248", "全家便利商店股份有限公司"),
    ("22099131", "台灣積體電路製造股份有限公司"),
    ("96979933", "中華電信股份有限公司"),
)
LEGISLATIVE_COMMITTEES = "https://data.ly.gov.tw/odw/ID14Action.action?committee=&name=&fileType=json"


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


def with_primary_provenance(rows):
    """Use the RLS-visible primary Evidence, not empty fact-table columns."""
    if rows is None:
        return None
    output = []
    for row in rows:
        proof = row.get("evidence_records") or {}
        output.append({**row, "source_url": proof.get("source_url"),
                       "retrieved_at": proof.get("retrieved_at"),
                       "provenance": proof.get("source_name"),
                       "source_record_id": proof.get("source_record_id")})
    return output


def with_source_file_provenance(rows):
    """Verify the existing MOL raw-row -> official snapshot chain, not a URL alone."""
    output = []
    for row in rows or []:
        item = dict(row)
        source = row.get("source_files") or {}
        dataset_id = str((source.get("metadata") or {}).get("dataset_id") or "")
        raw = row.get("raw")
        digest = hashlib.sha256((dataset_id + "|" + json.dumps(
            raw, ensure_ascii=False, sort_keys=True)).encode()).hexdigest() if isinstance(raw, dict) else None
        url = urllib.parse.urlsplit(str(source.get("source_url") or ""))
        if (source.get("id") == row.get("source_file_id") and source.get("id")
                and source.get("dataset") == row.get("dataset") == "penalties"
                and dataset_id in ("109896", "109897", "110908")
                and row.get("source_url") == f"https://data.gov.tw/dataset/{dataset_id}"
                and url.scheme == "https" and url.hostname == "apiservice.mol.gov.tw"
                and re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256") or ""))
                and row.get("id") == f"mol:{digest}"
                and age_hours(source.get("downloaded_at"), datetime.now(timezone.utc)) is not None):
            item.update(retrieved_at=source["downloaded_at"], provenance={
                "source_file_id": source["id"], "snapshot_sha256": source["sha256"],
                "source_record_id": row["id"], "download_url": source["source_url"],
                "raw_record_sha256": digest, "scope": "indexed_row_and_snapshot_metadata",
                "original_file_retained": None,
                "original_file_retention_scope": "not_verifiable_from_public_snapshot_metadata"})
        output.append(item)
    return output


def verified_term_freshness(terms, verifications):
    """Use rechecks only for their exact original term proof; never hide stale peers."""
    stamps, verified, unknown = [], 0, False
    for term in terms or []:
        stamp = term.get("retrieved_at")
        if age_hours(stamp, datetime.now(timezone.utc)) is None:
            stamp = None
        candidates = []
        for proof in verifications or []:
            locator = proof.get("source_locator") or {}
            if (locator.get("verified_evidence_id") == term.get("primary_evidence_id")
                    and locator.get("legislator_number") == term.get("legislator_number")
                    and locator.get("term") == term.get("term_number") == 11
                    and locator.get("match_method") == "unchanged_fact_exact_official_identifier"
                    and re.fullmatch(r"[0-9a-f]{64}", str(locator.get("snapshot_sha256") or ""))
                    and proof.get("source_url") == term.get("source_url")
                    and age_hours(proof.get("retrieved_at"), datetime.now(timezone.utc)) is not None):
                candidates.append(proof["retrieved_at"])
        if candidates:
            latest = max(candidates, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
            if not stamp or datetime.fromisoformat(latest) > datetime.fromisoformat(stamp.replace("Z", "+00:00")):
                stamp = latest
                verified += 1
        if stamp:
            stamps.append(stamp)
        else:
            unknown = True
    oldest = min(stamps, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))) if stamps and not unknown else None
    return oldest, verified


def official_term_11_ids():
    # The official host uses legacy TLS renegotiation that Python's OpenSSL
    # rejects on some Macs. curl supports this endpoint without disabling TLS.
    response = subprocess.run(["curl", "-fsSL", "--max-time", "25", LEGISLATIVE_COMMITTEES],
                              capture_output=True, check=True, timeout=30)
    payload = json.loads(response.stdout)
    rows = payload.get("dataList") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Legislative Yuan committee payload is invalid")
    identifiers = {str(row.get("lgno")) for row in rows if isinstance(row, dict)
                   and str(row.get("term")) == "11" and str(row.get("lgno") or "").isdigit()}
    if not identifiers:
        raise ValueError("Legislative Yuan term 11 identifiers are empty")
    return identifiers


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
            observations["procurement"].extend({**row,
                "retrieved_at": result.get("retrieved_at"), "provenance": result.get("source")}
                for row in result["records"])
        rows, err = probe("labor_penalties", lambda: public_rows(
            "source_records", {"company_name": "eq." + company, "dataset": "eq.penalties",
                               "select": "*,source_files(id,dataset,sha256,source_url,downloaded_at,metadata)"}, 100))
        error_counts["labor_penalties"] += bool(err)
        if rows is not None:
            penalty_rows.extend(with_source_file_provenance(rows))
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
                         rows=penalty_rows, identity="id", timestamp=max((row.get("retrieved_at") or "" for row in penalty_rows), default=None),
                         errors=error_counts["labor_penalties"], scope="indexed company-name reads; national recall unknown",
                         note="Raw-row hashes and official snapshot metadata checked; external_source_only does not prove original CSV retention. National recall unknown.", now=now))

    index = load_index()
    known = json.loads(Path(VERIFIED_CASES).read_text(encoding="utf-8"))["records"]
    jids = {row.get("jid") for row in index.get("records", [])}
    matched = sum(row.get("jid") in jids for row in known)
    sync = json.loads((ROOT / "data/public_sync_status.json").read_text(encoding="utf-8"))
    service_closed = any(item.get("source") == "judicial" and
                         item.get("error_type") == "service_closed"
                         for item in sync.get("errors") or [])
    judicial_errors = sum(item.get("source") == "judicial" and
                          item.get("error_type") != "service_closed"
                          for item in sync.get("errors") or [])
    judicial_status = sync.get("judicial_status")
    if (not service_closed and judicial_status is not None and
            judicial_status not in ("ok", "upstream_unavailable", "partial")):
        judicial_errors += 1
    upstream_unavailable = sync.get("judicial_source_unavailable") or []
    progress = sync.get("judicial_progress") or {}
    judicial_window = sync.get("judicial_window") or {}
    attempted_batches = None
    snapshot_path = ROOT / "data/judicial_jlist_snapshot.json"
    state_path = ROOT / "data/public_sync_state.json"
    if snapshot_path.exists() and state_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        state_progress = state_data.get("judicial_progress") or {}
        if (snapshot.get("window_id") == state_progress.get("window_id") and
                progress.get("total_batches") == state_progress.get("total_batches")):
            attempted_batches = len(state_data.get("judicial_batch_stats") or {})
            if not judicial_window.get("total"):
                judicial_window = {"total": len(snapshot.get("jids") or []),
                                   "window_id": snapshot["window_id"]}
    totals = sync.get("judicial_totals") or {}
    attempted_jids = totals.get("attempted_jids") or 0
    ingested_jids = totals.get("ingested_jids") or 0
    pending_jids = totals.get("pending_jids") or 0
    unavailable_jids = totals.get("upstream_unavailable_jids") or len(upstream_unavailable)
    judicial_window_quality = {
        "jlist_total": judicial_window.get("total"),
        "attempted_jids": attempted_jids,
        "ingested_jids": ingested_jids,
        "pending_jids": pending_jids,
        "upstream_unavailable_jids": unavailable_jids,
        "jlist_processing_coverage": ratio(attempted_jids, judicial_window.get("total") or 0),
        "ingestion_failure_rate": ratio(pending_jids, attempted_jids - unavailable_jids),
        "upstream_unavailable_rate": ratio(unavailable_jids, attempted_jids),
        "last_attempt_age_hours": age_hours(sync.get("last_attempt"), now),
        "completed_batches": progress.get("completed_batches", 0),
        "attempted_batches": attempted_batches,
        "total_batches": progress.get("total_batches", 0),
    }
    unprocessed_batches = max(0, progress.get("total_batches", 0) -
                              progress.get("completed_batches", 0))
    judicial_metric = metric("judiciary", observed=matched, expected=len(known),
                             rows=index.get("records", []), identity="jid", timestamp=index.get("generated_at"),
                             errors=judicial_errors, scope="3 official known-case JIDs; not historical recall",
                             note=(f"T.E.I. ingestion errors: {judicial_errors}; verified upstream unavailable: "
                                   f"{len(upstream_unavailable)}; unprocessed JList batches: "
                                   f"{unprocessed_batches}. Historical recall remains unknown."), now=now)
    judicial_metric["unprocessed_batches"] = unprocessed_batches
    judicial_metric["upstream_unavailable_rate"] = judicial_window_quality["upstream_unavailable_rate"]
    output.append(judicial_metric)

    source_ids, source_err = probe("politicians", official_term_11_ids)
    terms, terms_err = probe("politicians", lambda: public_rows("politician_terms", {
        "term_number": "eq.11", "select": "*,evidence_records!politician_terms_primary_evidence_id_fkey"
        "(source_url,retrieved_at,source_name,source_record_id)"}, 250))
    terms = with_primary_provenance(terms)
    matched_ids = ({str(row.get("legislator_number")) for row in terms if row.get("legislator_number") in source_ids}
                   if terms is not None and source_ids else set())
    verifications, verification_err = probe("politicians", lambda: public_rows("evidence_records", {
        "source_name": "eq.立法院開放資料服務平台", "source_record_id": "like.verification:member:11:*",
        "select": "source_url,source_locator,retrieved_at", "order": "retrieved_at.desc"}, 250))
    term_freshness, rechecked = verified_term_freshness(terms, verifications)
    output.append(metric("politicians", observed=len(matched_ids) if terms is not None and source_ids else None,
                         expected=len(source_ids) if source_ids else None,
                         rows=terms, identity="id",
                         timestamp=term_freshness,
                         errors=int(bool(source_err)) + int(bool(terms_err)) + int(bool(verification_err)),
                         scope="official term-11 committee lgno matched to published politician_terms; not all legislators",
                         note=(f"Exact official IDs; {rechecked} term facts rechecked against immutable official snapshot proofs. "
                               "Freshness uses the oldest verified/read term in this cohort; term dates and original Evidence are unchanged."),
                         required_data=True, now=now))

    for name, table, foreign_key, filters in (
        ("political_contributions", "relationships", "relationships_primary_evidence_id_fkey",
         {"relationship_type": "eq.POLITICAL_CONTRIBUTION_TO"}),
        ("asset_declarations", "asset_declarations", "asset_declarations_primary_evidence_id_fkey", {}),
    ):
        select = ("id,primary_evidence_id,evidence_records!" + foreign_key +
                  "(source_url,retrieved_at,source_name,source_record_id)")
        rows, err = probe(name, lambda table=table, filters=filters, select=select:
                          public_rows(table, {**filters, "select": select}, 100))
        rows = with_primary_provenance(rows)
        output.append(metric(name, observed=len(rows) if rows is not None else None, expected=None,
                             rows=rows, identity="id",
                             timestamp=max((row.get("retrieved_at") or "" for row in rows or []), default=None),
                             errors=int(bool(err)),
                             scope="public published-data sample; source denominator not yet established",
                             note="Zero real rows is High; fixture/schema coverage is excluded; national recall remains unknown.",
                             required_data=True, now=now))
    output.append(metric("entity_resolution", observed=None, expected=None, errors=0,
                         scope="private resolution_candidates excluded by RLS",
                         note="Public anon role cannot audit private candidate precision; run a privileged offline export separately.", now=now))
    return {
        "generated_at": now.isoformat(), "benchmark_version": 1,
        "read_only": True, "sample_uniform_numbers": [item[0] for item in SAMPLE],
        "judicial_sync": {key: sync.get(key) for key in
                          ("last_attempt", "last_sync", "judicial_status",
                           "judicial_fetched", "judicial_failed", "judicial_pending",
                           "judicial_progress", "judicial_window")},
        "judicial_upstream_unavailable": [
            {key: item.get(key) for key in
             ("jid", "classification", "http_status", "error_type", "request",
              "response_error_hash", "failure_runs", "first_seen", "last_seen",
              "jlist_metadata", "provenance")}
            for item in upstream_unavailable
        ],
        "judicial_window_quality": judicial_window_quality,
        "judicial_service_closed": service_closed,
        "judicial_failures": [
            {key: item.get(key) for key in
             ("jid", "http_status", "error_type", "request", "attempts", "elapsed_ms")}
            for item in sync.get("errors") or [] if item.get("source") == "judicial" and item.get("jid")
        ][:20],
        "metrics": [{**item, "severity": severity(item)} for item in output],
    }


def markdown(report, db_audit=None):
    def fmt(value):
        return "unknown" if value is None else str(value)

    target_url, _ = public_supabase_config()
    audit_note = None
    if db_audit:
        target_ref = (urllib.parse.urlsplit(target_url).hostname or '').split('.')[0]
        report_time = datetime.fromisoformat(report['generated_at'].replace('Z', '+00:00'))
        audit_age = age_hours(db_audit.get('audited_at'), report_time)
        if db_audit.get('project_ref') != target_ref or audit_age is None or audit_age > 24:
            audit_note = ("Database cross-check excluded from current findings: its target differs "
                          "from this benchmark or its timestamp is missing/older than 24 hours. "
                          "Refresh the target-specific read-only SQL audit before using all-state counts.")
            db_audit = None
    lines = ["# Data Health — DATA Phase 6", "", f"Generated: {report['generated_at']}",
             f"Benchmark Supabase: {target_url}",
             "", "This is a read-only, fixed-sample benchmark, **not national coverage**.",
             "Unknown values are not zero. Politician coverage uses official `lgno` overlap; contribution and asset denominators remain unknown. Adapter fixtures are excluded.",
             "See [Phase 6 offline acceptance](DATA_PHASE_6_OFFLINE_ACCEPTANCE.md) for sample limits, the post-sync gate, source issues, and checkpoint recovery. Report freshness is not source-publication freshness; JList processing is not national historical recall.",
             "", "| Source | Scope | Observed | Expected | Coverage | Freshness h | Errors | Duplicate | Provenance | Severity |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for item in report["metrics"]:
        lines.append("| " + " | ".join(fmt(item[key]).replace("|", "/") for key in
                     ("source", "scope", "observed", "expected", "coverage", "freshness_hours", "error_count", "duplicate_rate", "provenance_rate", "severity")) + " |")
    high = [item for item in report["metrics"] if item["severity"] == "High"]
    by_source = {item['source']: item for item in report['metrics']}
    political_finding = (
        "- **Contributions/assets:** current public samples contain "
        f"{fmt(by_source.get('political_contributions', {}).get('observed'))} contribution and "
        f"{fmt(by_source.get('asset_declarations', {}).get('observed'))} asset row(s). "
        "These are bounded public reads; national denominators and unpublished draft counts remain unknown. "
        "This probe does not re-audit private identity crosswalks or infer matching accuracy from row counts.")
    judicial_sync = report.get("judicial_sync") or {}
    judicial_window = judicial_sync.get("judicial_window") or {}
    judicial_progress = judicial_sync.get("judicial_progress") or {}
    judicial_failures = report.get("judicial_failures") or []
    judicial_unavailable = report.get("judicial_upstream_unavailable") or []
    judicial_service_closed = report.get("judicial_service_closed", False)
    judicial_quality = report.get("judicial_window_quality") or {}
    window_complete = (judicial_progress.get("total_batches", 0) > 0 and
                       judicial_progress.get("completed_batches") == judicial_progress.get("total_batches") and
                       judicial_quality.get("pending_jids") == 0)
    document_count = (f"{fmt(judicial_quality.get('ingested_jids'))} documents ingested across the window"
                      if window_complete else
                      f"{judicial_sync.get('judicial_fetched') or 0} documents fetched, "
                      f"{judicial_sync.get('judicial_failed') or 0} document failures")
    judicial_finding = (
        "- **Judiciary:** latest local official JList/JDoc attempt "
        f"{judicial_sync.get('last_attempt') or 'unknown'}: status "
        f"{judicial_sync.get('judicial_status') or 'unknown'}, "
        f"{document_count}; "
        f"{judicial_sync.get('judicial_pending') or 0} pending retries; "
        f"{len(judicial_unavailable)} verified upstream-unavailable documents; "
        f"{next((item['error_count'] for item in report['metrics'] if item['source'] == 'judiciary'), 0)} T.E.I. ingestion errors; "
        f"{judicial_progress.get('completed_batches', 0)}/"
        f"{judicial_progress.get('total_batches', 0)} JList batches complete "
        f"({fmt(judicial_quality.get('attempted_batches'))} attempted; "
        f"latest batch {judicial_window.get('batch_index', 'unknown')}, "
        f"{judicial_window.get('total') or judicial_quality.get('jlist_total') or 'unknown'} changed JIDs). "
        + ("The completed window has source-side document gaps; it is not complete JDoc coverage or national historical recall."
           if window_complete else
           "A failed or partial window is not a clean sync and cannot replace the last usable index.")
    )
    lines.extend(["", "## Findings and disposition", "",
                  f"- **Data-quality benchmark gate:** High = {len(high)}; " +
                  (", ".join(item["source"] for item in high) if high else "none") +
                  ". This does not clear operational freshness, security, capacity or deployment gates.",
                  "- **Politician master data:** the current official term-11 `lgno` overlap is "
                  f"{fmt(by_source.get('politicians', {}).get('observed'))}/"
                  f"{fmt(by_source.get('politicians', {}).get('expected'))}. "
                  "This measures the stated public sample; it does not establish national coverage or private draft counts.",
                  political_finding,
                  judicial_finding,
                  "- **Provenance/unknowns:** labor samples verify raw-row hashes against official snapshot metadata; this does not prove retention of older CSV bytes or canonical company identity. Procurement mirror provenance is not independent official notice confirmation. Private resolution candidates remain hidden by RLS, so live precision/recall is unknown.",
                  ""])
    if audit_note:
        lines.extend([audit_note, ""])
    if judicial_service_closed:
        lines.extend(["- **Source service hours:** the latest official `/Auth` response said the API was outside its service window. The [Judicial Yuan API specification](https://opendata.judicial.gov.tw/api/Newses/42/file) limits access to 00:00–06:00 Asia/Taipei. The fixed JList snapshot and checkpoint are preserved; this is source availability, not a credential failure or a successful ingestion.", ""])
    if judicial_quality:
        lines.extend(["### Judicial JList window coverage (not national historical recall)", "",
                      f"- Attempted: {fmt(judicial_quality.get('attempted_jids'))}/{fmt(judicial_quality.get('jlist_total'))} JIDs "
                      f"({fmt(judicial_quality.get('jlist_processing_coverage'))}); "
                      f"ingested {fmt(judicial_quality.get('ingested_jids'))}, "
                      f"pending ingestion {fmt(judicial_quality.get('pending_jids'))}, "
                      f"verified upstream unavailable {fmt(judicial_quality.get('upstream_unavailable_jids'))}.",
                      f"- Ingestion failure rate: {fmt(judicial_quality.get('ingestion_failure_rate'))}; "
                      f"upstream-unavailable rate: {fmt(judicial_quality.get('upstream_unavailable_rate'))}; "
                      f"latest attempt age: {fmt(judicial_quality.get('last_attempt_age_hours'))} h.",
                      "These ratios use only this fixed JList window and never stand in for all historical judgments.", ""])
    if judicial_failures:
        lines.extend(["### Judicial failed-document diagnostics (no credentials)", "",
                      "All listed failures are public JIDs. `POST /JDoc` requests use an in-memory token that is never recorded. HTTP 200 with `upstream_document_error` means the API returned a JSON document error, not a rate limit or transport timeout.",
                      "", "| JID | HTTP | Type | Method/path | Attempts | Elapsed ms |",
                      "|---|---:|---|---|---:|---:|"])
        for item in judicial_failures:
            request = item.get("request") or {}
            lines.append("| " + " | ".join(str(value).replace("|", "/") for value in (
                item.get("jid"), item.get("http_status"), item.get("error_type"),
                f"{request.get('method')} {request.get('endpoint')}",
                item.get("attempts"), item.get("elapsed_ms"))) + " |")
        lines.append("")
    if judicial_unavailable:
        lines.extend(["### Verified upstream document unavailable (not T.E.I. ingestion failure)", "",
                      "These public JIDs stayed in the official JList but JDoc returned the same HTTP 200 document error across separate bounded runs. They are excluded from case-content Evidence and remain recheckable; source metadata and error fingerprints are retained. This does not establish national judiciary coverage.",
                      "", "| JID | List date | Error | Runs | First seen | Last seen | Source |",
                      "|---|---|---|---:|---|---|---|"])
        for item in judicial_unavailable:
            metadata = item.get("jlist_metadata") or {}
            provenance = item.get("provenance") or {}
            lines.append("| " + " | ".join(str(value).replace("|", "/") for value in (
                item.get("jid"), metadata.get("list_date"), item.get("error_type"),
                item.get("failure_runs"), item.get("first_seen"), item.get("last_seen"),
                provenance.get("source_url"))) + " |")
        lines.append("")
    if db_audit:
        lines.extend(["## Privileged, read-only database cross-check", "",
                      f"Audited: {db_audit['audited_at']} against {db_audit['project_ref']}; this is a separate snapshot, not refreshed by the public benchmark.",
                      "All publication states were counted using equivalent read-only SQL:", ""])
        for name, count in db_audit["all_states_counts"].items():
            lines.append(f"- `{name}`: {count} record(s) across all states.")
        if db_audit.get("migration_count") is not None:
            lines.extend([f"- Corporate contribution Evidence, unresolved draft: {db_audit.get('unmatched_corporate_contribution_evidence_draft', 'unknown; not counted in this audit')}.",
                          f"- Published terms/contributions/assets: {db_audit['published_counts']['politician_terms']}/"
                          f"{db_audit['published_counts']['political_contributions']}/"
                          f"{db_audit['published_counts']['asset_declarations']}.",
                          "", f"Migrations: {db_audit['migration_count']}; public tables with RLS: "
                          f"{db_audit['rls_tables']}/{db_audit['public_tables']}; "
                          f"public indexes: {db_audit['public_indexes']}.",
                          f"Preview Supabase override configured for new deployments: "
                          f"{db_audit.get('preview_supabase_override_configured', 'unknown; verify deployment separately')}. "
                          "Existing Preview deployments may still use prior settings. "
                          "Production data was not copied or modified.", ""])
        else:
            lines.extend(["", "DATA Phase 1–4 migrations absent from that database: " +
                          ", ".join(db_audit["missing_migration_versions"]) + ".",
                          "The master/contribution ingestion entrypoints are absent; the older asset entrypoint exists. Anon RLS is publication-filtered but cannot explain zero rows across all states.",
                          "Preview has no Supabase override in Vercel environment variables and falls back to this same public project. Therefore Preview cannot gain independent data without an isolated database.", ""])
        judicial = db_audit.get("judicial_latest_attempt")
        if judicial:
            lines.extend(["## Previous GitHub judiciary sync", "",
                          f"[GitHub Actions run]({judicial['run_url']}): {judicial['outcome']}; "
                          f"{judicial['fetched_before_failure']} documents read before failure. "
                          f"Cause: {judicial['reason']}. No Production data was written.",
                          "The connector now uses bounded JDoc batches, per-request timeout/retry, persisted window progress, and per-source failures. A failed or partial window cannot replace the last usable index; source-side gaps remain High until a clean verified run.", ""])
    lines.extend(["## Reproduce and rollback", "",
                  "Set `TEI_ENTITY_SUPABASE_URL` and `TEI_ENTITY_ANON_KEY` to the Development project's public values, then run `python scripts/data_health.py --json reports/data_health.json --markdown docs/DATA_HEALTH.md --db-audit reports/data_health_db_audit_development.json`. Refresh the audit JSON using read-only `scripts/data_health_remote.sql` before comparing all-state counts. Never use Production credentials for this Development benchmark.", ""])
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
