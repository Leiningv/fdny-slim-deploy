import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import main


class ReviewText(unittest.TestCase):
    def test_no_nature_question_is_explained(self):
        text = main._held_review_text('zello-sullivan',
            {'nature': '', 'address': 'Monticello, NY', 'hold_reason': 'no nature'})
        self.assertIn('parsed the location as Monticello', text)
        self.assertNotIn('Monticello, NY', text)
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

    async def test_report_only_default_never_sends(self):
        with (patch.dict(main.os.environ, {'HELD_REVIEW_ROUTE':'report_only'}),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as send):
            await main._post_held_review('fdny', {'hold_reason':'no nature'}, 'clip.wav')
            send.assert_not_awaited()

    async def test_owner_dm_compact_line_never_group_or_voice(self):
        with (patch.dict(main.os.environ, {'HELD_REVIEW_ROUTE':'owner_dm',
                                          'HELD_REVIEW_OWNER_CHAT_ID':'19293781556@c.us'}),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock,
                           return_value=True) as send,
              patch.object(main.alert_waha, 'send_voice', new_callable=AsyncMock) as voice):
            await main._post_held_review('fdny', {'hold_reason':'terminal hold',
                'box_heard':'3413', 'address':'216 Avenue T, Brooklyn, NY',
                'nature':'Fire in a Private Dwelling','voice_url':'https://example.invalid/recording'}, 'clip.wav')
            self.assertEqual(send.await_args.kwargs['chat_id'], '19293781556@c.us')
            self.assertIn('3413', send.await_args.args[0])
            self.assertIn('https://example.invalid/recording', send.await_args.args[0])
            voice.assert_not_awaited()

    async def test_group_route_refused(self):
        with (patch.dict(main.os.environ, {'HELD_REVIEW_ROUTE':'owner_dm',
                                          'HELD_REVIEW_OWNER_CHAT_ID':'ops@g.us'}),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as send):
            await main._post_held_review('fdny', {'hold_reason':'terminal hold'}, 'clip.wav')
            send.assert_not_awaited()
