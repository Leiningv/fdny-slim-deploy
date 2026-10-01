import unittest
from unittest.mock import AsyncMock,patch,Mock
import detect,audio_review,main
OLD='Sullivan County Dispatch to Monticello Fire, second call, odor of smoke in the area of Cottage Street and Lanfield Avenue. For Monticello, a second call, odor of smoke from the area of Cottage Street and Lanfield Avenue. 542.'
NEW='Holden dispatch to Monticello. Possible structure fire, odor of smoke in the area of Cottage Street and Lanfield Avenue. For Monticello, possible structure fire, odor of smoke in the area of Cottage Street and Lanfield Avenue. 544.'
class CottageCases(unittest.TestCase):
 def test_exact_recordings(self):
  for text,nature,priority in [(OLD,'Smoke in the area',False),(NEW,'Possible Structure Fire',True)]:
   h=detect.analyze(text,'zello-sullivan')
   self.assertFalse(audio_review.mixed(text,'zello-sullivan'))
   self.assertEqual(h['address'],'Cottage Street & Landfield Avenue, Monticello, NY')
   self.assertEqual(h['nature'],nature);self.assertEqual(h['priority'],priority)
 def test_real_mixed_holds(self):
  variants=[OLD.replace('For Monticello, a second call, odor of smoke from the area of Cottage Street','For Monticello, a second call, odor of smoke from the area of Oak Street'),OLD.replace('For Monticello, a second call, odor of smoke','For Monticello, a second call, seizures'),OLD+' Third call, 60 Haddock Road, difficulty breathing.', '414 Broadway, seizures. '+OLD,OLD.replace('For Monticello, a second call','For Monticello, a third call'),OLD+' Another job, Cottage Street, smoke.',OLD+' First call, 414 Broadway, seizure.']
  for t in variants:self.assertTrue(audio_review.mixed(t,'zello-sullivan'),t)
 def test_spelling_is_corner_scoped(self):
  for t in [NEW.replace('Cottage Street','Oak Street'),NEW.replace('Monticello','Liberty')]:
   h=detect.analyze(t,'zello-sullivan');self.assertNotIn('Landfield',h['address'])
 def test_normal_fire_unchanged(self):
  self.assertEqual(detect.analyze(NEW.replace('Possible structure fire','Structure fire').replace('possible structure fire','structure fire'),'zello-sullivan')['nature'],'Structure Fire')
class FinalBoundary(unittest.IsolatedAsyncioTestCase):
 async def test_prepare_without_any_post(self):
  for t,n in [(OLD,'Smoke in the area'),(NEW,'Possible Structure Fire')]:
   h=detect.analyze(t,'zello-sullivan')
   with patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(41.657915,-74.685148)),patch.object(main,'_sullivan_point_area',new_callable=AsyncMock,return_value='Monticello'),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
    r=await main.verify_and_send('zello-sullivan',h,Mock(),prepare_only=True)
   self.assertEqual(r,'verified');send.assert_not_awaited();self.assertEqual(h['nature'],n);self.assertIn('Landfield',h['address'])
class AdditionalSafety(unittest.IsolatedAsyncioTestCase):
 async def test_failed_county_remains_held(self):
  h=detect.analyze(NEW,'zello-sullivan')
  with patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(41.657915,-74.685148)),patch.object(main,'_sullivan_point_area',new_callable=AsyncMock,return_value=''),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send:
   self.assertEqual(await main.verify_and_send('zello-sullivan',h,Mock(),prepare_only=True),'suppressed')
  send.assert_not_awaited();self.assertEqual(h['hold_reason'],'no verified location')
 def test_added_complaint_or_clipped_tail_held(self):
  for t in [OLD.replace('odor of smoke in','seizures and odor of smoke in'),OLD+' patient fell.',OLD.replace('For Monticello','For Liberty'),OLD+' 888 Resorts World, diabetic emergency.']:
   self.assertTrue(audio_review.mixed(t,'zello-sullivan'),t)
 async def test_reverse_county_town_and_failures(self):
  cases=[(200,{'county':'Sullivan County','state':'New York','village':'Monticello'},'Monticello'),(200,{'county':'Orange County','state':'New York','village':'Monticello'},''),(200,{'county':'Sullivan County','state':'New Jersey','village':'Monticello'},''),(200,{'county':'Sullivan County','state':'New York','village':'Liberty'},''),(503,{},'')]
  for status,area,expected in cases:
   response=AsyncMock();response.status=status;response.json.return_value={'address':area}
   request=Mock();request.__aenter__=AsyncMock(return_value=response);request.__aexit__=AsyncMock(return_value=False)
   session=Mock();session.get.return_value=request
   ctx=Mock();ctx.__aenter__=AsyncMock(return_value=session);ctx.__aexit__=AsyncMock(return_value=False)
   with patch.object(main.aiohttp,'ClientSession',return_value=ctx):
    self.assertEqual(await main._sullivan_point_area(41.657915,-74.685148,'Cottage Street & Landfield Avenue, Monticello, NY'),expected)
