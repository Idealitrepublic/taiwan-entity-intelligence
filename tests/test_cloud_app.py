import json
import unittest
from unittest.mock import patch
from app import app
from src import cloud_company

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
