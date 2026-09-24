#!/usr/bin/env python3
"""Incrementally ingest public evidence in CI.

Public open-data rows are content-addressed by evidence_id. Judicial records
use the official 7-day change feed; 165 and penalty datasets are re-read and
then de-duplicated by deterministic evidence IDs. The raw datasets are never
committed.
"""

import json
import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sources.public_records import evidence_rows as public_rows  # noqa: E402
from src.sources.judicial import evidence_rows as judicial_rows  # noqa: E402
from src.sources.judicial import JudicialRequestError  # noqa: E402
from src.sources.judicial_index import build_index  # noqa: E402

OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)
EVIDENCE = OUT / "public_evidence.jsonl"
STATE = OUT / "public_sync_state.json"
STATUS = OUT / "public_sync_status.json"
JUDICIAL_INDEX = OUT / "judicial_company_index.json"
JUDICIAL_SNAPSHOT = OUT / "judicial_jlist_snapshot.json"


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
        if source_label == "judicial" and isinstance(exc, JudicialRequestError):
            counters["errors"].append({"source": source_label, **exc.diagnostic})
        else:
            counters["errors"].append({"source": source_label, "error_type": type(exc).__name__,
                                       "error": str(exc) if source_label != "judicial" else "judicial_source_error"})


def should_publish_judicial_index(judicial_status: str) -> bool:
    """Never replace the last usable index with a partial/failed JList window."""
    return judicial_status in ("ok", "upstream_unavailable")


def verified_upstream_document_error(previous, detail, jlist_metadata) -> bool:
    """Require independent matching official responses; never infer from case type."""
    return bool(detail.get("error_type") == "upstream_document_error" and
                detail.get("http_status") == 200 and
                detail.get("response_error_hash") and
                detail.get("response_error_hash") == previous.get("response_error_hash") and
                jlist_metadata and
                int(previous.get("failure_runs") or 0) >= 1)


