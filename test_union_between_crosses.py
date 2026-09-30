import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
PHRASE='Is there an ambulance available for Union Street between Brooklyn and Kingston for a patient not feeling well?'
class BetweenCrosses(unittest.IsolatedAsyncioTestCase):
 def test_retains_bare_names_before_complaint(self):
  h=detect.analyze(PHRASE,'zello-hatzalah')
  self.assertEqual(h['address'],'Union Street, Brooklyn, NY')
  self.assertEqual(h['cross'],'Brooklyn & Kingston')
  self.assertEqual(h['spoken_three_road_crosses'],'Brooklyn & Kingston')
  self.assertEqual(h['nature'],'Not Feeling Well')
  self.assertNotIn('1374',h['address'])
 def test_reporting_stop_and_no_cross_unchanged(self):
  self.assertEqual(detect.extract_audio_crosses(PHRASE.replace('for a patient','reporting a patient')),'Brooklyn & Kingston')
  h=detect.analyze('Any units for 1339 Union Street for a patient not feeling well.','zello-hatzalah')
  self.assertFalse(h['cross']);self.assertFalse(h['spoken_between_crosses_required'])
 async def check(self,points,expected,lost=False):
  h=detect.analyze(PHRASE,'zello-hatzalah')
  if lost:h['cross']=None;h['spoken_three_road_crosses']=''
  with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'Union Street, Brooklyn, NY',40.669,-73.946,'Brooklyn')),
   patch.object(main,'_intersection_point',new_callable=AsyncMock,side_effect=points),
   patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
   patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
   patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
   self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),expected)
  if expected=='sent':self.assertIn('C/s Brooklyn & Kingston',send.await_args.args[0])
  else:send.assert_not_awaited()
 async def test_verified_pair_prints(self):await self.check([(40.669,-73.946),(40.669,-73.942)],'sent')
 async def test_unverified_cross_holds(self):await self.check([(40.669,-73.946),(None,None)],'suppressed')
 async def test_lost_pair_holds(self):await self.check([],'suppressed',True)
 async def test_same_junction_holds(self):await self.check([(40.669,-73.946),(40.669,-73.946)],'suppressed')

 def test_numbered_between_requires_spoken_pair(self):
  h=detect.analyze('Any units for 1339 Union Street between Brooklyn and New York for unresponsive?','zello-hatzalah')
  self.assertEqual(h['address'],'1339 Union Street, Brooklyn, NY')
  self.assertEqual(h['cross'],'Brooklyn & New York')
  self.assertFalse(h['placeholder_crosses_unresolved'])
  self.assertEqual(h['spoken_three_road_crosses'],'Brooklyn & New York')
 def test_existing_verified_grid_remains_whole_location(self):
  h=detect.analyze('70 units to 12 between 45 and 46 for an infant difficulty breathing.','zello-hatzalah')
  self.assertEqual(h['address'],'12th Ave between 45th & 46th St, Brooklyn, NY')
  self.assertFalse(h['spoken_between_crosses_required'])
