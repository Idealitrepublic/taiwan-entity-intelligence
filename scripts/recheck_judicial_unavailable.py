#!/usr/bin/env python3
"""Resume one frozen sweep of official-unavailable JDocs in the service window.

Only failed JIDs are selected. The ignored journal retains completed JIDs even
when the upstream error persists, so the first 25 cannot starve the remaining
queue. Credentials must already be loaded in this child process environment.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import sync_public_sources as sync  # noqa: E402
from scripts.sync_judicial_window import in_service_window, inspect_checkpoint  # noqa: E402
from src.local_artifacts import atomic_json, source_write_lock  # noqa: E402


def run_sweep(journal_path, *, batch_size=25, max_batches=None, check_only=False):
    if not 1 <= batch_size <= 25 or (max_batches is not None and max_batches < 1):
        raise ValueError('Use a batch size of 1..25 and positive max batches')
    inspect_checkpoint()
    state = sync.load_state()
    window_id = state['judicial_progress']['window_id']
    journal = (json.loads(journal_path.read_text()) if journal_path.exists() else
               {'window_id': window_id, 'jids': sorted(state.get('judicial_source_unavailable') or {}),
                'completed_jids': []})
    if (journal.get('window_id') != window_id or
            len(set(journal['jids'])) != len(journal['jids']) or
            len(set(journal['completed_jids'])) != len(journal['completed_jids']) or
            not set(journal['completed_jids']) <= set(journal['jids'])):
        raise RuntimeError('Recheck journal invalid or belongs to a different snapshot; preserve for review')
    remaining = [jid for jid in journal['jids'] if jid not in set(journal['completed_jids'])]
    if check_only:
        return {'total': len(journal['jids']), 'completed': len(journal['completed_jids']),
                'remaining': len(remaining), 'service_window_open': in_service_window()}
    if not in_service_window():
        raise RuntimeError('Official API closed; journal/checkpoint preserved')
    if not (os.environ.get('JUDICIAL_USER') and os.environ.get('JUDICIAL_PASSWORD')):
        raise RuntimeError('Judicial credentials not loaded; values suppressed')
    batches = 0
    while remaining and (max_batches is None or batches < max_batches):
        if not in_service_window():
            break
        chunk = remaining[:batch_size]
        for mode in ('pending', 'unavailable'):
            if not in_service_window():
                break
            state = sync.load_state()
            key = 'judicial_pending' if mode == 'pending' else 'judicial_source_unavailable'
            selected = [jid for jid in chunk if jid in (state.get(key) or {})]
            if not selected:
                continue
            before = state.get(key) or {}
            flag = '--judicial-retry-failed' if mode == 'pending' else '--judicial-recheck-unavailable'
            kwargs = {'retry_selection' if mode == 'pending' else 'unavailable_selection': selected}
            sync.main(['--source', 'judicial', flag, '--judicial-batch-size', str(batch_size),
                       '--judicial-workers', '2'], emit_status=False, **kwargs)
            state = sync.load_state()
            pending = state.get('judicial_pending') or {}
            unavailable = state.get('judicial_source_unavailable') or {}
            # Persist per-JID progress even when another item times out.
            for jid in selected:
                if jid not in pending and (jid not in unavailable or
                        unavailable[jid].get('failure_runs', 0) > before[jid].get('failure_runs', 0)):
                    journal['completed_jids'].append(jid)
            journal['completed_jids'] = sorted(set(journal['completed_jids']))
            atomic_json(journal_path, journal)
        state = sync.load_state()
        unresolved = set(state.get('judicial_pending') or {}) | set(state.get('judicial_source_unavailable') or {})
        journal['completed_jids'] = sorted(set(journal['completed_jids']) | (set(chunk) - unresolved))
        atomic_json(journal_path, journal)
        batches += 1
        print(json.dumps({'rechecked': len(journal['completed_jids']), 'total': len(journal['jids']),
                          'pending': len(state.get('judicial_pending') or {}),
                          'upstream_unavailable': len(state.get('judicial_source_unavailable') or {})}), flush=True)
        remaining = [jid for jid in journal['jids'] if jid not in set(journal['completed_jids'])]
        if set(chunk) & set(remaining):
            break  # transport/unclassified errors retry next invocation, no busy loop
    return {'total': len(journal['jids']), 'completed': len(journal['completed_jids']),
            'remaining': len(remaining), 'service_window_open': in_service_window()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--max-batches', type=int)
    args = parser.parse_args()
    with source_write_lock(sync.STATE.parent):
        result = run_sweep(sync.STATE.parent / 'judicial_unavailable_recheck.json',
                           check_only=args.check_only, max_batches=args.max_batches)
    print(json.dumps(result))
    return 0 if args.check_only or result['remaining'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
