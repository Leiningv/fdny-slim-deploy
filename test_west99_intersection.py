import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
PHRASE='Any units on the west side for West 99 at West End Avenue for 7-year-old not feeling well. Any Westside units for West 99 at West End Avenue?'
class Parser(unittest.TestCase):
    def test_exact_at_never_house(self):
        h=detect.analyze(PHRASE,'zello-hatzalah')
        self.assertEqual(h['address'],'West 99th Street & West End Avenue, Manhattan, NY')
        self.assertTrue(h['directional_numbered_corner'])
    def test_and_repeat(self):
        h=detect.analyze(PHRASE.replace(' at ',' and '),'zello-hatzalah')
        self.assertEqual(h['address'],'West 99th Street & West End Avenue, Manhattan, NY')
    def test_manhattan_beach_stays_brooklyn(self):
        self.assertEqual(detect.get_hatzolah_area('Manhattan Beach'),'Brooklyn')
class Gate(unittest.IsolatedAsyncioTestCase):
    async def test_missing_junction_holds_not_primary_fallback(self):
        h=detect.analyze(PHRASE,'zello-hatzalah')
        with (patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),
              patch.object(main,'geocode_verify',new_callable=AsyncMock) as primary,
              patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'ops_log'),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
        primary.assert_not_awaited();send.assert_not_awaited()
class Riverside(unittest.TestCase):
    def test_spoken_pair(self):
        h=detect.analyze('Any units for the Upper West Side? West Nine-Nine at Riverside Drive for 7-year-old not feeling well.','zello-hatzalah')
        self.assertEqual(h['address'],'West 99th Street & Riverside Drive, Manhattan, NY')
        self.assertTrue(h['directional_numbered_corner'])
    def test_no_borough_has_unresolved_flag(self):
        h=detect.analyze('For West 99 at Riverside Drive.','zello-hatzalah')
        self.assertTrue(h['directional_numbered_corner']); self.assertTrue(h['area_defaulted'])
