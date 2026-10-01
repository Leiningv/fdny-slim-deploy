import unittest
from unittest.mock import patch,AsyncMock,Mock
import detect,main
TEXT='Phone Alarm Box 570, Baltic Street and Bond Street for an explosion. Phone Alarm 570, Baltic Street and Bond Street for an explosion.'
class Exact(unittest.TestCase):
 def test_owner_confirmed_case(self):
  h=detect.analyze(TEXT,'fdny');self.assertEqual(h['nature'],'Explosion');self.assertEqual(h['address'],'Baltic Street & Bond Street, Brooklyn, NY');self.assertEqual(h['box_heard'],'0570')
 def test_report_of(self):self.assertEqual(detect.get_nature('Box 570 Baltic Street and Bond Street for report of an explosion in the area.','fdny'),'Explosion')
 def test_no_unsupported_explosion(self):self.assertNotEqual(detect.get_nature('Box 570 Baltic Street for no explosion.','fdny'),'Explosion')
 def test_unit_chatter(self):self.assertNotEqual(detect.get_nature('Unit discusses explosion training.','fdny'),'Explosion')
 def test_two_boxes_not_one_corner(self):self.assertIsNone(detect.fdny_spoken_road_pair(TEXT+' Box 364 Tompkins Avenue and Myrtle Avenue for an accident.'))
 def test_two_pairs_same_box_not_one_corner(self):self.assertIsNone(detect.fdny_spoken_road_pair(TEXT+' Box 570 Tompkins Avenue and Myrtle Avenue for an accident.'))
 def test_tompkins_located_at_owns_pair(self):
  h=detect.analyze('Brooklyn 5-7 Signal Box 364, located at Tompkins Avenue and Myrtle Avenue for car accident.','fdny');self.assertEqual(h['address'],'Tompkins Avenue & Myrtle Avenue, Brooklyn, NY')
 def test_numbered_bond_updated_dispatch(self):
  text="Phone Alarm, Box 570, 198 Bond Street, that's Warren Street to Baltic Street for an explosion. Phone Alarm, 570, 198 Bond Street, Warren Street to Baltic Street for an explosion."
  h=detect.analyze(text,'fdny');self.assertEqual(h['nature'],'Explosion');self.assertEqual(h['address'],'198 Bond Street, Brooklyn, NY');self.assertEqual(h['cross'],'Warren Street & Baltic Street');self.assertEqual(h['box_heard'],'0570')
class Holds(unittest.IsolatedAsyncioTestCase):
 async def test_unverified_corner_never_sends(self):
  h=detect.analyze(TEXT,'fdny')
  with (patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),patch.object(main,'_load_box_cache',return_value={}),patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
   result=await main.verify_and_send('fdny',h,Mock(),prepare_only=True)
  self.assertEqual(result,'suppressed');send.assert_not_awaited()
