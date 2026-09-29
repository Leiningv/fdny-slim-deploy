"""Conservative no-send checks for newly recoverable parser candidates."""
import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect
import main

class NewCandidateGates(unittest.IsolatedAsyncioTestCase):
    async def test_hatzalah_bare_grid_without_borough_or_map_stays_held(self):
        hit = detect.analyze('Hatzolah units respond, 14 and 46, child not breathing', 'zello-hatzalah')
        self.assertEqual(hit['address'], '14th Ave & 46th St, Brooklyn, NY')
        with (patch.object(main, '_intersection_point', new_callable=AsyncMock, return_value=(None,None)),
              patch('locality_gate.default_area_safe', new_callable=AsyncMock, return_value=False),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as send,
              patch.object(main, 'ops_log')):
            outcome = await main.verify_and_send('zello-hatzalah', hit, Mock())
        self.assertEqual(outcome, 'suppressed')
        self.assertEqual(hit['hold_reason'], 'ambiguous default borough')
        send.assert_not_awaited()

    async def test_sullivan_route_exit_without_verified_county_stays_held(self):
        hit = detect.analyze('Sullivan county dispatch, Beaverkill Valley, route 17 exit 104, '
                             'motor vehicle accident with possible entrapment', 'zello-sullivan')
        self.assertEqual(hit['address'], 'Route 17 at Exit 104, Sullivan Co, NY')
        with (patch.object(main, 'geocode_verify', new_callable=AsyncMock,
                           return_value=(False,False,'',None,None,'')),
              patch.object(main.control, 'muted_feeds', return_value=set()),
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock) as send,
              patch.object(main, 'ops_log')):
            outcome = await main.verify_and_send('zello-sullivan', hit, Mock())
        self.assertEqual(outcome, 'suppressed')
        self.assertEqual(hit['hold_reason'], 'no verified location')
        send.assert_not_awaited()
