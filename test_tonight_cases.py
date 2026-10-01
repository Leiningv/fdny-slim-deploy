import unittest
from unittest.mock import AsyncMock,patch
import detect,main,fdny_borough_gate as b
class Cases(unittest.TestCase):
 def test_mixed_cardiac(self):
  t='Any units in the B for 52nd Street 16 to 17 for lifeline call? B78 52nd 16 to 17. Any units in the B 43rd Street 15 to 16 for the cardiac? 239 236 239 236 43rd Street 15 to 16. And 289'
  hs=[detect.analyze(z,'zello-hatzalah') for z in detect.split_dispatch_jobs(t,'zello-hatzalah')];self.assertEqual(len(hs),2);self.assertEqual([h['nature'] for h in hs],['Lifeline Call','Cardiac']);self.assertTrue(hs[1]['address'].startswith('43rd Street between'))
 def test_burn(self):self.assertEqual(detect.analyze('Any units in Staten Island for East Main Street for a burn to a 1-year-old.','zello-hatzalah')['nature'],'Burn')
 def test_fracture(self):self.assertEqual(detect.get_nature('For 187th Street Union Turnpike possible fracture ten year old','hatzolah'),'Possible Fracture')
 def test_exposure(self):self.assertFalse(b.unnumbered_with_spoken_building('Fire on fourth floor. Exposure 1 is the street, 2 an alley.','FDNY Box 2105, Brooklyn, NY'))
 def test_prefix(self):self.assertNotIn('Fire',detect.analyze('175, fire broken. Box 1736 1040 code 1 we shut gas off to only apartment third floor 10-8.','fdny')['nature'])
 def test_broadway(self):h=detect.analyze('Sullivan dispatch Monticello activated fire alarm 498 Broadway Broadway Bowling.','zello-sullivan');self.assertEqual(h['address'],'498 Broadway, Monticello, NY')
 def test_gi_corridor(self):h=detect.analyze('Any units for 14th Avenue 50th to 51st for GI distress? 275 275 is a three-year-old severe abdominal.','zello-hatzalah');self.assertTrue(h['address'].startswith('14th Avenue between 50th & 51st'))
 def test_queens_ack_not_house(self):h=detect.analyze('Any Queens units for 78th Avenue between Main Street and 147 for a 70-year-old general illness? Queens 135 78th Avenue147 to Main.','zello-hatzalah');self.assertEqual(h['address'],'78th Avenue, Queens, NY');self.assertEqual(h['spoken_three_road_crosses'],'Main Street & 147th Street')
 def test_19th(self):h=detect.analyze('Any units for 19th Avenue and 49th Road near ShopRite for a 50-year-old not feeling well? Queens 149, the intersection of 19th and 49th Road.','zello-hatzalah');self.assertTrue(h['address'].startswith('19th Avenue & 49th Road'))
 def test_wire(self):self.assertEqual(detect.get_nature('Box 2756 8314 10th Avenue for wires burning on private dwelling','fdny'),'Wires Burning')
 def test_woodmere_unit_repeats(self):
  import audio_review
  t='Units available for Woodmere Boulevard and Central Avenue. 159 Woodmere Boulevard and Central Avenue. 159. 115 Woodmere Boulevard and Central. 115.'
  h=detect.analyze(t,'zello-hatzalah');self.assertEqual(h['address'],'Woodmere Boulevard, Woodmere, NY');self.assertEqual(h['direct_cross_candidate'],'Central Avenue');self.assertFalse(audio_review.mixed(t,'zello-hatzalah'));self.assertFalse(h['nature'])
 def test_real_houses_keep_mixed(self):
  import audio_review
  t='Units available for Woodmere Boulevard and Central Avenue. 159 Woodmere Boulevard for trauma. 115 Woodmere Boulevard for chest pain.'
  self.assertTrue(audio_review.mixed(t,'zello-hatzalah'))
 def test_gas_basement(self):
  self.assertEqual(detect.get_nature('Box 3172 526 East 78th Street for odor of gas in the basement','fdny'),'Odor of Gas in the Basement')
 def test_negated_gas_basement(self):
  self.assertNotEqual(detect.get_nature('No odor of gas in the basement','fdny'),'Odor of Gas in the Basement')
 def test_cardiac_arrest_not_shortened(self):
  self.assertEqual(detect.get_nature('for a cardiac arrest','hatzolah'),'Cardiac Arrest')
 def test_exact_gi(self):
  t='Any listen to me for 14th Avenue, 50th to 51st, GI distress. 275. 275, it is a 3-year-old, severe abdominal, 14th Avenue, 50 to 51. B54 is on the corner. 54.'
  h=detect.analyze(t,'zello-hatzalah');self.assertEqual(h['address'],'14th Avenue between 50th & 51st Street, Brooklyn, NY');self.assertEqual(h['cross'],'50th & 51st Street')
 def test_exact_fracture_cross_not_unit(self):
  t='Available for fresh metals, 187th Street off of Union Turnpike for possible fracture, 10-year-old. 85, it is 187th Street, 75th Avenue, Union Turnpike. 85. 85 with K54.'
  h=detect.analyze(t,'zello-hatzalah');self.assertEqual(h['cross'],'75th Avenue & Union Turnpike');self.assertFalse(h['address'].startswith('85 '));self.assertTrue(h['area_defaulted'])
