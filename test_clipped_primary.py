import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
CLIP="Street off of Bedford Avenue, for a fire on the second floor. Ladder147 responding."
class Clipped(unittest.TestCase):
    def test_cross_only_prefixes(self):
        for t in [CLIP,'Off of Bedford Avenue, fire second floor','Street off Bedford Avenue, fire','Road off of Main Street for smoke']:
            self.assertTrue(detect.fdny_clipped_cross_only(t))
    def test_complete_primary_and_dispatch_unchanged(self):
        for t in ['48 Martense Street off of Bedford Avenue for fire second floor',
                  'Phone Alarm box1552 48 Martense Street off of Bedford Avenue for fire',
                  'Bedford Avenue at Martense Street automatic alarm',
                  'Phone alarm box609 Hanson Place off of South Elliott Place automatic alarm']:
            self.assertFalse(detect.fdny_clipped_cross_only(t))
class SendBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_cross_only_never_geocodes_or_sends(self):
        h=detect.analyze(CLIP,'fdny')
        self.assertTrue(h)
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock) as geo,
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('fdny',h,Mock()),'suppressed')
        self.assertIn('clipped primary',h['hold_reason']);geo.assert_not_awaited();send.assert_not_awaited()
