import unittest
from unittest.mock import AsyncMock,Mock,patch
import main,detect,sullivan_gazetteer as gaz

class DispatchCross(unittest.IsolatedAsyncioTestCase):
    async def test_hudson_only_heard_cross(self):
        text='Any Riverdale units? Hudson Manor Terrace and West 237 for a 40-year-old abdominal pain.'
        h=detect.analyze(text,'zello-hatzalah')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'Hudson Manor Terrace, Riverdale, NY',40.89,-73.91,'Riverdale')),
              patch.object(main,'_cross_streets',new_callable=AsyncMock,return_value=('West 239th Street & West 237th Street',True)) as neighbors,
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'_load_recent',return_value=[]),
              patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'sent')
        t=send.await_args.args[0]
        self.assertIn('C/s West 237th Street',t);self.assertNotIn('239',t)
        neighbors.assert_not_awaited()
    def test_no_heard_cross_no_neighbors(self):
        h=detect.analyze('Riverdale units, for Hudson Manor Terrace, that went 237, for 40-year-old abdominal pain.','zello-hatzalah')
        self.assertFalse(h['cross'])
        self.assertNotIn('C/s',main.format_alert(h))

class GazetteerGate(unittest.TestCase):
    def test_route_suffix_protected(self):
        d,sha,roads=gaz.roads()
        r=[r for r in roads if r['name']=='Yulan Barryville Rd' and r['locality']=='Barryville'][0]
        self.assertIn('county rd 21',r['aliases']);self.assertNotIn('county rd 21a',r['aliases'])
        self.assertTrue(sha)
    def test_multiple_candidates_retained(self):
        catalog=[{'name':'Yulan Barryville Rd','locality':p,'aliases':set()} for p in ['Barryville','Yulan']]
        self.assertEqual(len(gaz.candidates('Yulin Berryville Road',catalog)),2)
    def test_corridor_exact_house(self):
        a,b,c=(0,0),(.001,0),(.002,0)
        r={'edges':{a:{b:85},b:{a:85,c:85},c:{b:85}}}
        self.assertTrue(gaz.corridor(r,[[a],[c]],b)[0])
        self.assertFalse(gaz.corridor(r,[[a],[c]],(.003,0))[0])
    def test_ambiguous_cross_holds(self):
        self.assertFalse(gaz.corridor({},[[(0,0),(1,1)],[(2,2)]],(0,0))[0])

class ShadowOnly(unittest.IsolatedAsyncioTestCase):
    async def test_missing_complaint_never_releases(self):
        h={'nature':'','address':'37 Yulin Berryville Road','excerpt':'37 Yulin Berryville Road cross streets Hickory Lane and County Road 21A.'}
        result=await gaz.shadow(h,None)
        self.assertFalse(result['release']);self.assertEqual(result['reason'],'no specific complaint')
    async def test_lookup_outage_retains_hold(self):
        h={'nature':'Cardiac Arrest','address':'37 Yulin Berryville Road','excerpt':'37 Yulin Berryville Road, cross streets Hickory Lane and County Road 21A. Cardiac arrest.'}
        before=dict(h)
        with patch.object(gaz,'roads',side_effect=RuntimeError()):
            result=await gaz.shadow(h,None)
        self.assertFalse(result['release']);self.assertEqual(h,before)
    async def test_lookup_without_session_never_releases(self):
        h={'nature':'Cardiac Arrest','address':'37 Yulin Berryville Road','excerpt':'37 Yulin Berryville Road, cross streets Hickory Lane and County Road 21A. Cardiac arrest.'}
        result=await gaz.shadow(h,None)
        self.assertFalse(result['release']);self.assertIn('lookup unavailable',result['reason'])