class Wiring(unittest.IsolatedAsyncioTestCase):
 async def test_success_no_google(self):
  with patch.dict(main.os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'1'}),patch.object(main,'_osm_intersection_point',new_callable=AsyncMock,return_value=(40.69,-73.94)),patch('google_intersection.lookup',new_callable=AsyncMock) as g:
   self.assertEqual(await main._intersection_point('Tompkins Avenue & Myrtle Avenue, Brooklyn, NY','Myrtle Avenue'),(40.69,-73.94));g.assert_not_awaited()
 async def test_failed_uses_exact(self):
  with patch.dict(main.os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'1'}),patch.object(main,'_osm_intersection_point',new_callable=AsyncMock,return_value=(None,None)),patch('google_intersection.lookup',new_callable=AsyncMock,return_value=(40.69,-73.94)) as g:
   self.assertEqual(await main._intersection_point('Tompkins Avenue & Myrtle Avenue, Brooklyn, NY','Myrtle Avenue'),(40.69,-73.94));g.assert_awaited_once()

 async def test_off_path_unchanged(self):
  with patch.dict(main.os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'0'}),patch.object(main,'_osm_intersection_point',new_callable=AsyncMock,return_value=(None,None)) as o,patch('google_intersection.lookup',new_callable=AsyncMock) as g:
   await main._intersection_point('Tompkins Avenue & Myrtle Avenue, Brooklyn, NY','Myrtle Avenue');o.assert_awaited_once();g.assert_not_awaited()
 async def test_untyped_no_google(self):
  with patch.dict(main.os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'1'}),patch.object(main,'_osm_intersection_point',new_callable=AsyncMock,return_value=(None,None)),patch('google_intersection.lookup',new_callable=AsyncMock) as g:
   await main._intersection_point('Tompkins Avenue, Brooklyn, NY','Myrtle');g.assert_not_awaited()

 async def test_bare_typed_roads_compose_exact(self):
  with patch.dict(main.os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'1'}),patch.object(main,'_osm_intersection_point',new_callable=AsyncMock,return_value=(None,None)),patch('google_intersection.lookup',new_callable=AsyncMock,return_value=None) as g:
   self.assertEqual(await main._intersection_point('15th Avenue, Brooklyn, NY','40th Street'),(None,None));g.assert_awaited_once_with('15th Avenue & 40th Street, Brooklyn, NY',timeout=1.5)

 async def test_grid_street_between_avenues(self):
  class Response:
   status=200
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   async def json(self):return {'address':{'county':'Kings County','state':'New York'}}
  class Session:
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   def get(self,*a,**k):return Response()
  h=detect.analyze('Any units in the B 43rd Street 15 to 16 for the cardiac?','zello-hatzalah')
  with patch.object(main,'_intersection_point',new_callable=AsyncMock,side_effect=[(40.63,-73.98),(40.63,-73.981)]),patch.object(main.aiohttp,'ClientSession',return_value=Session()):
   self.assertIsNotNone(await main._hatzalah_brooklyn_grid_corridor(h))
 async def test_grid_same_point_not_a_corridor(self):
  h=detect.analyze('Any units in the B 43rd Street 15 to 16 for the cardiac?','zello-hatzalah')
  with patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(40.63,-73.98)):
   self.assertIsNone(await main._hatzalah_brooklyn_grid_corridor(h))
 async def test_grid_queens_never_kings_inference(self):
  h=detect.analyze('Any Queens units for 43rd Street 15 to 16 for the cardiac?','zello-hatzalah')
  with patch.object(main,'_intersection_point',new_callable=AsyncMock) as o:
   self.assertIsNone(await main._hatzalah_brooklyn_grid_corridor(h));o.assert_not_awaited()
