import unittest
from unittest.mock import AsyncMock, Mock, patch

import detect
import main


class MonticelloMedicalDispatch(unittest.TestCase):
    def test_exact_held_transcript_recovers_spoken_medical_and_house(self):
        text = ('Sullivan County Dispatch, KUH Unit 5262, first responding to the '
                'Village of Monticello, a BLS response. 35-year-old male, general ill, '
                '377 East Broadway, apartment 5.')
        hit = detect.analyze(text, 'sullivan')
        self.assertEqual(hit['nature'], 'General Ill')
        self.assertEqual(hit['address'], '377 East Broadway, Monticello, NY')
        self.assertEqual(hit['apartment'], 'Apartment 5')

    def test_als_repeat_preserves_exact_wording(self):
        text = ('Dispatch, automatic mutual aid, ALS response. 35-year-old male, '
                'generally ill, 377 East Broadway, apartment 5, Village of Monticello.')
        hit = detect.analyze(text, 'sullivan')
        self.assertEqual((hit['nature'], hit['address']),
                         ('Generally Ill', '377 East Broadway, Monticello, NY'))

    def test_response_type_alone_is_not_a_complaint(self):
        text = 'BLS response to 377 East Broadway, Village of Monticello.'
        hit = detect.analyze(text, 'sullivan')
        self.assertEqual(hit['address'], '377 East Broadway, Monticello, NY')
        self.assertEqual(hit['nature'], '')

    def test_nonmedical_broadway_number_not_promoted(self):
        self.assertIsNone(detect.extract_dispatch_address(
            'Unit 377 East Broadway heard on the radio', 'sullivan'))


class VerifiedBroadwayGate(unittest.IsolatedAsyncioTestCase):
    async def test_no_unverified_broadway_post(self):
        hit = detect.analyze('BLS response, general ill at 377 East Broadway, '
                             'Village of Monticello.', 'sullivan')
        with (patch.object(main, 'geocode_verify', new_callable=AsyncMock,
                           return_value=(False, False, '', None, None, '')),
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as send,
              patch.object(main, 'ops_log')):
            outcome = await main.verify_and_send('zello-sullivan', hit, Mock())
        self.assertEqual(outcome, 'suppressed')
        send.assert_not_awaited()
