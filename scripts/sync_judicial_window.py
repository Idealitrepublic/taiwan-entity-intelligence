#!/usr/bin/env python3
"""Resume a fixed, official JList window with per-batch durable checkpoints.

Credentials come only from the process environment. The snapshot contains
public JIDs/JList metadata and is stored below ignored `data/`; no token or
credential is written. A changed JList never silently resets progress.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sync_public_sources as sync  # noqa: E402
from src.sources.judicial import changed_jids, get_token  # noqa: E402


def in_service_window(now=None):
    # Official specification: https://opendata.judicial.gov.tw/api/Newses/42/file
    local = (now or datetime.now(ZoneInfo("Asia/Taipei"))).astimezone(ZoneInfo("Asia/Taipei"))
    return 0 <= local.hour < 6


def ensure_snapshot():
    if sync.JUDICIAL_SNAPSHOT.exists():
        snapshot = json.loads(sync.JUDICIAL_SNAPSHOT.read_text(encoding="utf-8"))
    else:
        metadata = {}
        jids = changed_jids(get_token(), on_metadata=metadata.update)
        snapshot = {"jids": jids, "metadata": metadata,
                    "window_id": hashlib.sha256("\n".join(jids).encode("utf-8")).hexdigest()}
        progress = (sync.load_state().get("judicial_progress") or {})
        if progress.get("window_id") and progress["window_id"] != snapshot["window_id"]:
            raise RuntimeError("Current JList differs from checkpoint; existing completed batches cannot be reused")
        staging = sync.JUDICIAL_SNAPSHOT.with_suffix(".tmp")
        staging.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        staging.replace(sync.JUDICIAL_SNAPSHOT)
    progress = (sync.load_state().get("judicial_progress") or {})
    if progress.get("window_id") != snapshot["window_id"]:
        raise RuntimeError("JList snapshot does not match checkpoint")
    return snapshot


def inspect_checkpoint():
    """Read-only verification; never fetch JList or credentials."""
    if not sync.JUDICIAL_SNAPSHOT.exists() or not sync.STATE.exists():
        raise RuntimeError("Saved JList snapshot and checkpoint are both required")
    snapshot = json.loads(sync.JUDICIAL_SNAPSHOT.read_text(encoding="utf-8"))
    state = sync.load_state()
    jids = snapshot.get("jids") or []
    progress = state.get("judicial_progress") or {}
    batch_size = progress.get("batch_size")
    if (not jids or len(jids) != len(set(jids)) or
            snapshot.get("window_id") != hashlib.sha256("\n".join(jids).encode("utf-8")).hexdigest() or
            progress.get("window_id") != snapshot.get("window_id") or
            not isinstance(batch_size, int) or batch_size < 1 or
            progress.get("total", len(jids)) != len(jids) or
            progress.get("total_batches") != (len(jids) + batch_size - 1) // batch_size):
        raise RuntimeError("JList snapshot and checkpoint disagree")
    if any(jid not in snapshot.get("metadata", {}) for jid in jids):
        raise RuntimeError("JList metadata is incomplete")
    total = progress["total_batches"]
    completed = progress.get("completed_batches") or []
    if len(completed) != len(set(completed)) or any(not isinstance(i, int) or i < 0 or i >= total for i in completed):
        raise RuntimeError("Completed batch indexes are invalid")
    stats = state.get("judicial_batch_stats") or {}
    if any(int(key) < 0 or int(key) >= total or
           value.get("window_id") != snapshot["window_id"] or
           value.get("selected") != len(jids[int(key) * batch_size:(int(key) + 1) * batch_size]) or
           value.get("completed") != (int(key) in completed) or
           sum(value.get(field, 0) for field in ("fetched_initial", "pending", "upstream_unavailable", "recovered")) != value.get("selected")
           for key, value in stats.items()):
        raise RuntimeError("Per-batch statistics disagree with checkpoint")
    pending = state.get("judicial_pending") or {}
    unavailable = state.get("judicial_source_unavailable") or {}
    if set(pending) & set(unavailable) or not (set(pending) | set(unavailable)) <= set(jids):
        raise RuntimeError("Pending and upstream-unavailable JIDs overlap or lie outside snapshot")
    known = verify_completed(snapshot, batch_size)
    pending_types = Counter(item.get("error_type") or "unknown" for item in pending.values())
    return {"jlist_jids": len(jids), "total_batches": total,
            "attempted_batches": len(stats), "completed_batches": len(completed),
            "ingested_jids": sum(item["fetched_initial"] + item.get("recovered", 0) for item in stats.values()),
            "pending_jids": len(pending), "upstream_unavailable_jids": len(unavailable),
            "completed_evidence_verified": bool(known),
            "pending_error_types": dict(sorted(pending_types.items())),
            "pending_categories": {
                "upstream_document": pending_types.get("upstream_document_error", 0),
                "transport": sum(pending_types.get(kind, 0) for kind in
                                 ("transport_error", "RemoteDisconnected", "ConnectionResetError")),
                "rate_limit": pending_types.get("rate_limit", 0),
                "timeout": pending_types.get("timeout", 0),
                "service_closed": pending_types.get("service_closed", 0)}}


def verify_completed(snapshot, batch_size):
    state = sync.load_state()
    completed = state.get("judicial_progress", {}).get("completed_batches") or []
    known = set(state.get("judicial_source_unavailable") or {})
    if sync.EVIDENCE.exists():
        with sync.EVIDENCE.open(encoding="utf-8") as rows:
            for line in rows:
                if line.strip():
                    source = json.loads(line).get("source") or {}
                    if source.get("type") == "judicial":
                        known.add(source.get("record_id"))
    for batch in completed:
        selected = snapshot["jids"][batch * batch_size:(batch + 1) * batch_size]
        if not set(selected).issubset(known):
            raise RuntimeError(f"Checkpoint batch {batch} lacks saved evidence or upstream-unavailable records")
    return known


def backfill_batch_stats(snapshot, batch_size, known):
    """Recover exact prior completed counts without inventing prior timestamps."""
    state = sync.load_state()
    stats = dict(state.get("judicial_batch_stats") or {})
    unavailable = state.get("judicial_source_unavailable") or {}
    changed = False
    for batch in state.get("judicial_progress", {}).get("completed_batches") or []:
        if str(batch) in stats:
            continue
        selected = snapshot["jids"][batch * batch_size:(batch + 1) * batch_size]
        unavailable_count = sum(jid in unavailable for jid in selected)
        ingested_count = sum(jid in known and jid not in unavailable for jid in selected)
        stats[str(batch)] = {"window_id": snapshot["window_id"], "selected": len(selected),
                             "fetched_initial": ingested_count,
                             "failed_initial": unavailable_count,
                             "attempted_at": None, "backfilled_from_evidence": True,
                             "error_types": {"upstream_document_error": unavailable_count}
                             if unavailable_count else {},
                             "pending": 0, "upstream_unavailable": unavailable_count,
                             "recovered": 0, "completed": True}
        changed = True
    if changed:
        state["judicial_batch_stats"] = stats
        staging = sync.STATE.with_suffix(".tmp")
        staging.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        staging.replace(sync.STATE)


def compact_status(status):
    return {"status": status.get("judicial_status"),
            "fetched": status.get("judicial_fetched"),
            "failed": status.get("judicial_failed"),
            "pending": status.get("judicial_pending"),
            "upstream_unavailable": len(status.get("judicial_source_unavailable") or []),
            "progress": status.get("judicial_progress")}


def batch_already_attempted(batch, state, snapshot, batch_size):
    if batch in set((state.get("judicial_progress") or {}).get("completed_batches") or []):
        return True
    stat = (state.get("judicial_batch_stats") or {}).get(str(batch)) or {}
    expected = len(snapshot["jids"][batch * batch_size:(batch + 1) * batch_size])
    return bool(expected and stat.get("window_id") == snapshot["window_id"] and
                stat.get("selected") == expected)


def run(*, max_batches=None, batch_size=25, workers=3):
    if not in_service_window():
        print("Judicial API closed (Asia/Taipei 06:00–00:00); checkpoint preserved", flush=True)
        return 2
    checkpoint = inspect_checkpoint() if sync.JUDICIAL_SNAPSHOT.exists() else None
    if checkpoint and checkpoint["total_batches"] != (checkpoint["jlist_jids"] + batch_size - 1) // batch_size:
        raise RuntimeError("Requested batch size differs from saved checkpoint")
    snapshot = ensure_snapshot()
    known = verify_completed(snapshot, batch_size)
    backfill_batch_stats(snapshot, batch_size, known)
    total = (len(snapshot["jids"]) + batch_size - 1) // batch_size
    processed = 0
    for batch in range(total):
        if batch_already_attempted(batch, sync.load_state(), snapshot, batch_size):
            continue
        if max_batches is not None and processed >= max_batches:
            break
        sync.main(["--source", "judicial", "--judicial-batch-size", str(batch_size),
                   "--judicial-batch-index", str(batch), "--judicial-workers", str(workers),
                   "--judicial-snapshot"], emit_status=False)
        status = json.loads(sync.STATUS.read_text(encoding="utf-8"))
        processed += 1
        if processed % 10 == 0 or status.get("judicial_failed"):
            print(json.dumps({"batch": batch, **compact_status(status)}, ensure_ascii=False), flush=True)
        current_errors = [item for item in status.get("errors") or [] if item.get("batch_index") == batch]
        if any(item.get("error_type") in {"rate_limit", "timeout", "transport_error", "service_closed"}
               for item in current_errors):
            print("Transient API failure; checkpoint saved for later resume", flush=True)
            return 1
        if not status.get("judicial_window", {}).get("selected"):
            print("No JIDs selected; stopping without advancing checkpoint", flush=True)
            return 1

    # Retry only failed JIDs. Identical JDoc errors can be isolated as an
    # explicit upstream-unavailable record; changing or transport errors stay pending.
    for _ in range(2):
        pending_snapshot = sorted((sync.load_state().get("judicial_pending") or {}).keys())
        pending_before = len(pending_snapshot)
        if not pending_before:
            break
        for start in range(0, pending_before, batch_size):
            selection = [jid for jid in pending_snapshot[start:start + batch_size]
                         if jid in (sync.load_state().get("judicial_pending") or {})]
            if not selection:
                continue
            sync.main(["--source", "judicial", "--judicial-batch-size", str(batch_size),
                       "--judicial-workers", str(workers), "--judicial-retry-failed"],
                      emit_status=False, retry_selection=selection)
            status = json.loads(sync.STATUS.read_text(encoding="utf-8"))
            print(json.dumps({"retry": True, **compact_status(status)}, ensure_ascii=False), flush=True)
            if any(item.get("error_type") in {"rate_limit", "timeout", "transport_error", "service_closed"}
                   and (item.get("jid") in selection or not item.get("jid"))
                   for item in status.get("errors") or []):
                print("Transient API failure during retry; checkpoint saved", flush=True)
                return 1
        if len(sync.load_state().get("judicial_pending") or {}) >= pending_before:
            break

    final = json.loads(sync.STATUS.read_text(encoding="utf-8"))
    print(json.dumps({"final": compact_status(final)}, ensure_ascii=False), flush=True)
    return 0 if final.get("judicial_status") in ("ok", "upstream_unavailable") else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--check-only", action="store_true", help="Validate saved local checkpoint without API access")
    args = parser.parse_args()
    if args.max_batches is not None and args.max_batches < 1:
        parser.error("--max-batches must be positive")
    if not 1 <= args.batch_size <= 500:
        parser.error("--batch-size must be 1..500")
    if not 1 <= args.workers <= 3:
        parser.error("--workers must be 1..3")
    if args.check_only:
        print(json.dumps(inspect_checkpoint(), ensure_ascii=False, sort_keys=True))
        return 0
    return run(max_batches=args.max_batches, batch_size=args.batch_size, workers=args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
