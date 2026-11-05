"""No partial Evidence publication, silent checkpoint reset or concurrent writer."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.local_artifacts import atomic_json, atomic_text_file, source_write_lock
from scripts import sync_public_sources as sync

ROOT = Path(__file__).resolve().parents[1]


class LocalArtifactTests(unittest.TestCase):
    def test_reader_sees_old_complete_utf8_until_atomic_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.jsonl'
            path.write_text('舊的完整來源\n')
            with atomic_text_file(path) as stream:
                stream.write('新的完整來源\n')
                stream.flush()
                self.assertEqual(path.read_text(), '舊的完整來源\n')
            self.assertEqual(path.read_text(), '新的完整來源\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_interrupted_writer_preserves_old_file_and_removes_staging_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'checkpoint.json'
            atomic_json(path, {'completed': [1, 2]})
            with self.assertRaises(RuntimeError):
                with atomic_text_file(path) as stream:
                    stream.write('incomplete')
                    raise RuntimeError('simulated interruption')
            self.assertEqual(json.loads(path.read_text()), {'completed': [1, 2]})
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_malformed_existing_checkpoint_is_not_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            path.write_text('{incomplete')
            with patch.object(sync, 'STATE', path), self.assertRaisesRegex(RuntimeError, 'refusing to reset'):
                sync.load_state()
            self.assertEqual(path.read_text(), '{incomplete')

    def test_process_lock_is_reentrant_and_rejects_a_second_process(self):
        with tempfile.TemporaryDirectory() as folder:
            code = ('from src.local_artifacts import source_write_lock,SyncAlreadyRunning; '
                    'import sys\ntry:\n with source_write_lock(sys.argv[1]): pass\n'
                    'except SyncAlreadyRunning: sys.exit(3)')
            with source_write_lock(folder), source_write_lock(folder):
                result = subprocess.run([sys.executable, '-c', code, folder], cwd=ROOT,
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 3)
            result = subprocess.run([sys.executable, '-c', code, folder], cwd=ROOT,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
