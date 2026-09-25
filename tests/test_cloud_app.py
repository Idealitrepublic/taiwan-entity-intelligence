import json
import io
import unittest
from unittest.mock import patch
from app import app
from src import cloud_company
from src.rate_limit import FixedWindowLimiter, client_identity

class CloudAppTests(unittest.TestCase):
    def request(self,path):
        status=[]
        body=b''.join(app({'REQUEST_METHOD':'GET','PATH_INFO':path,'HTTP_HOST':'taiwan-entity-intelligence.vercel.app'},lambda s,h:status.append(s)))
        return status[0],body
    def test_primary_domain_serves_locally(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No proxy allowed')):
            status,body=self.request('/')
        self.assertTrue(status.startswith('200'))
        self.assertIn(b'Taiwan Entity Intelligence',body)
    def test_invalid_uniform_is_rejected_before_network(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No network allowed')):
            status,body=self.request('/api/company/123')
        self.assertTrue(status.startswith('400'))
    def test_health_does_not_claim_success_on_failed_database(self):
        with patch('app.db_count',side_effect=RuntimeError('Unavailable')):
            status,body=self.request('/api/status')
        self.assertTrue(status.startswith('503'))
        self.assertFalse(json.loads(body)['supabase']['connected'])
    def test_domain_requires_a_domain(self):
        with self.assertRaises(ValueError):
            cloud_company.check_domain('localhost')
    def test_runtime_error_is_redacted_and_request_is_logged(self):
        status=[]
        headers=[]
        with patch('app.dispatch',side_effect=RuntimeError('secret-value')), \
             patch('sys.stderr',new_callable=io.StringIO) as stderr:
            body=b''.join(app({'REQUEST_METHOD':'GET','PATH_INFO':'/api/fail'},
                              lambda s,h:(status.append(s),headers.extend(h))))
        self.assertTrue(status[0].startswith('502'))
        self.assertNotIn(b'secret-value',body)
        events=[json.loads(line) for line in stderr.getvalue().splitlines()]
        self.assertEqual([event['event'] for event in events],
                         ['request_failed','request_complete'])
        self.assertTrue(dict(headers).get('X-Request-Id'))
    def test_rate_limiter_is_bounded_and_resets(self):
        limiter=FixedWindowLimiter(window_seconds=60)
        self.assertTrue(limiter.allow('client',2,now=1))
        self.assertTrue(limiter.allow('client',2,now=2))
        self.assertFalse(limiter.allow('client',2,now=3))
        self.assertTrue(limiter.allow('client',2,now=61))
    def test_rate_limit_identity_ignores_spoofed_forwarded_for(self):
        environ = {'HTTP_X_FORWARDED_FOR': '1.2.3.4', 'REMOTE_ADDR': '192.0.2.10'}
        with patch.dict('os.environ', {'VERCEL': ''}):
            self.assertEqual(client_identity(environ), '192.0.2.10')
        environ['HTTP_X_VERCEL_FORWARDED_FOR'] = '198.51.100.5'
        with patch.dict('os.environ', {'VERCEL': '1'}):
            self.assertEqual(client_identity(environ), '198.51.100.5')
