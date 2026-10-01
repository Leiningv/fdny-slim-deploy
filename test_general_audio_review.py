import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import audio_review
import detect
import main

PRIMARY = 'Phone Alarm Box 3302, 2775 East 16th Street, Bell Parkway South, Hammonds Avenue, for an odor of gasoline.'
SECOND = 'Phone Alarm Box 3302, 2775 East 16th Street, Belt Parkway South to Emmons Avenue, for an odor of gasoline.'

class Decisions(unittest.TestCase):
    def test_lost_complaint_veto_is_not_just_fire(self):
        self.assertTrue(audio_review.complaint_lost(PRIMARY, 'Phone Alarm'))
        self.assertFalse(audio_review.complaint_lost(PRIMARY, 'Odor of Gasoline'))
        self.assertFalse(audio_review.complaint_lost('Phone alarm, fire alarm activation', 'Automatic Alarm'))
    def test_two_numbered_ems_pairs_hold_whole_clip(self):
        for text in ["Any units available for 1557, 18-year-old dizzy. Any units for 1551, 50-year-old abdominal pain.",
                     "Any units available for 15 and 57, dizzy. Any units to 15 and 51, abdominal pain."]:
            self.assertTrue(audio_review.mixed(text,'zello-hatzalah'))
        self.assertFalse(audio_review.mixed("Units for 15 and 57, dizzy. Units for 15 and 57",'zello-hatzalah'))
    def test_no_mixed_job_recovery(self):
        h,r=audio_review.one_candidate(SECOND+' Phone Alarm Box 1234, 10 Main Street, smoke.', 'fdny')
        self.assertIsNone(h)
    def test_anchors_reject_wrong_house_box_and_complaint(self):
        h=detect.analyze(PRIMARY,'fdny')
        for phrase in [SECOND.replace('2775','2776').replace('Box 3302','Box 3303'),
                       SECOND.replace('Box 3302','Box 3303'),
                       SECOND.replace('odor of gasoline','unconscious')]:
            c=detect.analyze(phrase,'fdny')
            self.assertFalse(audio_review.compatible(h,c,'fdny',True))
    def test_mangled_street_repair_needs_anchors(self):
        h=detect.analyze('Phone alarm Box 2688, 4 Hamilton Parkway, for truck fire','fdny')
        c=detect.analyze('Phone alarm Box 2688, Fort Hamilton Parkway, for truck fire','fdny')
        self.assertTrue(audio_review.compatible(h,c,'fdny',False))
        other=detect.analyze('Phone alarm Box 2688, Central Avenue, for truck fire','fdny')
        self.assertFalse(audio_review.compatible(h,other,'fdny',False))
    def test_substantive_nature_cannot_change(self):
        a=detect.analyze('Phone Alarm Box 3302, 2775 East 16th Street, odor of gas','fdny')
        b=detect.analyze('Phone Alarm Box 3302, 2775 East 16th Street, automatic alarm','fdny')
        self.assertFalse(audio_review.compatible(a,b,'fdny'))

