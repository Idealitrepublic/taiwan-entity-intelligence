"""Ensure the approved read-only backup cannot target Development or leak PG overrides."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.ops_production_backup import backup, production_environment


class ProductionBackupTests(unittest.TestCase):
    def test_only_original_production_and_session_port_are_accepted(self):
        for url in ('postgresql://postgres:test@db.canqjiokrtcxkwblhmml.supabase.co/postgres',
                    'postgresql://postgres:test@localhost/postgres',
                    'postgresql://postgres:test@db.rztdbdurkjfrirsrrhtu.supabase.co.attacker.test/postgres',
                    'postgresql://postgres.rztdbdurkjfrirsrrhtu:test@aws-0.pooler.supabase.com:6543/postgres',
                    'postgresql://postgres:test@db.rztdbdurkjfrirsrrhtu.supabase.co/other'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                production_environment(url)

    def test_query_and_ambient_options_cannot_disable_read_only(self):
        with patch.dict(os.environ, {'PGSERVICE': 'other', 'PGOPTIONS': '-c default_transaction_read_only=off'}):
            env = production_environment('postgresql://postgres:test@db.rztdbdurkjfrirsrrhtu.supabase.co/postgres?options=unsafe')
        self.assertNotIn('PGSERVICE', env)
        self.assertEqual(env['PGOPTIONS'], '-c default_transaction_read_only=on')
        self.assertEqual(env['PGSSLMODE'], 'require')

    def test_wrong_target_rejected_before_dump_or_filesystem_work(self):
        with patch('scripts.ops_production_backup.encrypt_stream') as dump:
            with self.assertRaises(ValueError):
                backup(Path('/nonexistent'), '', '', Path('/nonexistent'))
            dump.assert_not_called()

    def test_production_session_user_matches_project(self):
        env = production_environment('postgresql://postgres.rztdbdurkjfrirsrrhtu:test@aws-0.pooler.supabase.com:5432/postgres')
        self.assertEqual(env['PGUSER'], 'postgres.rztdbdurkjfrirsrrhtu')
        self.assertEqual(env['PGDATABASE'], 'postgres')
