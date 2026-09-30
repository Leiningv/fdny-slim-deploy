import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect, main
class Pressure(unittest.TestCase):
    def test_spoken_order_and_singles(self):
        for t in ['low blood pressure, dehydrated','dehydrated and low blood pressure','low blood pressure','dehydrated']:
            self.assertEqual(detect.get_nature('47-year-old female '+t+', ALS response','sullivan'),detect._addr_title(t))
    def test_no_stitching(self):
        self.assertEqual(detect.get_nature('low blood pressure. Another job dehydrated','sullivan'),'Low Blood Pressure')
    def test_negated_training_not_promoted(self):
        for p in ['no ','negative ','training ']:
            self.assertFalse(detect.get_nature(p+'low blood pressure, dehydrated','sullivan'))
    def test_no_inferred_diagnosis(self):
        n=detect.get_nature('47-year-old female low blood pressure dehydrated','sullivan')
        self.assertNotIn('hypotension',n.lower());self.assertNotIn('shock',n.lower())
class Map(unittest.IsolatedAsyncioTestCase):
    async def test_road_remains_map_gated(self):
        h=detect.analyze('Liberty Command ALS response 47-year-old female low blood pressure dehydrated 39 Old Monticello Road','zello-sullivan')
        self.assertEqual(h['nature'],'Low Blood Pressure Dehydrated')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-sullivan',h,Mock()),'suppressed')
        send.assert_not_awaited()