def main(argv=None, *, emit_status=True, retry_selection=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("all", "government", "judicial"), default="all")
    parser.add_argument("--judicial-batch-index", type=int, default=0)
    parser.add_argument("--judicial-batch-size", type=int, default=200)
    parser.add_argument("--judicial-workers", type=int, default=1)
    parser.add_argument("--judicial-retry-failed", action="store_true")
    parser.add_argument("--judicial-recheck-unavailable", action="store_true")
    parser.add_argument("--judicial-snapshot", action="store_true")
    args = parser.parse_args(argv)
    if (args.judicial_retry_failed or args.judicial_recheck_unavailable) and args.source != "judicial":
        parser.error("judicial retry/recheck requires --source judicial")
    if args.judicial_retry_failed and args.judicial_recheck_unavailable:
        parser.error("choose retry-failed or recheck-unavailable")
    if args.judicial_snapshot and (args.source != "judicial" or args.judicial_retry_failed or
                                   args.judicial_recheck_unavailable):
        parser.error("--judicial-snapshot requires ordinary judicial batch mode")
    if retry_selection is not None and not args.judicial_retry_failed:
        parser.error("retry_selection requires --judicial-retry-failed")
    state = load_state()
    snapshot_jids = None
    snapshot_window = None
    if args.judicial_snapshot:
        snapshot = json.loads(JUDICIAL_SNAPSHOT.read_text(encoding="utf-8"))
        progress = state.get("judicial_progress") or {}
        if progress.get("window_id") != snapshot.get("window_id") or progress.get("batch_size") != args.judicial_batch_size:
            parser.error("snapshot does not match persisted judicial progress")
        all_jids = snapshot["jids"]
        start = args.judicial_batch_index * args.judicial_batch_size
        snapshot_jids = all_jids[start:start + args.judicial_batch_size]
        snapshot_window = {"total": len(all_jids), "window_id": snapshot["window_id"],
                           "batch_index": args.judicial_batch_index,
                           "batch_size": args.judicial_batch_size,
                           "remaining": max(0, len(all_jids) - start - len(snapshot_jids)),
                           "selected_metadata": {jid: snapshot["metadata"].get(jid)
                                                 for jid in snapshot_jids}}
    seen = set(state.get("evidence_ids", []))
    existing: Dict[str, Dict[str, Any]] = {}
    if EVIDENCE.exists():
        for line in EVIDENCE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["evidence_id"]] = row

    counters = {"fetched": 0, "new": 0, "seen_again": 0, "errors": [], "by_source": {},
                "judicial_failed": 0}
    if args.source in ("all", "government"):
        def record_public_error(source, exc):
            if sum(item["source"] == "government_open_data" for item in counters["errors"]) < 20:
                counters["errors"].append({"source": "government_open_data",
                                           "dataset": source, "error": str(exc)})

        consume(lambda: public_rows(on_error=record_public_error), existing, seen,
                counters, "government_open_data")

    # Only public JIDs and sanitized metadata enter the persisted retry queue.
    pending = dict(state.get("judicial_pending") or {})
    unavailable = dict(state.get("judicial_source_unavailable") or {})
    if not pending:
        for item in (state.get("source_errors") or {}).get("judicial") or []:
            if item.get("jid"):
                pending[item["jid"]] = {"source": "judicial", "jid": item["jid"],
                                        "error_type": "prior_unclassified",
                                        "http_status": None,
                                        "request": {"method": "POST", "endpoint": "/JDoc"},
                                        "attempts": None,
                                        "batch_index": 0}
    if retry_selection is not None:
        retry_jids = list(retry_selection)
        if len(retry_jids) != len(set(retry_jids)) or len(retry_jids) > args.judicial_batch_size or \
                any(jid not in pending for jid in retry_jids):
            parser.error("retry_selection must be a unique bounded subset of pending JIDs")
    else:
        retry_jids = (sorted(pending)[:args.judicial_batch_size] if args.judicial_retry_failed else
                      sorted(unavailable)[:args.judicial_batch_size] if args.judicial_recheck_unavailable else None)
    retry_metadata = None
    if retry_jids is not None and JUDICIAL_SNAPSHOT.exists():
        saved = json.loads(JUDICIAL_SNAPSHOT.read_text(encoding="utf-8"))
        progress = state.get("judicial_progress") or {}
        if saved.get("window_id") == progress.get("window_id"):
            retry_metadata = {jid: saved.get("metadata", {}).get(jid) for jid in retry_jids}
            if any(not value for value in retry_metadata.values()):
                parser.error("retry JID missing from fixed JList snapshot")
    window = {}
    if args.source in ("all", "judicial") and os.environ.get("JUDICIAL_USER") and os.environ.get("JUDICIAL_PASSWORD"):
        def record_judicial_error(jid, exc):
            counters["judicial_failed"] += 1
            detail = (exc.diagnostic if isinstance(exc, JudicialRequestError) else
                      {"error_type": type(exc).__name__, "http_status": None,
                       "request": {"method": "POST", "endpoint": "/JDoc"},
                       "attempts": 1})
            previous = pending.get(jid) or unavailable.get(jid) or {}
            observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            jlist_metadata = (window.get("selected_metadata") or {}).get(jid) or previous.get("jlist_metadata")
            same_official_error = verified_upstream_document_error(previous, detail, jlist_metadata)
            item = {"source": "judicial", "jid": jid, **detail,
                    "batch_index": previous.get("batch_index", args.judicial_batch_index),
                    "jlist_metadata": jlist_metadata,
                    "first_seen": previous.get("first_seen") or observed_at,
                    "last_seen": observed_at,
                    "failure_runs": int(previous.get("failure_runs") or 0) + 1}
            if same_official_error:
                item["classification"] = "permanent-source-error"
                item["provenance"] = {"source_name": "Judicial Yuan JList/JDoc",
                                       "source_url": jlist_metadata["source_url"],
                                       "retrieved_at": observed_at}
                unavailable[jid] = item
                pending.pop(jid, None)
            else:
                pending[jid] = item
                unavailable.pop(jid, None)
                if sum(error["source"] == "judicial" for error in counters["errors"]) < 20:
                    counters["errors"].append(item)

        def record_judicial_success(jid):
            pending.pop(jid, None)
            unavailable.pop(jid, None)

        consume(lambda: judicial_rows(on_error=record_judicial_error,
                                      batch_index=args.judicial_batch_index,
                                      batch_size=args.judicial_batch_size,
                                      on_window=window.update,
                                      on_success=record_judicial_success,
                                      workers=args.judicial_workers,
                                      retry_jids=retry_jids,
                                      snapshot_jids=snapshot_jids,
                                      snapshot_window=snapshot_window,
                                      retry_window={"total": (len(saved["jids"]) if retry_metadata is not None else
                                                              (state.get("judicial_progress") or {}).get("total", 0)),
                                                    "window_id": (state.get("judicial_progress") or {}).get("window_id"),
                                                    "batch_size": args.judicial_batch_size,
                                                    "batch_index": args.judicial_batch_index,
                                                    **({"selected_metadata": retry_metadata,
                                                        "snapshot": True} if retry_metadata is not None else {})}
                                      if retry_jids is not None else None), existing, seen,
                counters, "judicial")
    elif args.source in ("all", "judicial"):
        counters["errors"].append({"source": "judicial", "error": "JUDICIAL_USER/JUDICIAL_PASSWORD not configured"})
    if (args.judicial_retry_failed or args.judicial_recheck_unavailable) and not retry_jids:
        counters["errors"].append({"source": "judicial", "error_type": "no_pending_failures"})
    judicial_errors = [item for item in counters["errors"] if item["source"] == "judicial"]
    judicial_count = counters["by_source"].get("judicial", 0)
    progress = state.get("judicial_progress") or {}
    if window.get("window_id"):
        total_batches = (window["total"] + args.judicial_batch_size - 1) // args.judicial_batch_size
        if (retry_jids is None and
                (progress.get("window_id") != window["window_id"] or
                 progress.get("batch_size") != args.judicial_batch_size)):
            progress = {"window_id": window["window_id"], "total": window["total"],
                        "batch_size": args.judicial_batch_size,
                        "total_batches": total_batches, "completed_batches": []}
        if retry_jids is None and args.judicial_batch_index >= total_batches and total_batches:
            counters["errors"].append({"source": "judicial", "error": "batch index exceeds JList window"})
            judicial_errors = [item for item in counters["errors"] if item["source"] == "judicial"]
        elif retry_jids is None and not judicial_errors and window["selected"]:
            progress["completed_batches"] = sorted(set(progress["completed_batches"]) |
                                                   {args.judicial_batch_index})
        elif retry_jids is not None and not judicial_errors and retry_jids:
            batch_indexes = {item.get("batch_index") for jid, item in
                             {**(state.get("judicial_pending") or {}),
                              **(state.get("judicial_source_unavailable") or {})}.items()
                             if jid in retry_jids}
            if not batch_indexes:
                batch_indexes = {0}
            for batch_index in batch_indexes:
                if not any(item.get("batch_index") == batch_index for item in pending.values()):
                    progress["completed_batches"] = sorted(set(progress.get("completed_batches", [])) |
                                                           {batch_index})
    judicial_status = (state.get("last_judicial_status", "not_run") if args.source == "government" else
                       "error" if judicial_errors or pending else
                       "partial" if window.get("total", 0) and
                       len(progress.get("completed_batches", [])) < progress.get("total_batches", 0) else
                       "empty_window" if not window.get("total", 0) else
                       "upstream_unavailable" if unavailable else "ok")

    with EVIDENCE.open("w", encoding="utf-8") as fh:
        for eid in sorted(existing):
            fh.write(json.dumps(existing[eid], ensure_ascii=False, sort_keys=True) + "\n")

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    batch_stats = dict(state.get("judicial_batch_stats") or {})
    if args.source in ("all", "judicial") and window.get("window_id"):
        if retry_jids is None:
            if any(item.get("window_id") != window["window_id"] for item in batch_stats.values()):
                batch_stats = {}
            batch_stats[str(args.judicial_batch_index)] = {
                "window_id": window["window_id"], "selected": window.get("selected", 0),
                "fetched_initial": judicial_count, "failed_initial": counters["judicial_failed"],
                "attempted_at": now,
                "error_types": dict(Counter(item.get("error_type") or "unknown"
                                            for item in counters["errors"] if item.get("jid")))}
        for batch_key, item in batch_stats.items():
            index = int(batch_key)
            item["pending"] = sum(row.get("batch_index") == index for row in pending.values())
            item["upstream_unavailable"] = sum(row.get("batch_index") == index for row in unavailable.values())
            item["recovered"] = max(0, item["selected"] - item["fetched_initial"] -
                                    item["pending"] - item["upstream_unavailable"])
            item["completed"] = index in progress.get("completed_batches", [])
    judicial_totals = {
        "attempted_jids": sum(item["selected"] for item in batch_stats.values()),
        "ingested_jids": sum(item["fetched_initial"] + item.get("recovered", 0)
                             for item in batch_stats.values()),
        "pending_jids": len(pending),
        "upstream_unavailable_jids": len(unavailable),
        "pending_error_types": dict(Counter(item.get("error_type") or "unknown"
                                            for item in pending.values())),
        "upstream_error_types": dict(Counter(item.get("error_type") or "unknown"
                                             for item in unavailable.values())),
    }
    source_errors = dict(state.get("source_errors") or {})
    if args.source in ("all", "government"):
        source_errors["government_open_data"] = [item for item in counters["errors"]
                                                 if item["source"] == "government_open_data"]
    if args.source in ("all", "judicial"):
        source_errors["judicial"] = list(pending.values()) + [item for item in judicial_errors
                                                               if not item.get("jid")]
    all_errors = [item for items in source_errors.values() for item in items]
    state = {
        "last_sync": now if args.source in ("all", "judicial") and
                     not all_errors and should_publish_judicial_index(judicial_status) else state.get("last_sync"),
        "last_attempt": now,
        "evidence_count": len(existing),
        "last_run_fetched": counters["fetched"],
        "last_run_new": counters["new"],
        "last_run_seen_again": counters["seen_again"],
        "evidence_ids": sorted(seen),
        "judicial_progress": progress,
        "judicial_batch_stats": batch_stats,
        "judicial_pending": pending,
        "judicial_source_unavailable": unavailable,
        "last_judicial_status": judicial_status,
        "source_errors": source_errors,
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    status = {
        "last_sync": state["last_sync"],
        "last_attempt": now,
        "evidence_count": len(existing),
        "new": counters["new"],
        "fetched": counters["fetched"],
        "by_source": counters["by_source"],
        "errors": all_errors,
        "judicial_enabled": bool(os.environ.get("JUDICIAL_USER") and os.environ.get("JUDICIAL_PASSWORD")),
        "judicial_status": judicial_status,
        "judicial_fetched": judicial_count,
        "judicial_failed": counters["judicial_failed"],
        "judicial_pending": len(pending),
        "judicial_source_unavailable": list(unavailable.values()),
        "judicial_progress": {"total_batches": progress.get("total_batches", 0),
                              "completed_batches": len(progress.get("completed_batches", []))},
        "judicial_totals": judicial_totals,
        "judicial_window": window,
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    if should_publish_judicial_index(judicial_status):
        JUDICIAL_INDEX.write_text(
            json.dumps(build_index(existing.values(), now), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    if emit_status:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    return 1 if all_errors or (args.source != "government" and
                                      judicial_status in ("error", "partial")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
