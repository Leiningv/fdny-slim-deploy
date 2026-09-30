import unittest
import detect
class Breather(unittest.TestCase):
    def test_explicit_dispatch_words_retained(self):
        for phrase in ['severe difficulty breather','severe deep breather','severe breather','very big breather']:
            self.assertEqual(detect.get_nature('Any units for Surf Avenue and West5th for a '+phrase,'hatzolah'),detect._addr_title(phrase))
        self.assertEqual(detect.get_nature('We have a severe deep breather Surf and West pit','hatzolah'),'Severe Deep Breather')
    def test_no_bare_training_or_negative_promotion(self):
        for t in ['severe breather','unit breather','for training severe breather','we have no severe breather','for a negative severe deep breather']:
            self.assertFalse(detect.get_nature(t,'hatzolah'))
    def test_other_feeds_unchanged(self):
        self.assertFalse(detect.get_nature('for a severe breather','fdny'))
    def test_location_words_not_rewritten(self):
        for t in ['We have a severe deep breather surf and west pit','We have a severe breather surf and west end']:
            h=detect.analyze('Any units in Coney Island? '+t,'zello-hatzalah')
            self.assertTrue(h)
            self.assertNotIn('5th',h['address'])
from unittest.mock import AsyncMock,Mock,patch
import main
class BreatherMap(unittest.IsolatedAsyncioTestCase):
    async def test_unverified_location_still_unsent(self):
        h=detect.analyze('Any units in Coney Island? We have a severe deep breather Surf and West pit','zello-hatzalah')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),
              patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'ops_log'),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
        send.assert_not_awaited()
