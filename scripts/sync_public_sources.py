#!/usr/bin/env python3
"""Run the public-record ingestion layer in GitHub Actions.

Outputs:
  data/public_evidence.jsonl  - normalized evidence records
  data/public_sync_state.json - lightweight hashes/metadata for incremental sync

The raw public datasets are not committed. The JSONL is a compact evidence
layer and may be configured for artifact-only storage in CI.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "src"
sys.path.insert(0, str(ROOT))

from src.sources.public_records import evidence_rows  # noqa: E402

OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)
EVIDENCE = OUT / "public_evidence.jsonl"
STATE = OUT / "public_sync_state.json"


def load_state() -> Dict[str, Any]:
    if not STATE.exists():
        return {"evidence_ids": [], "last_sync": None}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"evidence_ids": [], "last_sync": None}


def main() -> int:
    state = load_state()
    seen = set(state.get("evidence_ids", []))
    existing: Dict[str, Dict[str, Any]] = {}
    if EVIDENCE.exists():
        for line in EVIDENCE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["evidence_id"]] = row

    fetched = 0
    added = 0
    updated = 0
    for row in evidence_rows():
        fetched += 1
        eid = row["evidence_id"]
        if eid not in existing:
            added += 1
        else:
            updated += 1
        existing[eid] = row
        seen.add(eid)

    # Deterministic ordering makes CI diffs reviewable.
    with EVIDENCE.open("w", encoding="utf-8") as fh:
        for eid in sorted(existing):
            fh.write(json.dumps(existing[eid], ensure_ascii=False, sort_keys=True) + "\n")

    from datetime import datetime, timezone
    state = {
        "last_sync": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "evidence_count": len(existing),
        "last_run_fetched": fetched,
        "last_run_new": added,
        "last_run_seen_again": updated,
        "evidence_ids": sorted(seen),
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "fetched": fetched,
        "new": added,
        "seen_again": updated,
        "total": len(existing),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
