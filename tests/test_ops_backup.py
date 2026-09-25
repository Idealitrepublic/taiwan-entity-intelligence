import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ops_backup


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen") and shutil.which("tar"),
                     "age and tar are required for the local encryption scenario")
class OpsBackupEncryptionTests(unittest.TestCase):
    def test_archive_verification_drains_after_toc_reader_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = root / "identity.txt"
            subprocess.run([shutil.which("age-keygen"), "-o", str(identity)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            recipient = next(line.split(":", 1)[1].strip() for line in identity.read_text().splitlines()
                             if line.startswith("# public key:"))
            encrypted = root / "test.dump.age"
            with encrypted.open("wb") as stream:
                subprocess.run([shutil.which("age"), "-r", recipient], input=b"x" * (4 * 1024 * 1024),
                               stdout=stream, check=True, stderr=subprocess.DEVNULL)
            reader = root / "toc-reader"
            reader.write_text("#!/bin/sh\nhead -c 1 >/dev/null\n", encoding="utf-8")
            reader.chmod(0o700)
            original_executable = ops_backup.executable
            with patch.object(ops_backup, "executable",
                              side_effect=lambda name: str(reader) if name == "pg_restore" else original_executable(name)):
                ops_backup.verify_archive(encrypted, identity)

    def test_sync_bundle_encrypts_and_verifies_without_plaintext_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = root / "identity.txt"
            subprocess.run([shutil.which("age-keygen"), "-o", str(identity)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            identity.chmod(0o600)
            recipient = next(line.split(":", 1)[1].strip() for line in identity.read_text().splitlines()
                             if line.startswith("# public key:"))
            (root / "snapshot.json").write_text('{"jids": ["public-id"]}', encoding="utf-8")
            encrypted = root / "sync-evidence.tar.age"
            with patch.object(ops_backup, "ROOT", root), \
                 patch.object(ops_backup, "SYNC_FILES", ("snapshot.json",)):
                ops_backup.encrypt_sync_bundle(encrypted, recipient,
                                               {"snapshot.json": ops_backup.sha256(root / "snapshot.json")})
                ops_backup.verify_archive(encrypted, identity)
            self.assertGreater(encrypted.stat().st_size, 0)
            self.assertEqual(encrypted.stat().st_mode & 0o077, 0)
            self.assertNotIn(b"public-id", encrypted.read_bytes())
            encrypted.write_bytes(encrypted.read_bytes()[:-8])
            with patch.object(ops_backup, "SYNC_FILES", ("snapshot.json",)):
                with self.assertRaises(RuntimeError):
                    ops_backup.verify_bundle(encrypted, identity)


if __name__ == "__main__":
    unittest.main()
