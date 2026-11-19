"""Page-load health must not compete with search through exact-count fanout."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch

import app


class SearchLoadIsolationTests(unittest.TestCase):
    def setUp(self):
        app.STATUS_CACHE.clear()
        self.config = patch.multiple(app.core,
            SUPABASE='https://canqjiokrtcxkwblhmml.supabase.co', SUPABASE_KEY='anon-test')
        self.config.start()

    def tearDown(self):
        self.config.stop()
        app.STATUS_CACHE.clear()

    def seed(self):
        with patch('app.Thread'):
            result = app.database_status()
        app.STATUS_BACKGROUND_LOCK.release()
        return result

    def test_cold_and_repeated_page_loads_never_start_count_queries(self):
        with patch('app.db_count') as counted, patch('app._refresh_database_status') as full, \
                patch('app.Thread') as thread:
            try:
                for _ in range(20):
                    code, body, _ = app.dispatch('/api/status', {})
                    self.assertEqual(code, 200)
                    self.assertEqual(body['supabase']['canonical']['companies'], 472)
                    self.assertEqual(body['supabase']['counts_state'], 'cached')
                counted.assert_not_called()
                full.assert_not_called()
                thread.assert_called_once()
            finally:
                app.STATUS_BACKGROUND_LOCK.release()

    def test_probe_preserves_exact_counts_dates_and_cached_label(self):
        _, before, _ = self.seed()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'[]'
        with patch('app.urllib.request.urlopen', return_value=response) as opened, \
                patch('app.db_count') as counted:
            # db_count is not the probe; use a matching cache key while mocked.
            app.STATUS_CACHE[(app.core.SUPABASE, id(app.db_count))] = (0, (200, before))
            app._refresh_status_connectivity()
            _, after, _ = app.database_status()
            counted.assert_not_called()
        self.assertTrue(after['supabase']['connected'])
        for key in ('canonical', 'metric_checked_at', 'counts_checked_at', 'stale_metrics', 'counts_state'):
            self.assertEqual(after['supabase'][key], before['supabase'][key])
        req = opened.call_args.args[0]
        self.assertEqual(req.full_url, app.core.SUPABASE + '/rest/v1/entities?select=id&limit=1')
        self.assertIsNone(req.get_header('Prefer'))
        self.assertEqual(opened.call_args.kwargs['timeout'], 2)

    def test_failed_probe_retains_counts_and_throttles_retry_without_secrets(self):
        _, before, _ = self.seed()
        with patch('app.urllib.request.urlopen', side_effect=TimeoutError('private-secret')), \
                patch('app.log_event') as logged:
            app._refresh_status_connectivity()
        with patch('app.Thread') as thread:
            code, after, _ = app.database_status()
            thread.assert_not_called()
        self.assertEqual(code, 200)
        self.assertFalse(after['supabase']['connected'])
        self.assertEqual(before['supabase']['canonical'], after['supabase']['canonical'])
        self.assertNotIn('private-secret', str(logged.call_args))

    def test_simultaneous_page_loads_share_one_lightweight_probe(self):
        started, release = Event(), Event()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'[]'

        def probe(*args, **kwargs):
            started.set()
            release.wait(3)
            return response

        with patch('app.urllib.request.urlopen', side_effect=probe) as opened, \
                patch('app.db_count') as counted:
            try:
                app.database_status()
                self.assertTrue(started.wait(1))
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(lambda _: app.database_status(), range(20)))
                self.assertTrue(all(result[0] == 200 for result in results))
                self.assertEqual(opened.call_count, 1)
                counted.assert_not_called()
            finally:
                release.set()
                self.assertTrue(app.STATUS_BACKGROUND_LOCK.acquire(timeout=3))
                app.STATUS_BACKGROUND_LOCK.release()

    def test_other_database_cannot_inherit_counts_or_fabricate_zero(self):
        with patch('app.core.SUPABASE', 'https://other.supabase.co'):
            _, before, _ = self.seed()
            self.assertNotIn('canonical', before['supabase'])
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps([]).encode()
            with patch('app.urllib.request.urlopen', return_value=response):
                app._refresh_status_connectivity()
            code, after, _ = app.database_status()
            self.assertEqual(code, 200)
            self.assertTrue(after['supabase']['connected'])
            self.assertEqual(after['supabase']['counts_state'], 'unavailable')
            self.assertNotIn('canonical', after['supabase'])
