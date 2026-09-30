import unittest
from unittest.mock import AsyncMock,Mock,patch
import main,detect,audio_review

FDNY='Phone Alarm Box 3047, 1878 New York Avenue, Avenue K King, Avenue J John, point of fire in the rear, multiple dwelling.'
class Extraction(unittest.TestCase):
    def test_rear_dwelling_never_alarm(self):
        h=detect.analyze(FDNY,'fdny')
        self.assertEqual(h['nature'],'Fire in the Rear, Multiple Dwelling')
        self.assertEqual(h['cross'],'Avenue K & Avenue J')
        self.assertTrue(audio_review.complaint_lost(FDNY,'Phone Alarm'))
    def test_negative_fire_not_upgraded(self):
        self.assertFalse(audio_review.complaint_lost('Phone alarm, no fire in the rear','Phone Alarm'))
    def test_age_once(self):
        h=detect.analyze("Any units in Canarsie, Pennsylvania Avenue and Vandalia? It's an 80-year-old not feeling well.",'zello-hatzalah')
        self.assertEqual(main.format_alert(h).lower().count('80-year-old'),1)
    def test_numbered_spoken_block_candidate(self):
        h=detect.analyze('Any units to1516 44th Street for patient unconscious. 1516 44th Street between 15 and 16 and a private.','zello-hatzalah')
        self.assertEqual(h['cross'],'15th Avenue & 16th Avenue')
        self.assertTrue(h['inherited_numbered_cross'])

class Corner(unittest.IsolatedAsyncioTestCase):
    async def test_pennsylvania_vandalia_verified_spoken_corner(self):
        h=detect.analyze("Any units in Canarsie, Pennsylvania Avenue and Vandalia? It's an 80-year-old not feeling well.",'zello-hatzalah')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'Pennsylvania Avenue, Brooklyn, NY',40.65,-73.88,'Brooklyn')),
              patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(40.65,-73.88)),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
              patch('locality_gate.default_area_safe',new_callable=AsyncMock,return_value=True),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
            outcome=await main.verify_and_send('zello-hatzalah',h,Mock())
        self.assertEqual(outcome,'sent');self.assertIn('Vandalia',send.await_args.args[0]);self.assertNotIn('Flatlands',send.await_args.args[0])

class ActualTerminalHold(unittest.IsolatedAsyncioTestCase):
    async def test_rear_dwelling_off_cannot_send(self):
        import tempfile,time
        from pathlib import Path
        stats=Mock()
        with tempfile.TemporaryDirectory() as d:
            wav=Path(d)/'clip.wav';wav.write_bytes(b'fixture')
            with (patch.dict(main.os.environ,{'FDNY_AUDIO_REVIEW':'0','HELD_REVIEW_ROUTE':'report_only'}),
                  patch.object(main,'_fdny_fetch_clip',return_value=wav),patch.object(main,'_fdny_clip_sanity',return_value=''),
                  patch.object(main,'_archive_clip'),patch.object(main,'_save_seen'),patch.object(main,'_kw_check',new_callable=AsyncMock),
                  patch.object(main,'ops_log'),patch.object(main,'_append_alert_log'),patch.object(main,'_fdny_call_record'),
                  patch.object(main,'_held_recording',new_callable=AsyncMock,return_value=''),
                  patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
                await main._fdny_handle_call({'id':'rear','ts':time.time(),'transcription':FDNY,'audio_url':'https://example.invalid/audio'},stats,{},Path(d))
            send.assert_not_awaited()
            self.assertIn('dwelling',stats.mark_alert.call_args.kwargs['reason'])
            self.assertEqual(stats.mark_alert.call_args.args[1],'Fire in the Rear, Multiple Dwelling')

class CorridorRepeat(unittest.TestCase):
    def test_pennsylvania_repeat_primary_not_cross_pair(self):
        s='Unit 10, can I receive from Pennsylvania Avenue off of Vandalia Avenue for 80-year-old not feeling well? K-50, direction? K-50, Pennsylvania between Flatlands and Vandalia, 50. Responding.'
        h=detect.analyze(s,'zello-hatzalah')
        self.assertEqual(h['address'],'Pennsylvania Avenue, Brooklyn, NY')
        self.assertEqual(h['cross'],'Flatlands Avenue & Vandalia Avenue')
        self.assertFalse(h['direct_cross_candidate'])

class InheritedVerification(unittest.IsolatedAsyncioTestCase):
    async def check(self,valid):
        h=detect.analyze('Any units to1516 44th Street for patient unconscious. 1516 44th Street between 15 and 16 and a private.','zello-hatzalah')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'1516 44th Street, Brooklyn, NY',40.63,-73.98,'Brooklyn')),
              patch('spoken_cross.verify',new_callable=AsyncMock,return_value=valid),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'sent' if valid else 'suppressed')
        if valid:self.assertIn('C/s 15th Avenue & 16th Avenue',send.await_args.args[0])
        else:send.assert_not_awaited()
    async def test_real_crosses_print(self):await self.check(True)
    async def test_unproven_crosses_hold(self):await self.check(False)
