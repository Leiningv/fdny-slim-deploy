import unittest
import detect
class HighPulse(unittest.TestCase):
    def test_compound_spoken_order_and_singles(self):
        for t in ['generally ill, high heart rate','generally ill high pulse rate','high pulse rate and generally ill','high heart rate','high pulse rate']:
            self.assertEqual(detect.get_nature('27-year-old male '+t+', BLS response','sullivan'),detect._addr_title(t))
    def test_no_stitching(self):
        self.assertNotEqual(detect.get_nature('generally ill. Another job high pulse rate','sullivan'),'Generally Ill High Pulse Rate')
    def test_negated_training_not_promoted(self):
        for p in ['no ','negative ','training ']:
            self.assertFalse(detect.get_nature(p+'high heart rate','sullivan'))
    def test_no_diagnosis_or_acronym_invention(self):
        self.assertEqual(detect.get_nature('high pulse rate','sullivan'),'High Pulse Rate')
        self.assertNotIn('tachy',detect.get_nature('high pulse rate','sullivan').lower())
    def test_other_feeds_unchanged(self):
        self.assertFalse(detect.get_nature('high pulse rate','hatzolah'))
from unittest.mock import AsyncMock,Mock,patch
import main
class PulseMap(unittest.IsolatedAsyncioTestCase):
    async def test_unverified_road_still_held(self):
        h=detect.analyze('Bethel BLS response 27-year-old male generally ill high heart rate 200 Herd Road','zello-sullivan')
        self.assertEqual(h['nature'],'Generally Ill High Heart Rate')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'ops_log'),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-sullivan',h,Mock()),'suppressed')
        send.assert_not_awaited()
