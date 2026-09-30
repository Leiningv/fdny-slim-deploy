import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
BELT="Phone Alarm Box 8626, it's East 29th Street and the Belt Parkway, odor of smoke in the area. Phone Alarm 8626, Belt Parkway, it's East 29th Street and the Belt Parkway for a smoke in the area."
GAS='Phone Alarm, Box 3547, West 19th Street, Mermaid Avenue, odor of gas in the area. Phone Alarm, 3547, West 19th Street, Mermaid Avenue, odor of gas in the area.'
class Extraction(unittest.TestCase):
    def test_belt_both_roads(self):
        h=detect.analyze(BELT,'fdny');self.assertEqual(h['address'],'East 29th Street & Belt Parkway, Brooklyn, NY');self.assertEqual(h['box_heard'],'8626')
    def test_mermaid_retained(self):
        h=detect.analyze(GAS,'fdny');self.assertEqual(h['address'],'West 19th Street & Mermaid Avenue, Brooklyn, NY')
    def test_two_boxes_no_pair(self):
        self.assertFalse(detect.fdny_spoken_road_pair(BELT+' Box 1234 100 Henry Street smoke'))
    def test_spoken_box_not_silently_erased(self):
        h=detect.analyze(BELT,'fdny');text=main.format_alert(h)
        self.assertIn('Box 8626 (heard; location not corroborated)',text)
    def test_no_box_invented(self):
        self.assertNotIn('Box',main.format_alert({'source':'fdny','address':'West Street','nature':'Smoke'}))
class Verification(unittest.IsolatedAsyncioTestCase):
    async def test_unverified_pair_cannot_print_or_send(self):
        h=detect.analyze(BELT,'fdny')
        with (patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),
              patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),
              patch.object(main,'_load_box_cache',return_value={}),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            result=await main.verify_and_send('fdny',h,Mock(),prepare_only=True)
        self.assertEqual(result,'suppressed');send.assert_not_awaited()
    async def test_verified_pair_preserved_without_inferred_house(self):
        h=detect.analyze(GAS,'fdny')
        with (patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(40.57,-73.98)),
              patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[('W 19 ST at MERMAID AVE','Brooklyn')]),
              patch.object(main,'_load_box_cache',return_value={}),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            result=await main.verify_and_send('fdny',h,Mock(),prepare_only=True)
        self.assertEqual(result,'verified');self.assertEqual(h['address'],'West 19th Street & Mermaid Avenue, Brooklyn, NY');send.assert_not_awaited()
