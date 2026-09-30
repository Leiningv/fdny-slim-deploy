import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
class OceanStitch(unittest.TestCase):
 def test_one_dispatch_placeholder_crosses_hold_before_maps(self):
  s='Are units available for Ocean Parkway between X and Y for a patient not feeling well?'
  h=detect.analyze(s,'zello-hatzalah')
  self.assertEqual((h['nature'],h['address']),('Not Feeling Well','Ocean Pkwy, Brooklyn, NY'))
  self.assertTrue(h['placeholder_crosses_unresolved']);self.assertFalse(h['cross'])
 def test_real_and_placeholder_cross_still_retain_known_shape(self):
  self.assertTrue(detect.analyze('Any units for Union Street between Brooklyn and Kingston for a patient not feeling well?','zello-hatzalah')['cross'])
 def test_ptt_location_cannot_receive_later_nature_fragment(self):
  rec={'start':100.,'stop':105.,'address':'Ocean Pkwy, Brooklyn, NY','nature':'','opener':True}
  self.assertFalse(main._ptt_group_match(rec,106.,'',8.,'Not Feeling Well'))
 def test_same_location_can_receive_matching_repeat_nature(self):
  rec={'start':100.,'stop':105.,'address':'','nature':'Not Feeling Well','opener':True}
  self.assertTrue(main._ptt_group_match(rec,106.,'Ocean Pkwy, Brooklyn, NY',8.,''))
class FinalGate(unittest.IsolatedAsyncioTestCase):
 async def test_placeholder_between_never_sends_street_only(self):
  h=detect.analyze('Are units available for Ocean Parkway between X and Y for a patient not feeling well?','zello-hatzalah')
  with (patch.object(main,'geocode_verify',new_callable=AsyncMock) as geo,patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
   self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
  self.assertEqual(h['hold_reason'],'spoken between crosses unresolved during transcription');send.assert_not_awaited();geo.assert_not_awaited()
