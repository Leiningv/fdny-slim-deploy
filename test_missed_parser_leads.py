import unittest
from unittest.mock import patch,AsyncMock,Mock
import detect,main
from fdny_borough_gate import spoken_borough_conflict
class Parser(unittest.TestCase):
 def test_rockaway(self):
  t='Any R units available to load up a bus to head to Rockaway Beach Boulevard and Beach 80th for a patient with chest pain?'
  h=detect.analyze(t,'hatzolah');self.assertEqual(h['address'],'Rockaway Beach Boulevard, Queens, NY');self.assertEqual(h['direct_cross_candidate'],'Beach 80th');self.assertEqual(h['nature'],'Chest Pain')
 def test_kingston_tail(self):
  h=detect.analyze('Any units head to Kingston and Montgomery, trauma. PH79 head over to Kingston and Montgomery, the Crown.','hatzolah')
  self.assertEqual(h['address'],'Kingston & Montgomery, Brooklyn, NY');self.assertEqual(h['nature'],'');self.assertFalse(h['direct_cross_candidate'])
 def test_mental_health(self):
  h=detect.analyze('Dispatch Woodburn 12 Stangle Drive female mental health BLS response','sullivan');self.assertEqual(h['nature'],'Mental Health');self.assertEqual(h['address'],'12 Stangle Drive, Sullivan Co, NY')
  self.assertFalse(detect.get_nature('female no mental health BLS response','sullivan'))
  self.assertFalse(detect.get_nature('mental health training at the station','sullivan'))
 def test_grand_primary(self):
  h=detect.analyze('Brooklyn box 258679 Grand Street Manhattan Avenue to Graham Avenue motor vehicle accident','fdny')
  self.assertEqual(h['address'],'679 Grand Street, Brooklyn, NY');self.assertEqual(h['cross'],'Manhattan Avenue & Graham Avenue')
  self.assertEqual(spoken_borough_conflict('679 Grand Street, Manhattan Avenue to Graham Avenue',h['address']),'')
  self.assertEqual(spoken_borough_conflict('679 Grand Street, Manhattan',h['address']),'Manhattan')
class Gated(unittest.IsolatedAsyncioTestCase):
 async def test_kingston_unverified_held(self):
  h=detect.analyze('Any units head to Kingston and Montgomery, trauma.','hatzolah')
  with patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'):
   self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock(),prepare_only=True),'suppressed')
 async def test_sullivan_unknown_spelling_held(self):
  h=detect.analyze('Dispatch Woodburn 12 Spangle Drive female mental health BLS response','sullivan')
  with patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'):
   self.assertEqual(await main.verify_and_send('sullivan',h,Mock(),prepare_only=True),'suppressed')
