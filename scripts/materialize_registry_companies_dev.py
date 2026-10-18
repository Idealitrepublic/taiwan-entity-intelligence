#!/usr/bin/env python3
"""Resolve every exact-ID donor candidate against the official company registry.

Only tei-development is writable. Name-only labor/judicial mentions and donation
relationships remain unresolved; this publishes registry identity Evidence only.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_graph_coverage_dev import is_development_target  # noqa: E402
from scripts.audit_p0_data_chain import development_environment  # noqa: E402
from src.company_registry_materialization import build_official_registry_identity_bundle  # noqa: E402
from src.entities.repository import MOEA_COMPANY_API  # noqa: E402

STATE_PATH = ROOT / "data/local/registry_company_integration.json"
CANDIDATES_SQL = r"""
select coalesce(jsonb_agg(candidate order by uniform),'[]'::jsonb) from (
  select ev.source_locator->>'donor_uniform_number' as uniform,
    count(distinct regexp_replace(ev.title,'^政治獻金來源紀錄：','')) as labels,
    min(regexp_replace(ev.title,'^政治獻金來源紀錄：','')) as expected_name,
    bool_and(regexp_replace(ev.title,'^政治獻金來源紀錄：','') ~ '(股份有限公司|有限公司)$') as company_form
  from public.evidence_records ev
  where ev.source_name='監察院政治獻金公開查閱平臺'
    and ev.source_locator->>'donor_uniform_number' ~ '^[0-9]{8}$'
  group by ev.source_locator->>'donor_uniform_number'
) candidate;
"""


def psql(sql, env, *, timeout=90):
    result = subprocess.run(["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                            input=sql, text=True, capture_output=True, env=env, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Development database query failed; connection details suppressed")
    return result.stdout.strip()


def candidates(env):
    return json.loads(psql("BEGIN READ ONLY;\n" + CANDIDATES_SQL + "\nROLLBACK;", env))


def official_registry(uniform, *, retries=3, pause=time.sleep):
    url = MOEA_COMPANY_API + "?" + urlencode({
        "$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}", "$top": "1"})
    last_type = "unknown"
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={
                "Accept": "application/json", "User-Agent": "Taiwan-Entity-Intelligence/2.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
            # This official endpoint returns HTTP 200 with an empty body when
            # an identifier is not a company-registration row (e.g. a shop).
            if not raw:
                return None, "official_not_found"
            rows = json.loads(raw.decode("utf-8-sig"))
            if rows == []:
                return None, "official_not_found"
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
                return None, "official_not_unique"
            return rows[0], None
        except urllib.error.HTTPError as exc:
            last_type = f"http_{exc.code}"
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (TimeoutError, OSError, ValueError):
            last_type = "transport_or_json"
        if attempt + 1 < retries:
            pause(min(8, 2 ** attempt))
    return None, last_type


def classify(candidate, registry, retrieved_at):
    if registry is None:
        return "official_unavailable", None
    try:
        bundle = build_official_registry_identity_bundle(
            registry, uniform=candidate["uniform"], retrieved_at=retrieved_at)
    except ValueError:
        return "invalid_registry_record", None
    if candidate["labels"] != 1:
        return "verified_id_conflicting_donor_labels", bundle
    if not candidate["company_form"]:
        return "verified_id_noncompany_donor_label", bundle
    if bundle["entities"][0]["canonical_name"] != candidate["expected_name"]:
        return "verified_id_name_differs", bundle
    if registry.get("Company_Status_Desc") != "核准設立":
        return "verified_id_not_active", bundle
    return "verified", bundle


def merge_bundles(bundles):
    merged = {key: [] for key in ("entities", "identifiers", "evidence", "entity_evidence")}
    for bundle in bundles:
        for key in merged:
            merged[key].extend(bundle[key])
    return merged


def publish(bundles, env):
    if not bundles:
        return
    if len(bundles) > 25:
        raise ValueError("A publication batch is limited to 25 companies")
    payload = json.dumps(merge_bundles(bundles), ensure_ascii=False).replace("'", "''")
    psql("BEGIN; SELECT public.tei_ingest_bundle('" + payload + "'::jsonb); COMMIT;", env)


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2))
    temporary.replace(path)


def run(*, apply, max_candidates=None, state_path=STATE_PATH,
        fetch=official_registry, env=None, pause=time.sleep):
    env = env or development_environment()
    if not is_development_target(env):
        raise RuntimeError("Only tei-development can be used for company integration")
    rows = candidates(env)
    if len(rows) > 1000 or len({row["uniform"] for row in rows}) != len(rows):
        raise RuntimeError("Unexpected or duplicate candidate inventory")
    selected = rows[:max_candidates]
    state = json.loads(state_path.read_text()) if apply and state_path.exists() else {}
    totals = {"candidates": len(rows), "processed": len(selected),
              "deferred": len(rows) - len(selected), "already_integrated": 0, "verified": 0,
              "published": 0, "verification_types": {}, "unresolved": {}, "source_errors": {}}
    pending = []
    pending_keys = []

    def flush():
        if not pending:
            return
        publish(pending, env)
        for uniform, name in pending_keys:
            state[uniform] = {"name": name, "status": "integrated"}
        totals["published"] += len(pending)
        save_state(state_path, state)
        pending.clear()
        pending_keys.clear()

    for row in selected:
        uniform = row["uniform"]
        if apply and state.get(uniform) == {"name": row["expected_name"], "status": "integrated"}:
            totals["already_integrated"] += 1
            continue
        registry, source_error = fetch(uniform)
        if source_error and source_error != "official_not_found":
            totals["source_errors"][source_error] = totals["source_errors"].get(source_error, 0) + 1
        if source_error == "official_not_found":
            status, bundle = "not_in_company_registry", None
        else:
            status, bundle = classify(row, registry, datetime.now(timezone.utc).isoformat())
        pause(0.2)
        if bundle is None:
            totals["unresolved"][status] = totals["unresolved"].get(status, 0) + 1
            continue
        totals["verified"] += 1
        totals["verification_types"][status] = totals["verification_types"].get(status, 0) + 1
        if apply:
            pending.append(bundle)
            pending_keys.append((uniform, row["expected_name"]))
            if len(pending) == 25:
                flush()
    if apply:
        flush()
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Publish verified identities to tei-development")
    parser.add_argument("--max-candidates", type=int, help="Bound this resumable run")
    args = parser.parse_args()
    if args.max_candidates is not None and args.max_candidates < 1:
        parser.error("--max-candidates must be positive")
    print(json.dumps(run(apply=args.apply, max_candidates=args.max_candidates),
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
