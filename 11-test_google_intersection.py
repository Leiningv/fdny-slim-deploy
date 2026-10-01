import copy,unittest,os,asyncio
from unittest.mock import patch
import google_intersection as g
Q='Tompkins Avenue & Myrtle Avenue, Brooklyn, NY'
def payload():
 return {'status':'OK','results':[{'types':['intersection'],'address_components':[{'long_name':'Myrtle Avenue & Tompkins Avenue','types':['intersection']},{'long_name':'Brooklyn','types':['political','sublocality']},{'long_name':'New York','types':['political','administrative_area_level_1']}],'geometry':{'location_type':'GEOMETRIC_CENTER','location':{'lat':40.6957144,'lng':-73.946369}}}]}
class Exact(unittest.TestCase):
 def test_exact(self):self.assertEqual(g.exact_result(Q,payload()),(40.6957144,-73.946369))
 def test_wrong_road(self):self.assertIsNone(g.exact_result(Q.replace('Myrtle','Atlantic'),payload()))
 def test_wrong_borough(self):self.assertIsNone(g.exact_result(Q.replace('Brooklyn','Queens'),payload()))
 def test_single_road(self):self.assertIsNone(g.exact_result('Tompkins Avenue, Brooklyn, NY',payload()))
 def test_house(self):self.assertIsNone(g.query('12 Tompkins Avenue & Myrtle Avenue, Brooklyn, NY'))
 def test_partial(self):p=payload();p['results'][0]['partial_match']=True;self.assertIsNone(g.exact_result(Q,p))
 def test_street_centroid(self):p=payload();p['results'][0]['types']=['route'];self.assertIsNone(g.exact_result(Q,p))
 def test_multiple(self):p=payload();p['results']*=2;self.assertIsNone(g.exact_result(Q,p))
 def test_empty(self):self.assertIsNone(g.exact_result(Q,{'status':'ZERO_RESULTS'}))
 def test_suffix_ordinals(self):self.assertEqual(g.canon('40th St'),g.canon('40 Street'))
 def test_typed_query(self):self.assertEqual(g.query('15th Avenue & 40th Street, Brooklyn, NY')[2],'15th Avenue and 40th Street, Brooklyn, NY')
class Gate(unittest.IsolatedAsyncioTestCase):
 async def test_off_no_network(self):
  with patch.dict(os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'0'}),patch.object(g.aiohttp,'ClientSession') as s:
   self.assertIsNone(await g.lookup(Q));s.assert_not_called()
 async def test_missing_key_no_network(self):
  with patch.dict(os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'1','GOOGLE_GEOCODING_API_KEY':''}),patch.object(g.aiohttp,'ClientSession') as s:
   self.assertIsNone(await g.lookup(Q));s.assert_not_called()
 async def test_network_failure_holds(self):
  with patch.dict(os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'1','GOOGLE_GEOCODING_API_KEY':'test-key'}),patch.object(g.aiohttp,'ClientSession',side_effect=OSError('offline')):
   self.assertIsNone(await g.lookup(Q))
 async def test_timeout_holds(self):
  async def slow(coro,timeout):
   coro.close()
   raise asyncio.TimeoutError()
  with patch.dict(os.environ,{'GOOGLE_EXACT_INTERSECTION_FALLBACK':'1','GOOGLE_GEOCODING_API_KEY':'test-key'}),patch.object(g.asyncio,'wait_for',side_effect=slow):
   self.assertIsNone(await g.lookup(Q))