class Workflow(unittest.IsolatedAsyncioTestCase):
    async def test_one_cached_second_read(self):
        stats=Mock()
        with patch.object(main.transcribe,'second_listen',return_value=SECOND) as ear:
            self.assertEqual(await main._bounded_second_listen(Path('a.wav'),'fdny',stats),SECOND)
            self.assertEqual(await main._bounded_second_listen(Path('a.wav'),'fdny',stats),SECOND)
        ear.assert_called_once()
    async def test_prepost_replaces_fallback_no_send_from_review(self):
        h=detect.analyze(PRIMARY,'fdny');h['nature']='Phone Alarm'
        with (patch.object(main,'_bounded_second_listen',new_callable=AsyncMock,return_value=SECOND),
              patch.object(main,'verify_and_send',new_callable=AsyncMock,return_value='verified') as verify):
            revised,reason=await main._fdny_audio_review({'ts':time.time(),'transcription':PRIMARY},h,Mock(),'a.wav','')
        self.assertEqual(reason,'')
        self.assertEqual(revised['nature'],'Odor of Gasoline')
        self.assertEqual(revised['cross'],'Belt Parkway South & Emmons Avenue')
        self.assertTrue(all(c.kwargs['prepare_only'] for c in verify.await_args_list))
    async def test_empty_second_fails_closed(self):
        h=detect.analyze(PRIMARY,'fdny')
        with (patch.object(main,'_bounded_second_listen',new_callable=AsyncMock,return_value=''),
              patch.object(main,'verify_and_send',new_callable=AsyncMock,return_value='verified')):
            _,reason=await main._fdny_audio_review({'ts':time.time(),'transcription':PRIMARY},h,Mock(),'a.wav','')
        self.assertTrue(reason)
    async def test_map_failure_cannot_be_overridden(self):
        h=detect.analyze(PRIMARY,'fdny')
        with (patch.object(main,'_bounded_second_listen',new_callable=AsyncMock,return_value=SECOND),
              patch.object(main,'verify_and_send',new_callable=AsyncMock,return_value='suppressed')):
            _,reason=await main._fdny_audio_review({'ts':time.time(),'transcription':PRIMARY},h,Mock(),'a.wav','')
        self.assertTrue(reason)
    async def test_stale_skips_second_service(self):
        with patch.object(main,'_bounded_second_listen',new_callable=AsyncMock) as ear:
            _,reason=await main._fdny_audio_review({'ts':time.time()-700},None,Mock(),'a.wav','')
        self.assertIn('stale',reason);ear.assert_not_awaited()
    async def test_prepare_mode_never_sends(self):
        h=detect.analyze('Any units to 17 and 55 for a full trauma?','zello-hatzalah')
        with (patch.object(main,'_hatzalah_point_area',new_callable=AsyncMock,return_value='Brooklyn'),
              patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(40.63,-73.99)),
              patch.object(main,'_cross_streets',new_callable=AsyncMock,return_value=(None,False)),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send,
              patch.object(main,'_ensure_ogg') as ogg):
            result=await main.verify_and_send('zello-hatzalah',h,Mock(),'a.wav',prepare_only=True)
        self.assertEqual(result,'verified');send.assert_not_awaited();ogg.assert_not_called()

class Handler(unittest.IsolatedAsyncioTestCase):
    async def test_enabled_handler_reviews_before_actual_sender(self):
        import tempfile,os
        events=[]
        async def fake_send(profile, hit, stats, clip_name, **kwargs):
            events.append(('prepare' if kwargs.get('prepare_only') else 'send',hit['nature']))
            return 'verified' if kwargs.get('prepare_only') else 'sent'
        with tempfile.TemporaryDirectory() as d:
            wav=Path(d)/'clip.wav';wav.write_bytes(b'placeholder')
            with (patch.dict(os.environ,{'FDNY_AUDIO_REVIEW':'1'}),
                  patch.object(main,'_fdny_fetch_clip',return_value=wav),
                  patch.object(main,'_fdny_clip_sanity',return_value=''),
                  patch.object(main,'_archive_clip'),patch.object(main,'_save_seen'),
                  patch.object(main,'_kw_check',new_callable=AsyncMock),
                  patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'2775 EAST 16 STREET, Brooklyn, NY',40.58,-73.95,'Brooklyn')),
                  patch.object(main,'_bounded_second_listen',new_callable=AsyncMock,return_value=SECOND) as ear,
                  patch.object(main,'verify_and_send',new_callable=AsyncMock,side_effect=fake_send),
                  patch.object(main,'_append_alert_log'),patch.object(main,'_fdny_call_record')):
                await main._fdny_handle_call({'id':'gas','ts':time.time(),'transcription':PRIMARY,'audio_url':'https://example.invalid/x'},Mock(),{},Path(d))
        ear.assert_awaited_once()
        self.assertTrue(events)
        self.assertEqual(events[-1],('send','Odor of Gasoline'))
        self.assertTrue(all(kind=='prepare' for kind,nat in events[:-1]))

class Archive(unittest.TestCase):
    def test_retention_is_per_feed_and_removes_matching_ogg(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'src';src.write_bytes(b'pcm')
            archive=root/'archive';archive.mkdir()
            for name in ['fdny-1-a.wav','fdny-2-b.wav','zello-hatzalah-1.wav']:
                (archive/name).write_bytes(b'old')
            (archive/'fdny-1-a.ogg').write_bytes(b'old')
            with patch.object(main,'ARCHIVE_DIR',archive),patch.object(main,'ARCHIVE_KEEP',2):
                main._archive_clip(src,'fdny-3-c.wav')
            self.assertFalse((archive/'fdny-1-a.wav').exists())
            self.assertFalse((archive/'fdny-1-a.ogg').exists())
            self.assertTrue((archive/'zello-hatzalah-1.wav').exists())
