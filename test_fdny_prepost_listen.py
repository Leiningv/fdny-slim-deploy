"""FDNY complaint and map-verified spoken cross regressions."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import detect
import main

LAFAYETTE_PRIMARY = ('Looking at 235. 235. Yeah, phone alarm, 653, '
                     '362 Lafayette Avenue, Class 1, smoke on the number one floor. '
                     '235, 10-4, responding.')
LAFAYETTE_SECOND = ('Phone Alarm Box 653, 362 Lafayette Avenue, '
                    'Classon and Grand Avenue, smoke on the number one floor.')
COOPER_PRIMARY = ('Phone alarm box 536, 36 Cooper Street, Bushwick Avenue to Broadway, '
                  'odor of gas.')


class NatureParsing(unittest.TestCase):
    def test_lafayette_preserves_spoken_smoke_floor(self):
        hit = detect.analyze(LAFAYETTE_PRIMARY, 'fdny')
        self.assertEqual(hit['nature'], 'Smoke on the Number One Floor')
        self.assertEqual(hit['address'], '362 Lafayette Avenue, Brooklyn, NY')
        self.assertIsNone(hit['cross'])
        self.assertEqual(detect.analyze(LAFAYETTE_SECOND, 'fdny')['cross'],
                         'Classon & Grand Avenue')

    def test_cooper_gas_precedes_phone_alarm(self):
        hit = detect.analyze(COOPER_PRIMARY, 'fdny')
        self.assertEqual(hit['nature'], 'Odor of Gas')
        self.assertEqual(hit['cross'], 'Bushwick Avenue & Broadway')
        self.assertEqual(detect.get_nature('Phone Alarm 36 Cooper Street, no smoke on the '
                                           'number one floor', 'fdny'), '')


class FDNYCrossDisplay(unittest.IsolatedAsyncioTestCase):
    async def test_2435_audio_box_and_abbreviated_crosses(self):
        # The earlier primary ASR read 9235; the user's recorded dispatch
        # twice says Box 2435. This validates the independent reading only;
        # any future box rewrite needs an explicit matching source/map gate.
        phrase = ('Unassigned class 3 Brooklyn box 2435 479 East 29th Street, '
                  'Foster to Newkirk Avenue is automatic alarm.')
        hit = detect.analyze(phrase, 'fdny')
        self.assertEqual(hit['box_heard'], '2435')
        self.assertEqual(hit['cross'], 'Foster & Newkirk Avenue')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,
                           return_value=(True,False,'479 EAST 29 STREET, Brooklyn, NY',
                                         40.638728,-73.948985,'Brooklyn')),
              patch('spoken_cross.verify',new_callable=AsyncMock,return_value=True) as check,
              patch.object(main,'_box_lookup',new_callable=AsyncMock,
                           return_value=[('Foster Ave & E 29 St','Brooklyn')]),
              patch.object(main,'_load_box_cache',return_value={}),
              patch.object(main,'_nearest_box',new_callable=AsyncMock,
                           return_value=('2435','Foster Ave & E 29 St',30)),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'_save_recent'),
              patch.object(main,'_ensure_ogg',return_value=None),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send,
              patch.object(main,'ops_log'),patch.object(main,'_uguu_upload',new_callable=AsyncMock)):
            await main.verify_and_send('fdny',hit,Mock(),'',fresh_ts=None)
        self.assertEqual(send.await_count, 1, hit.get('hold_reason'))
        text=send.await_args.args[0]
        self.assertIn('2435',text)
        self.assertIn('Foster Avenue',text)
        self.assertIn('Newkirk Avenue',text)
