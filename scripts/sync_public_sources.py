#!/usr/bin/env python3
"""Incrementally ingest public evidence in CI.

Public open-data rows are content-addressed by evidence_id. Judicial records
use the official 7-day change feed; 165 and penalty datasets are re-read and
then de-duplicated by deterministic evidence IDs. The raw datasets are never
committed.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sources.public_records import evidence_rows as public_rows  # noqa: E402
from src.sources.judicial import evidence_rows as judicial_rows  # noqa: E402

OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)
EVIDENCE = OUT / "public_evidence.jsonl"
STATE = OUT / "public_sync_state.json"
STATUS = OUT / "public_sync_status.json"


def load_state() -> Dict[str, Any]:
    if not STATE.exists():
        return {"evidence_ids": [], "last_sync": None}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"evidence_ids": [], "last_sync": None}


def consume(loader, existing, seen, counters, source_label):
    try:
        for row in loader():
            counters["fetched"] += 1
            counters["by_source"].setdefault(source_label, 0)
            counters["by_source"][source_label] += 1
            eid = row["evidence_id"]
            if eid not in existing:
                counters["new"] += 1
            else:
                counters["seen_again"] += 1
            existing[eid] = row
            seen.add(eid)
    except Exception as exc:
        counters["errors"].append({"source": source_label, "error": str(exc)})


def main() -> int:
    state = load_state()
    seen = set(state.get("evidence_ids", []))
    existing: Dict[str, Dict[str, Any]] = {}
    if EVIDENCE.exists():
        for line in EVIDENCE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["evidence_id"]] = row

    counters = {"fetched": 0, "new": 0, "seen_again": 0, "errors": [], "by_source": {}}
    consume(public_rows, existing, seen, counters, "government_open_data")

    # Judicial API is credential-protected; run only when GitHub Secrets exist.
    if os.environ.get("JUDICIAL_USER") and os.environ.get("JUDICIAL_PASSWORD"):
        consume(judicial_rows, existing, seen, counters, "judicial")
    else:
        counters["errors"].append({"source": "judicial", "error": "JUDICIAL_USER/JUDICIAL_PASSWORD not configured"})

    with EVIDENCE.open("w", encoding="utf-8") as fh:
        for eid in sorted(existing):
            fh.write(json.dumps(existing[eid], ensure_ascii=False, sort_keys=True) + "\n")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    state = {
        "last_sync": now,
        "evidence_count": len(existing),
        "last_run_fetched": counters["fetched"],
        "last_run_new": counters["new"],
        "last_run_seen_again": counters["seen_again"],
        "evidence_ids": sorted(seen),
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    status = {
        "last_sync": now,
        "evidence_count": len(existing),
        "new": counters["new"],
        "fetched": counters["fetched"],
        "by_source": counters["by_source"],
        "errors": counters["errors"],
        "judicial_enabled": bool(os.environ.get("JUDICIAL_USER") and os.environ.get("JUDICIAL_PASSWORD")),
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
