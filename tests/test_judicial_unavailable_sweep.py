import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import recheck_judicial_unavailable as sweep


class JudicialUnavailableSweepTests(unittest.TestCase):
    def setUp(self):
        self.state = {'judicial_progress': {'window_id': 'window'},
                      'judicial_source_unavailable': {str(i): {'failure_runs': 2} for i in range(6)},
                      'judicial_pending': {}}
        self.selected = []

    def execute(self, args, *, emit_status, **kwargs):
        selected = kwargs.get('unavailable_selection') or kwargs.get('retry_selection')
        self.selected.extend(selected)
        for jid in selected:
            self.state['judicial_source_unavailable'][jid]['failure_runs'] += 1
        return 0

    def test_frozen_sweep_resumes_past_persistently_unavailable_first_batch(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sweep, 'inspect_checkpoint'), \
                patch.object(sweep, 'in_service_window', return_value=True), \
                patch.object(sweep.sync, 'load_state', side_effect=lambda: copy.deepcopy(self.state)), \
                patch.object(sweep.sync, 'main', side_effect=self.execute), \
                patch.dict(sweep.os.environ, JUDICIAL_USER='not-a-secret', JUDICIAL_PASSWORD='not-a-secret'):
            journal = Path(directory) / 'journal.json'
            first = sweep.run_sweep(journal, batch_size=2, max_batches=1)
            self.assertEqual(first['completed'], 2)
            second = sweep.run_sweep(journal, batch_size=2)
            self.assertEqual(second['remaining'], 0)
            self.assertEqual(self.selected, list('012345'))
            self.assertEqual(json.loads(journal.read_text())['completed_jids'], list('012345'))

    def test_check_only_and_closed_window_never_call_api_or_write_journal(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sweep, 'inspect_checkpoint'), \
                patch.object(sweep, 'in_service_window', return_value=False), \
                patch.object(sweep.sync, 'load_state', return_value=self.state), \
                patch.object(sweep.sync, 'main', side_effect=AssertionError('API called')):
            journal = Path(directory) / 'journal.json'
            self.assertEqual(sweep.run_sweep(journal, check_only=True)['remaining'], 6)
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                sweep.run_sweep(journal)
            self.assertFalse(journal.exists())

    def test_new_snapshot_cannot_reuse_prior_completed_journal(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sweep, 'inspect_checkpoint'), \
                patch.object(sweep.sync, 'load_state', return_value=self.state):
            journal = Path(directory) / 'journal.json'
            journal.write_text(json.dumps({'window_id': 'old', 'jids': ['0'], 'completed_jids': ['0']}))
            with self.assertRaisesRegex(RuntimeError, 'different snapshot'):
                sweep.run_sweep(journal, check_only=True)


if __name__ == '__main__':
    unittest.main()
