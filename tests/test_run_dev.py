import os
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

from scripts.run_dev import read_local_env, require_development_public_target


class LocalEnvLoaderTests(unittest.TestCase):
    def test_standalone_launcher_can_import_its_configuration_guard(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/run_dev.py'
        code = (f"import runpy; m=runpy.run_path({str(script)!r},run_name='guard_test'); "
                "m['require_development_public_target']({'TEI_ENTITY_SUPABASE_URL':"
                "'https://canqjiokrtcxkwblhmml.supabase.co','TEI_ENTITY_ANON_KEY':'sb_publishable_test_only'})")
        result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, 'standalone launcher cannot load its guard')

    def test_local_server_requires_explicit_development_public_database(self):
        valid = {"TEI_ENTITY_SUPABASE_URL": "https://canqjiokrtcxkwblhmml.supabase.co",
                 "TEI_ENTITY_ANON_KEY": "sb_publishable_test_only"}
        require_development_public_target(valid)
        for bad in ({}, {**valid, "TEI_ENTITY_SUPABASE_URL": "https://rztdbdurkjfrirsrrhtu.supabase.co"},
                    {**valid, "TEI_ENTITY_ANON_KEY": ""},
                    {**valid, "TEI_ENTITY_ANON_KEY": "sb_secret_fixture"},
                    {**valid, "TEI_PRIVATE_SUPABASE_URL": "https://rztdbdurkjfrirsrrhtu.supabase.co"},
                    {**valid, "TEI_PRIVATE_SUPABASE_URL": valid["TEI_ENTITY_SUPABASE_URL"],
                     "TEI_PRIVATE_SUPABASE_ANON_KEY": "different-key"}):
            with self.assertRaises(RuntimeError):
                require_development_public_target(bad)

    def test_url_with_shell_metacharacters_is_not_executed_or_echoed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            secret = "postgresql://example.invalid/db?options=a&token=private"
            path.write_text(f"TEI_DEV_DATABASE_URL={secret}\n")
            os.chmod(path, 0o600)
            self.assertEqual(read_local_env(path)["TEI_DEV_DATABASE_URL"], secret)

    def test_rejects_loose_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            path.write_text("TOKEN=private\n")
            os.chmod(path, 0o644)
            with self.assertRaisesRegex(RuntimeError, "0600"):
                read_local_env(path)

    def test_error_never_includes_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            path.write_text("private-token-without-key\n")
            os.chmod(path, 0o600)
            with self.assertRaises(RuntimeError) as caught:
                read_local_env(path)
            self.assertNotIn("private-token", str(caught.exception))

    def test_bare_database_url_has_safe_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            path.write_text("postgresql://example.invalid/private\n")
            os.chmod(path, 0o600)
            with self.assertRaises(RuntimeError) as caught:
                read_local_env(path)
            self.assertIn("TEI_DEV_DATABASE_URL=", str(caught.exception))
            self.assertNotIn("example.invalid", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
