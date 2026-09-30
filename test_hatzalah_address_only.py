"""Hatzalah needs a verified spoken address, not a spoken borough."""
import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect
import main

class AddressOnly(unittest.IsolatedAsyncioTestCase):
    async def check(self, phrase, point, expected):
        hit = detect.analyze(phrase, 'zello-hatzalah')
        self.assertTrue(hit['area_defaulted'])
        self.assertEqual(hit['address'], '17th Ave & 55th St, Brooklyn, NY')
        with (patch.object(main, '_intersection_point', new_callable=AsyncMock, return_value=point),
              patch('locality_gate.default_area_safe', new_callable=AsyncMock, return_value=False) as old_gate,
              patch.object(main, '_cross_streets', new_callable=AsyncMock, return_value=(None,False)),
              patch.object(main, '_map_street_names', new_callable=AsyncMock, return_value=set()),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main, '_save_recent'),
              patch.object(main, 'ops_log'),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock, return_value=True) as send):
            outcome = await main.verify_and_send('zello-hatzalah', hit, Mock())
        self.assertEqual(outcome, expected)
        old_gate.assert_not_awaited()
        if expected == 'sent':
            send.assert_awaited_once()
        else:
            send.assert_not_awaited()
            self.assertEqual(hit['hold_reason'], 'no verified location')
    async def test_17_and_55_posts_with_real_intersection(self):
        await self.check('Any units available for 17 and 55 for a trauma?', (40.626,-73.984), 'sent')
    async def test_same_dispatch_holds_if_intersection_not_real(self):
        await self.check('Any units available for 17 and 55 for a trauma?', (None,None), 'suppressed')
