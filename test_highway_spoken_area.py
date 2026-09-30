import unittest
from unittest.mock import patch,AsyncMock,Mock
import detect,main
from highway_area import spoken_area
class Areas(unittest.TestCase):
 def test_exact_anchors(self):
  for location in ['Gowanus Expressway near Exit 17, 92 Street westbound','Gowanus Expressway between Exit 22 and 23 westbound','Belt Parkway in the area of 92 Street','BQE northbound','Gowanus Expressway between exit22 and23 westbound']:
   h=detect.analyze(location+' for auto accident','fdny')
   self.assertEqual(h['spoken_highway_area'],location)
   self.assertTrue(h['address'].startswith(location))
   self.assertFalse(h['cross'])
 def test_rejections(self):
  for t in ['Gowanus Expressway for auto accident','Gowanus Expressway in the area of something for car fire','Gowanus Expressway in the area of unknown westbound for auto accident','maybe Gowanus Expressway near Exit 17 for auto accident','501 West Avenue at Gowanus Expressway westbound for auto accident']:
   self.assertFalse(spoken_area(t))
class Sender(unittest.IsolatedAsyncioTestCase):
 async def test_no_map_only_for_original_spoken_area(self):
  text='Gowanus Expressway near Exit 17, 92 Street westbound for auto accident'
  hit=detect.analyze(text,'fdny')
  with patch.object(main,'geocode_verify',new_callable=AsyncMock) as geo,patch.object(main,'_box_lookup',new_callable=AsyncMock) as box,patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'):
   result=await main.verify_and_send('fdny',hit,Mock(),prepare_only=True,source_call={'transcription':text})
   self.assertEqual(result,'verified');geo.assert_not_awaited();box.assert_not_awaited()
 async def test_ordinary_street_still_map_gated(self):
  hit=detect.analyze('Box 1234 501 West Avenue auto accident','fdny')
  with patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')) as geo,patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'):
   self.assertEqual(await main.verify_and_send('fdny',hit,Mock(),prepare_only=True),'suppressed');geo.assert_awaited()
