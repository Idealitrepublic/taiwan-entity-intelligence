import io
import socket
import ssl
import unittest
import urllib.error
from unittest.mock import patch

from src.sources import procurement


class ProcurementTransportTests(unittest.TestCase):
    def test_transport_timeout_can_recover_on_one_bounded_retry(self):
        with patch.object(procurement.urllib.request, 'urlopen', side_effect=[
                TimeoutError('private exception text'), io.BytesIO(b'{"records": []}')]) as opened, \
                patch.object(procurement.time, 'sleep') as sleep:
            self.assertEqual(procurement._json_get(procurement.API), {'records': []})
        self.assertEqual(opened.call_count, 2)
        self.assertTrue(all(0 < call.kwargs['timeout'] <= 8 for call in opened.call_args_list))
        sleep.assert_called_once()

    def test_exhausted_retries_stay_partial_with_safe_diagnostics(self):
        with patch.object(procurement.urllib.request, 'urlopen', side_effect=TimeoutError('sensitive marker')), \
                patch.object(procurement.time, 'sleep'):
            result = procurement.lookup_awards('96979933')
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['records'], [])
        self.assertEqual(result['source_error']['category'], 'timeout')
        self.assertNotIn('sensitive marker', str(result))
        self.assertNotIn('retrieved_at', result)
        self.assertIn('attempted_at', result)

    def test_http_429_and_invalid_tls_are_never_blindly_retried(self):
        errors = [urllib.error.HTTPError(procurement.API, 429, 'rate limit', {}, None),
                  urllib.error.URLError(ssl.SSLCertVerificationError('certificate error'))]
        for error in errors:
            with self.subTest(error=type(error).__name__), \
                    patch.object(procurement.urllib.request, 'urlopen', side_effect=error) as opened, \
                    patch.object(procurement.time, 'sleep') as sleep:
                with self.assertRaises(type(error)):
                    procurement._json_get(procurement.API)
                opened.assert_called_once()
                sleep.assert_not_called()

    def test_deadline_exhaustion_never_starts_an_extra_request(self):
        with patch.object(procurement.time, 'monotonic', side_effect=[0, 0, 10, 10]), \
                patch.object(procurement.time, 'sleep'), \
                patch.object(procurement.urllib.request, 'urlopen', side_effect=TimeoutError()) as opened:
            with self.assertRaises(TimeoutError):
                procurement._json_get(procurement.API, timeout=8)
        opened.assert_called_once()

    def test_dns_diagnostic_does_not_include_exception_text(self):
        value = procurement._source_error(urllib.error.URLError(socket.gaierror(-2, 'private marker')))
        self.assertEqual(value['category'], 'dns')
        self.assertEqual(value['errno'], -2)
        self.assertNotIn('private marker', str(value))

    def test_success_http_with_invalid_source_schema_is_not_a_zero_result(self):
        with patch.object(procurement.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"error":"upstream error"}')) as opened:
            result = procurement.lookup_awards('96979933')
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['source_error']['category'], 'format')
        opened.assert_called_once()


if __name__ == '__main__':
    unittest.main()
