import time, os, unittest
from unittest.mock import AsyncMock, Mock, patch
import detect, main
class Locality(unittest.TestCase):
    def test_observed_folsburg_initial(self):
        t='Are there any units in South Folsburg from Main Street, Laurel to Lincoln for an active choking in a car?'
        h=detect.analyze(t,'zello-hatzalah');self.assertEqual(h['address'],'Main Street, S Fallsburg, NY');self.assertFalse(h['area_defaulted']);self.assertEqual(h['spoken_locality'],'S Fallsburg')
    def test_exact_repeat_town(self):
        h=detect.analyze('Any units in South Fallsburg in front of theater at 5250 Main Street off Laurel Avenue for choking.','zello-hatzalah')
        self.assertEqual(h['address'],'5250 Main Street, S Fallsburg, NY')
    def test_not_global_list(self):
        h=detect.analyze('Any units in Eldred for 12 Main Street for choking.','zello-hatzalah')
        self.assertIn(', Eldred, NY',h['address']);self.assertEqual(h['spoken_locality'],'Eldred')
    def test_named_nj_existing(self):
        self.assertEqual(detect.get_hatzolah_area('Any units in Paramus for Forest Avenue for an MVA'),'Paramus')
    def test_bayswater_existing(self):
        self.assertEqual(detect.get_hatzolah_area('Any units in Bayswater for Dunbar and Mott Avenue for child unresponsive'),'Queens')
    def test_no_named_area_home(self):
        self.assertEqual(detect.get_hatzolah_area('Any units for 13 and 47 for bleeding'),'Brooklyn')
    def test_b_division_not_town(self):
        self.assertFalse(detect.spoken_hatzalah_locality('Any units in the B for 13 and 47 for bleeding'))
    def test_town_named_road_not_place(self):
        self.assertFalse(detect.spoken_hatzalah_locality('Any units for South Folsburg Road for choking'))
    def test_unit_origin_not_job_local(self):
        self.assertFalse(detect.spoken_hatzalah_locality('Unit in Paramus responding to Brooklyn 12 Main Street choking'))

class Repeat(unittest.IsolatedAsyncioTestCase):
    def row(self,**kw):
        r={'t':time.time()-45,'nature':'choking','tokens':['main'],'address':'Main Street, Brooklyn, NY','source':'zello-hatzalah','area_defaulted':True};r.update(kw);return r
    async def case(self,enabled=True,old=None,verified=True,label='5250 Main Street, South Fallsburg, New York',sendok=True,prepare=False):
        h=detect.analyze('Any units in South Fallsburg for 5250 Main Street choking.','zello-hatzalah');row=old or self.row()
        with (patch.dict(os.environ,{'HATZALAH_LOCALITY_REPEAT_CORRECTION':'1' if enabled else '0'}),
              patch.object(main,'_load_recent',return_value=[row]),patch.object(main,'_save_recent') as save,
              patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(verified,True,label,41.7,-74.6,'South Fallsburg')),
              patch.object(main,'_cross_streets',new_callable=AsyncMock,return_value=(None,False)),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_correct_street_via_crosses',new_callable=AsyncMock,return_value=None),
              patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=sendok) as send):
            out=await main.verify_and_send('zello-hatzalah',h,Mock(),prepare_only=prepare)
        return out,h,send,save
    async def test_default_holds_with_candidate(self):
        out,h,send,save=await self.case(enabled=False);self.assertEqual(out,'suppressed');self.assertIn('locality_correction_candidate',h);send.assert_not_awaited()
    async def test_opt_in_exact_correction_explicit(self):
        out,h,send,save=await self.case();self.assertEqual(out,'sent');text=send.await_args.args[0]
        self.assertIn('LOCATION CORRECTION',text);self.assertIn('Earlier: Main Street, Brooklyn',text);self.assertIn('5250 Main Street, South Fallsburg',text)
        self.assertEqual(len(save.call_args.args[0]),1);self.assertFalse(save.call_args.args[0][0]['area_defaulted'])
    async def test_legacy_row_no_correction(self):
        out,h,send,save=await self.case(old={'t':time.time()-45,'nature':'choking','tokens':['main']});self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_wrong_house_map_no_correction(self):
        out,h,send,save=await self.case(label='5252 Main Street, South Fallsburg, New York');self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_different_prior_house_not_corrected(self):
        out,h,send,save=await self.case(old=self.row(address='5248 Main Street, Brooklyn, NY'));self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_explicit_previous_locality_not_overridden(self):
        out,h,send,save=await self.case(old=self.row(area_defaulted=False));self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_old_repeat_not_corrected(self):
        out,h,send,save=await self.case(old=self.row(t=time.time()-121));self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_failed_send_preserves_previous(self):
        out,h,send,save=await self.case(sendok=False);self.assertEqual(out,'queued');save.assert_not_called()
    async def test_prepare_never_mutates_or_sends(self):
        out,h,send,save=await self.case(prepare=True);self.assertEqual(out,'verified');send.assert_not_awaited();save.assert_not_called()
    async def test_map_failure_never_corrects(self):
        out,h,send,save=await self.case(verified=False);self.assertEqual(out,'suppressed');send.assert_not_awaited()

    async def test_real_nominatim_house_comma_road_label(self):
        out,h,send,save=await self.case(label='5250, Main Street, South Fallsburg, Town of Fallsburg, Sullivan County, New York')
        self.assertEqual(out,'sent');self.assertIn('LOCATION CORRECTION',send.await_args.args[0])
