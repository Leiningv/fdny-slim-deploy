import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect, audio_review, main

SOURCE = ('Sullivan dispatch, Empress, 2 calls. First call, Town of Thompson, '
          'Resorts World, 888 Resorts World Drive, diabetic emergency, difficulty breathing, '
          'ALS response. Second call, Village of Monticello, 414 Broadway, '
          'the Courthouse, for seizures, BLS response.')
REPEAT = ('diabetic attack, difficulty breathing, Resorts World, 888 Resorts World Drive. '
          'Second call, 414 Broadway, the courthouse, Village of Monticello, for seizure, BLS response.')

class NumberedJobs(unittest.TestCase):
    def test_actual_source_and_clipped_repeat_are_mixed(self):
        for t in (SOURCE, REPEAT):
            self.assertTrue(audio_review.mixed(t, 'zello-sullivan'))
            self.assertIsNone(audio_review.one_candidate(t, 'zello-sullivan')[0])
    def test_page_response_and_first_call_repeat_unchanged(self):
        for t in ('First call, 414 Broadway, seizure. Repeating first call, 414 Broadway, seizure.',
                  '414 Broadway, seizure, second page, BLS response.',
                  '414 Broadway, seizure, second response requested.'):
            self.assertFalse(detect.sullivan_numbered_jobs(t, 'sullivan'))
    def test_other_feeds_unchanged(self):
        self.assertFalse(detect.sullivan_numbered_jobs(SOURCE, 'zello-hatzalah'))
    def test_source_not_truncated_at_280(self):
        t = 'Sullivan dispatch, 414 Broadway, seizure. ' + 'Repeating dispatch details. '*15 + 'Second call, 60 Haddock Road, difficulty breathing.'
        h = detect.analyze(t, 'zello-sullivan')
        self.assertNotIn('Second call', h['excerpt'])
        self.assertTrue(detect.sullivan_numbered_jobs(h['dispatch_source_text'], 'sullivan'))

class SendBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_final_send_holds_original_and_preview_overflow(self):
        for t in (SOURCE, REPEAT, SOURCE.replace('Second call', 'Repeating dispatch details. '*15+'Second call')):
            h=detect.analyze(t, 'zello-sullivan')
            with (patch.object(main, 'geocode_verify',new_callable=AsyncMock) as geo,
                  patch.object(main.alert_waha, 'send_text',new_callable=AsyncMock) as send):
                self.assertEqual(await main.verify_and_send('zello-sullivan',h,Mock()),'suppressed')
            self.assertIn('numbered dispatch jobs',h['hold_reason'])
            geo.assert_not_awaited();send.assert_not_awaited()
    async def test_wrapper_holds_before_prepare_and_second_listen(self):
        h=detect.analyze(SOURCE,'zello-sullivan')
        with (patch.object(main,'verify_and_send',new_callable=AsyncMock) as verify,
              patch.object(main,'_bounded_second_listen',new_callable=AsyncMock) as ear):
            result,_=await main.verify_zello_with_second_listen('zello-sullivan',h,Mock(),'a.wav',fresh_ts=0)
        self.assertEqual(result,'suppressed');verify.assert_not_awaited();ear.assert_not_awaited()
