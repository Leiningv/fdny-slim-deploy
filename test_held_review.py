import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import main


class ReviewText(unittest.TestCase):
    def test_no_nature_question_is_explained(self):
        text = main._held_review_text('zello-sullivan',
            {'nature': '', 'address': 'Monticello, NY', 'hold_reason': 'no nature'})
        self.assertIn('parsed the location as Monticello, NY', text)
        self.assertIn('What complaint does the dispatcher actually say', text)
        self.assertNotIn('no clear complaint', text)

    def test_cross_number_question_does_not_invent_an_alternative(self):
        text = main._held_review_text('fdny',
            {'nature': 'Alarm', 'address': '1111 Avenue U, Brooklyn, NY',
             'hold_reason': 'FDNY numbered cross street needs an independent audio check'})
        self.assertIn('transcribed with the wrong digits', text)
        self.assertNotIn('22nd', text)


class ReviewDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_off_gate_sends_nothing(self):
        with (patch.dict(main.os.environ, {'HELD_REVIEW_ENABLED':'0'}),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as text):
            await main._post_held_review('fdny', {'hold_reason':'no nature'}, 'clip.wav')
            text.assert_not_awaited()

    async def test_text_and_real_voice_target_ops_only(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'clip.ogg').write_bytes(b'OggS'+b'1'*200)
            with (patch.dict(main.os.environ, {'HELD_REVIEW_ENABLED':'1'}),
                  patch.object(main, 'ARCHIVE_DIR', Path(d)),
                  patch.object(main, '_ensure_ogg', return_value='clip.ogg'),
                  patch.object(main.alert_waha, '_ops_chat', return_value='ops@g.us'),
                  patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock,
                               return_value=True) as text,
                  patch.object(main.alert_waha, 'send_voice', new_callable=AsyncMock,
                               return_value=True) as voice):
                await main._post_held_review('zello-sullivan',
                    {'address':'Monticello, NY','nature':'','hold_reason':'no nature'}, 'clip.wav')
                self.assertEqual(text.await_args.kwargs['chat_id'], 'ops@g.us')
                self.assertEqual(voice.await_args.kwargs['chat_id'], 'ops@g.us')
                self.assertIn('/audio/clip.ogg', voice.await_args.args[0])
