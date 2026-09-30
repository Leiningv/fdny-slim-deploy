import unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
FIRST='Available for Kingston Avenue, Lincoln Place, in the restaurant for a possible anaphylaxis.'
REPEAT="15, go over to Mendy's Restaurant on Kingston Avenue, 257 Kingston. A backup unit available."
class Kingston(unittest.IsolatedAsyncioTestCase):
 def test_full_recording_retains_details(self):
  h=detect.analyze(FIRST+' '+REPEAT,'zello-hatzalah')
  self.assertEqual(h['address'],'257 Kingston Avenue, Brooklyn, NY')
  self.assertEqual(h['place'],"Mendy's Restaurant")
  self.assertEqual(h['cross'],'Lincoln Place')
  self.assertEqual(h['nature'],'Anaphylaxis')
 def test_generic_place(self):self.assertEqual(detect.analyze(FIRST,'zello-hatzalah')['place'],'restaurant')
 def test_location_repeat_never_creates_nature(self):
  self.assertIsNone(detect.analyze(REPEAT,'zello-hatzalah'))
  a=detect.extract_dispatch_address(REPEAT,'hatzolah')
  self.assertEqual(detect.extract_same_street_house(REPEAT,a),'257 Kingston Avenue, Brooklyn, NY')
 def test_other_street_house_not_inherited(self):
  self.assertEqual(detect.extract_same_street_house('Kingston Avenue, 257 Albany.','Kingston Avenue, Brooklyn, NY'),'Kingston Avenue, Brooklyn, NY')
 def test_member_not_house(self):
  self.assertEqual(detect.extract_same_street_house('K257 Kingston Avenue.','Kingston Avenue, Brooklyn, NY'),'Kingston Avenue, Brooklyn, NY')
 def test_walton_repeated_cross(self):
  h=detect.analyze('Units available for ODA and Walton, Walton and Harrison, a full trauma situation. Go to Walton Street, second floor.','zello-hatzalah')
  self.assertEqual(h['spoken_retained_cross'],'Harrison')
 def test_same_street_group_only(self):
  rec={'start':100.,'stop':105.,'address':'Kingston Avenue, Brooklyn, NY','nature':'Anaphylaxis','opener':False}
  self.assertTrue(main._ptt_group_match(rec,106.,'257 Kingston Avenue, Brooklyn, NY',8.,''))
  self.assertFalse(main._ptt_group_match(rec,106.,'257 Albany Avenue, Brooklyn, NY',8.,''))
  rec['nature']=''
  self.assertFalse(main._ptt_group_match(rec,106.,'',8.,'Anaphylaxis'))
 async def check(self,point,expected,lost=False):
  h=detect.analyze(FIRST,'zello-hatzalah')
  if lost:h['cross']=''
  with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'Kingston Avenue, Brooklyn, NY',40.67,-73.94,'Brooklyn')),
   patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=point),patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
   patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
   patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
   self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),expected)
  if expected=='sent':
   self.assertIn('C/s Lincoln Place',send.await_args.args[0]);self.assertIn('restaurant',send.await_args.args[0])
  else:send.assert_not_awaited()
 async def test_cross_carries(self):await self.check((40.67,-73.94),'sent')
 async def test_unverified_holds(self):await self.check((None,None),'suppressed')
 async def test_lost_holds(self):await self.check((40.67,-73.94),'suppressed',True)
