import unittest,time
from unittest.mock import AsyncMock,Mock,patch
import detect,audio_review,main
FIRST='Any units in the W from Franklin and Myrtle for child difficulty breathing? '
SECOND='Any units on the Upper West Side to West 7th and Broadway with the backup to West Side 901.'
SOURCE=FIRST+('W110 respond. '*30)+SECOND
class UwsMixed(unittest.TestCase):
    def test_recording_wide_detected_beyond_preview(self):
        self.assertTrue(detect.hatzalah_uws_mixed_request(SOURCE,'zello-hatzalah'))
        self.assertTrue(audio_review.mixed(SOURCE,'zello-hatzalah'))
        h=detect.analyze(SOURCE,'zello-hatzalah')
        self.assertIn(SECOND,h['dispatch_source_text'])
        self.assertNotIn(SECOND,h['excerpt'])
    def test_scope_and_repeats(self):
        for t in [FIRST,FIRST+FIRST,SECOND,SECOND+' '+SECOND,'W110 backup 169 '+SECOND,FIRST+SECOND.replace('Broadway','Riverside'),FIRST+SECOND.replace('West Side 901','West Side 902')]:
            self.assertFalse(detect.hatzalah_uws_mixed_request(t,'zello-hatzalah'))
    def test_other_feeds_unchanged(self):
        for p in ['fdny','zello-sullivan']:
            self.assertFalse(detect.hatzalah_uws_mixed_request(SOURCE,p))
class UwsGuard(unittest.IsolatedAsyncioTestCase):
    async def test_final_guard_before_maps_send(self):
        h=detect.analyze(SOURCE,'zello-hatzalah')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock) as geo,patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
        geo.assert_not_awaited();send.assert_not_awaited()
    async def test_wrapper_holds_without_second_listen(self):
        h=detect.analyze(SOURCE,'zello-hatzalah')
        with (patch.object(main,'verify_and_send',new_callable=AsyncMock) as verify,patch.object(main,'_bounded_second_listen',new_callable=AsyncMock) as listen):
            result,_=await main.verify_zello_with_second_listen('zello-hatzalah',h,Mock(),'unused.wav',fresh_ts=time.time())
        self.assertEqual(result,'suppressed');verify.assert_not_awaited();listen.assert_not_awaited()
