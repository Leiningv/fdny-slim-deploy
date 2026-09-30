import tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch,AsyncMock
import main
from status import Stats

class OutcomeOrdering(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_hold_saved_before_slow_or_failed_upload(self):
        events=[]
        stats=Mock()
        stats.mark_alert.side_effect=lambda *a,**kw: events.append(('saved',kw))
        async def upload(*args):
            self.assertEqual(events[0][0], 'saved')
            self.assertIn('/audio/', events[0][1]['voice_url'])
            raise RuntimeError('simulated upload unavailable')
        with tempfile.TemporaryDirectory() as d:
            wav=Path(d)/'clip.wav';wav.write_bytes(b'placeholder')
            with (patch.dict(main.os.environ, {'FDNY_AUDIO_REVIEW':'0','HELD_REVIEW_ROUTE':'report_only'}),
                  patch.object(main,'_fdny_fetch_clip',return_value=wav),
                  patch.object(main,'_fdny_clip_sanity',return_value=''),
                  patch.object(main,'_archive_clip'),patch.object(main,'_save_seen'),
                  patch.object(main,'_kw_check',new_callable=AsyncMock),
                  patch.object(main,'ops_log'),patch.object(main,'_append_alert_log'),
                  patch.object(main,'_fdny_call_record') as record,
                  patch.object(main,'_held_recording',new_callable=AsyncMock,side_effect=upload),
                  patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
                await main._fdny_handle_call({'id':'hold','ts':time.time(),
                        'transcription':'Phone Alarm Box 3413, 216 Avenue T, fire in a private dwelling.',
                        'audio_url':'https://example.invalid/audio'},stats,{},Path(d))
                record.assert_called_once()
                send.assert_not_awaited()
        self.assertIn('review disabled; terminal hold',events[0][1]['reason'])

    def test_recording_enrichment_has_no_duplicate_counter(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(main.os.environ,{'SEG_DIR':d}):
            stats=Stats()
            stats.mark_alert('fdny','Fire','780 Washington Avenue',False,failed=False,
                             outcome='suppressed',voice_url='local',reason='held')
            stats.update_alert_recording('fdny','Fire','780 Washington Avenue','local','published')
            self.assertEqual(len(stats.alerts),1)
            self.assertEqual(stats.alerts_failed,0)
            self.assertEqual(stats.alerts_sent,0)
            self.assertEqual(stats.alerts[0]['voice'],'published')
