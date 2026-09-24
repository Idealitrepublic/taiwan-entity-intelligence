#!/usr/bin/env python3
"""Read-only Phase 6 release gate over a completed sync and fresh Data Health JSON.

Refresh Data Health separately after the official source sync. This command
never calls any source API or mutates the saved snapshot/checkpoint.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.sync_judicial_window import inspect_checkpoint  # noqa: E402
from scripts import sync_public_sources as sync  # noqa: E402
from src.data_health import SOURCES  # noqa: E402


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (AttributeError, ValueError):
        return None


def evaluate(health, *, now=None, max_report_age_hours=24):
    now = now or datetime.now(timezone.utc)
    checkpoint = inspect_checkpoint()
    state = json.loads(sync.STATE.read_text(encoding="utf-8"))
    snapshot = json.loads(sync.JUDICIAL_SNAPSHOT.read_text(encoding="utf-8"))
    issues = []
    if checkpoint["completed_batches"] != checkpoint["total_batches"]:
        issues.append("JList batches incomplete")
    if checkpoint["attempted_batches"] != checkpoint["total_batches"]:
        issues.append("JList batch statistics incomplete")
    if checkpoint["pending_jids"]:
        issues.append("JDoc retries pending")
    if checkpoint["ingested_jids"] + checkpoint["upstream_unavailable_jids"] != checkpoint["jlist_jids"]:
        issues.append("JList JIDs not fully accounted for")

    by_jid = {}
    duplicates = 0
    incomplete = 0
    snapshot_jids = set(snapshot["jids"])
    with sync.EVIDENCE.open(encoding="utf-8") as records:
        for line in records:
            if not line.strip():
                continue
            row = json.loads(line)
            source = row.get("source") or {}
            jid = source.get("record_id")
            if source.get("type") != "judicial" or jid not in snapshot_jids:
                continue
            if row.get("evidence_id") in by_jid.setdefault(jid, set()):
                duplicates += 1
            by_jid[jid].add(row.get("evidence_id"))
            if not (row.get("evidence_id") and jid and source.get("name") and
                    str(source.get("url") or "").startswith("https://") and
                    source.get("content_hash") and _timestamp(row.get("retrieved_at")) and
                    row.get("fact", {}).get("type") and row.get("raw")):
                incomplete += 1
    batch_size = (state.get("judicial_progress") or {}).get("batch_size")
    stats = state.get("judicial_batch_stats") or {}
    attempted = ({jid for index in stats for jid in
                  snapshot["jids"][int(index) * batch_size:(int(index) + 1) * batch_size]}
                 if batch_size and stats else snapshot_jids if checkpoint["attempted_batches"] == checkpoint["total_batches"]
                 else set())
    ingested = attempted - set(state.get("judicial_pending") or {}) - \
        set(state.get("judicial_source_unavailable") or {})
    missing = len(ingested - set(by_jid))
    if missing or incomplete:
        issues.append("Judicial Evidence or provenance incomplete")
    if duplicates:
        issues.append("Duplicate judicial Evidence IDs")

    generated = _timestamp(health.get("generated_at"))
    last_attempt = _timestamp(state.get("last_attempt"))
    if (not generated or (now - generated).total_seconds() > max_report_age_hours * 3600 or
            last_attempt and generated < last_attempt):
        issues.append("Data Health report stale or predates latest sync")
    metrics = health.get("metrics") or []
    if len(metrics) != len(SOURCES) or {item.get("source") for item in metrics} != set(SOURCES):
        issues.append("Data Health source metrics missing or duplicated")
    if any(item.get("severity") == "High" for item in metrics):
        issues.append("Data Health High severity remains")
    quality = health.get("judicial_window_quality") or {}
    if (quality.get("jlist_total") != checkpoint["jlist_jids"] or
            quality.get("completed_batches") != checkpoint["completed_batches"] or
            quality.get("pending_jids") != checkpoint["pending_jids"] or
            quality.get("ingested_jids") != checkpoint["ingested_jids"] or
            quality.get("upstream_unavailable_jids") != checkpoint["upstream_unavailable_jids"]):
        issues.append("Data Health judicial metrics disagree with checkpoint")
    source_quality = {item["source"]: {key: item.get(key) for key in
                      ("coverage", "freshness_hours", "duplicate_rate", "provenance_rate", "severity")}
                      for item in metrics if item.get("source") in SOURCES}
    review_required = sorted(name for name, item in source_quality.items()
                             if item["coverage"] is None or item["freshness_hours"] is None or
                             item["provenance_rate"] is None or item["provenance_rate"] < 1 or
                             item["duplicate_rate"] not in (None, 0))
    return {"accepted": not issues, "issues": issues, "checkpoint": checkpoint,
            "evidence": {"distinct_jids": len(by_jid), "missing_jids": missing,
                         "duplicate_evidence_ids": duplicates, "incomplete_rows": incomplete},
            "high_count": sum(item.get("severity") == "High" for item in metrics),
            "source_quality": source_quality, "review_required": review_required,
            "report_generated_at": health.get("generated_at")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-json", type=Path, default=ROOT / "reports/data_health.json")
    parser.add_argument("--refresh-health", action="store_true",
                        help="After completed sync only, refresh Development Data Health before gate")
    args = parser.parse_args()
    if args.refresh_health:
        checkpoint = inspect_checkpoint()
        if (checkpoint["completed_batches"] != checkpoint["total_batches"] or
                checkpoint["pending_jids"] or
                checkpoint["attempted_batches"] != checkpoint["total_batches"]):
            print(json.dumps({"accepted": False, "issues": ["Judicial sync incomplete; Data Health not refreshed"]},
                             ensure_ascii=False))
            return 1
        if (os.environ.get("TEI_ENTITY_SUPABASE_URL", "").rstrip("/") !=
                "https://canqjiokrtcxkwblhmml.supabase.co" or
                not os.environ.get("TEI_ENTITY_ANON_KEY")):
            parser.error("Development Supabase URL and public key must be explicitly configured")
        subprocess.run([sys.executable, str(ROOT / "scripts/data_health.py"),
                        "--json", str(args.health_json),
                        "--markdown", str(ROOT / "docs/DATA_HEALTH.md"),
                        "--db-audit", str(ROOT / "reports/data_health_db_audit_development.json")],
                       cwd=ROOT, check=True)
    result = evaluate(json.loads(args.health_json.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
