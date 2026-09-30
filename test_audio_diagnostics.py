import unittest
import urllib.error
from unittest.mock import patch
import transcribe
import audio_review

class Diagnostics(unittest.TestCase):
    def test_http_status_without_secret_response(self):
        for status, category in [(429, 'rate_limited'), (401, 'access_rejected'),
                                 (403, 'access_rejected'), (500, 'provider_error'),
                                 (400, 'request_rejected')]:
            error = urllib.error.HTTPError('https://provider.invalid/secret', status,
                                           'secret response', {}, None)
            with (patch.object(transcribe, 'GROQ_ENABLED', True),
                  patch.object(transcribe, 'GROQ_KEY', 'test-only'),
                  patch.object(transcribe, '_groq_transcribe', side_effect=error),
                  self.assertLogs(level='WARNING') as logs):
                self.assertEqual(transcribe.second_listen('test.wav', 'zello-hatzalah'), '')
            text = ' '.join(logs.output)
            self.assertIn('http_status=' + str(status), text)
            self.assertIn(category, text)
            self.assertNotIn('secret', text)
            self.assertNotIn('test-only', text)

    def test_actual_clarendon_search_report_is_mixed(self):
        text = ('57 signal Box 3907, Claremont Road, East 35 34 car fire. '
                '57 signal Box 3907, Claremont Road, East 35 34 car fire. '
                'Division 15. Box 1636 primary is complete negative on the second floor '
                'with the exception of three 10-45 no codes.')
        self.assertTrue(audio_review.mixed(text, 'fdny'))
        candidate, reason = audio_review.one_candidate(text, 'fdny')
        self.assertIsNone(candidate)
        self.assertIn('multiple jobs', reason)

if __name__ == '__main__':
    unittest.main()
