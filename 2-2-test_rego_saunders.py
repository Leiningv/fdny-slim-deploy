import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect, main
SOURCE='Unit in Queen Trigo Park, Saunders and 64 Road, abdominal.'
class RegoSaunders(unittest.TestCase):
    def test_exact_asr_and_clear_variants(self):
        for t in [SOURCE,SOURCE.replace('Queen Trigo','Queens, Rego'),SOURCE.replace('Saunders','Saunders Street').replace('64 Road','64th Road')]:
            h=detect.analyze(t,'zello-hatzalah')
            self.assertEqual(h['address'],'Saunders Street & 64 Road, Queens, NY')
            self.assertEqual(h['nature'],'Abdominal')
            self.assertFalse(h['area_defaulted'])
    def test_no_blanket_alias_or_road_replacement(self):
        for t in [SOURCE.replace('64 Road','63rd Drive'),SOURCE.replace('Saunders','Other'),SOURCE.replace('Queen Trigo','Brooklyn, Trigo')]:
            h=detect.analyze(t,'zello-hatzalah')
            self.assertNotEqual(h and h['address'],'Saunders Street & 64 Road, Queens, NY')
        self.assertEqual(detect.get_hatzolah_area('Queen Trigo Park'),'Brooklyn')
    def test_other_feeds_unchanged(self):
        for feed in ['fdny','zello-sullivan']:
            h=detect.analyze(SOURCE,feed)
            self.assertNotEqual(h and h['address'],'Saunders Street & 64 Road, Queens, NY')
    def test_no_nature_borrowing(self):
        h=detect.analyze(SOURCE.replace('abdominal','unit responding'),'zello-hatzalah')
        self.assertFalse(h and h['nature'])
class RegoMap(unittest.IsolatedAsyncioTestCase):
    async def test_maps_unavailable_stays_unsent(self):
        h=detect.analyze(SOURCE,'zello-hatzalah')
        with (patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
        send.assert_not_awaited()
