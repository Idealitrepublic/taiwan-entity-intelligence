"""Exercise restore rejection boundaries before any database process starts."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.ops_restore_drill import drill, normalize_constraint, restore_error_category, sql_identifier, validate_archive


class RestoreDrillTests(unittest.TestCase):
    def archive(self, root):
        root.chmod(0o700)
        files = {}
        for name in ('development.dump.age', 'sync-evidence.tar.age'):
            path = root / name
            path.write_bytes(b'encrypted test fixture')
            path.chmod(0o600)
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {'project_ref': 'canqjiokrtcxkwblhmml', 'archive_verified': True,
                    'encrypted_files': files}
        (root / 'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_tampered_encrypted_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.archive(root)
            self.assertEqual(validate_archive(root), root.resolve())
            (root / 'development.dump.age').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                validate_archive(root)

    def test_production_or_unverified_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = self.archive(root)
            for override in ({'project_ref': 'rztdbdurkjfrirsrrhtu'}, {'archive_verified': False},
                             {'encrypted_files': {'../outside': 'digest'}}):
                (root / 'manifest.json').write_text(json.dumps({**original, **override}))
                with self.assertRaises(ValueError):
                    validate_archive(root)

    def test_production_source_fails_before_read_or_cluster_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.archive(root)
            identity = root / 'identity'
            identity.write_text('test identity, not a real secret')
            identity.chmod(0o600)
            with patch('scripts.ops_restore_drill.snapshot') as read, \
                    patch('scripts.ops_restore_drill.subprocess.run') as command:
                with self.assertRaises(ValueError):
                    drill(root, 'postgresql://postgres:test@db.rztdbdurkjfrirsrrhtu.supabase.co/postgres', identity)
                read.assert_not_called()
                command.assert_not_called()

    def test_publicly_readable_directory_and_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.archive(root)
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                validate_archive(root)
            root.chmod(0o700)
            identity = root / 'identity'
            identity.write_text('test fixture')
            identity.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'identity'):
                drill(root, '', identity)

    def test_database_supplied_names_are_quoted_as_identifiers(self):
        self.assertEqual(sql_identifier('odd"table'), '"odd""table"')

    def test_cross_version_parenthesis_normalization_cannot_hide_changed_checks(self):
        source = {'conname': 'resolution_candidates_score_check', 'definition':
                  "CHECK ((((score >= (0)::numeric) AND (score <= (1)::numeric)) AND (score <> 'NaN'::numeric)))"}
        restored = {**source, 'definition':
                    "CHECK (((score >= (0)::numeric) AND (score <= (1)::numeric) AND (score <> 'NaN'::numeric)))"}
        self.assertEqual(normalize_constraint(source), normalize_constraint(restored))
        for value in (restored['definition'].replace('AND', 'OR'),
                      restored['definition'].replace('(1)::numeric', '(2)::numeric')):
            self.assertNotEqual(normalize_constraint(source), normalize_constraint({**source, 'definition': value}))

    def test_restore_errors_only_expose_fixed_categories_or_schema_names(self):
        error = b'pg_restore: error: ERROR:  schema "auth" does not exist\nCommand was: SECRET ROW CONTENT'
        self.assertEqual(restore_error_category(error), 'missing local prerequisite schema: auth')
        self.assertNotIn('SECRET', restore_error_category(b'ERROR: SECRET ROW CONTENT'))
