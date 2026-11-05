"""Reject privileged keys even when accidentally placed in an anon-key setting."""
import base64
import json
import os
import unittest
from unittest.mock import patch

from app import workspace_public_config
from src.entities.repository import EntityRepository, EntityStoreUnavailable
from src.runtime_config import private_supabase_config, public_supabase_config


def fixture_key(role):
    payload = base64.urlsafe_b64encode(json.dumps({'role': role}).encode()).decode().rstrip('=')
    return 'test.' + payload + '.not-a-real-signature'


class RuntimeConfigTests(unittest.TestCase):
    def test_privileged_keys_never_escape_public_or_private_config(self):
        for key in ('sb_secret_fixture', fixture_key('service_role'), fixture_key('authenticated'), 'bad.jwt.payload', 'sbp_management_fixture', 'unknown-opaque-credential'):
            with self.subTest(kind=key.split('.')[0]), patch.dict(os.environ, {
                    'TEI_ENTITY_SUPABASE_URL': 'https://development.invalid', 'TEI_ENTITY_ANON_KEY': key,
                    'TEI_PRIVATE_SUPABASE_URL': 'https://development.invalid', 'TEI_PRIVATE_SUPABASE_ANON_KEY': key}, clear=True):
                self.assertEqual(public_supabase_config()[1], '')
                self.assertEqual(private_supabase_config(), ('', ''))
                self.assertFalse(workspace_public_config()['auth_enabled'])
                self.assertEqual(workspace_public_config()['publishable_key'], '')
                with patch('urllib.request.urlopen') as opened:
                    with self.assertRaises(EntityStoreUnavailable):
                        EntityRepository()._get('entities', {})
                    opened.assert_not_called()

    def test_public_keys_remain_compatible(self):
        for key in ('sb_publishable_fixture', fixture_key('anon')):
            with patch.dict(os.environ, {'TEI_ENTITY_SUPABASE_URL': 'https://development.invalid',
                                        'TEI_ENTITY_ANON_KEY': key,
                                        'TEI_PRIVATE_SUPABASE_URL': 'https://development.invalid',
                                        'TEI_PRIVATE_SUPABASE_ANON_KEY': key}, clear=True):
                self.assertEqual(public_supabase_config(), ('https://development.invalid', key))
                self.assertEqual(private_supabase_config(), ('https://development.invalid', key))

    def test_explicit_service_secret_cannot_be_relabelled_as_anon(self):
        with patch.dict(os.environ, {'TEI_ENTITY_ANON_KEY': 'opaque-test-secret',
                                    'SUPABASE_SERVICE_ROLE_KEY': 'opaque-test-secret'}, clear=True):
            self.assertEqual(public_supabase_config()[1], '')
