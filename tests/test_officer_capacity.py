import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.sync_moea_officers_dev import capacity_plan, require_index_capacity


class OfficerCapacityTests(unittest.TestCase):
    def test_large_bulk_index_stops_before_exhausting_free_budget(self):
        plan = capacity_plan(475196563, 30_000_000, 100_000)
        self.assertFalse(plan['allowed'])
        self.assertGreater(plan['estimated_growth_bytes'], 0)
        self.assertTrue(capacity_plan(100_000, 10_000, 10)['allowed'])
        self.assertFalse(capacity_plan(480_000_000, 0, 0)['allowed'])
        with self.assertRaises(ValueError):
            capacity_plan(0, -1, 0)

    def test_capacity_probe_failure_stops_instead_of_assuming_zero_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder) / 'stage.csv'
            stage.write_text('official data')
            with patch('scripts.sync_moea_officers_dev.database_environment', return_value={}), \
                 patch('scripts.sync_moea_officers_dev.subprocess.run',
                       return_value=SimpleNamespace(returncode=1, stdout='')):
                with self.assertRaisesRegex(RuntimeError, 'probe failed'):
                    require_index_capacity(stage, 1000)

    def test_rejected_budget_never_reaches_archive_or_index(self):
        from scripts import sync_moea_officers_dev as sync
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'official.csv'
            source.write_text('official source')
            with patch('sys.argv', ['sync', '--file', str(source), '--apply', '--confirm-capacity']), \
                 patch.object(sync, 'prepare', return_value=('a' * 64, 1000, 0)), \
                 patch.object(sync, 'database_environment', return_value={}), \
                 patch.object(sync, 'require_index_capacity', side_effect=RuntimeError('capacity guard')), \
                 patch.object(sync, 'archive') as archive, patch.object(sync, 'index') as index:
                with self.assertRaisesRegex(RuntimeError, 'capacity guard'):
                    sync.main()
                archive.assert_not_called()
                index.assert_not_called()


if __name__ == '__main__':
    unittest.main()
