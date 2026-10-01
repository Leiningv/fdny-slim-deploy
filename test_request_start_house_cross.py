import os
import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect, main

PREFIX='SI-57, you available for the bus? Copy that. 901, take it in. You are heading over to 28 Culver Street, Colonial to Forest. Communicate with 11. The crew is 89, 98, and 47. '
BATTERY='Box 2752, 106 Battery Avenue, off of 90 Street, 92 Street, odor of gas. Box 2752, 106 Battery Avenue, 90 to 92 Street, odor of gas.'
class RequestStarts(unittest.TestCase):
    def test_vendor_v_and_b_reads_own_bleeding(self):
        for start in ['Any units from the V for','Any units in the B for','Any units available for','Any units free for']:
            with self.subTest(start=start):
                spans=detect.split_dispatch_jobs(PREFIX+start+' 13 and 47 for bleeding trauma? 286','zello-hatzalah')
                self.assertEqual(len(spans),2)
                first,second=[detect.analyze(t,'zello-hatzalah') for t in spans]
                self.assertFalse(first['nature']);self.assertEqual(second['nature'],'Bleeding')
                self.assertEqual(second['address'],'13th Ave & 47th St, Brooklyn, NY')
                self.assertNotIn('Colonial',second['dispatch_source_text'])
    def test_two_full_requests_each_owns_its_complaint(self):
        t='Any units for 16 and 52 for trauma? Any units in the B for 13 and 47 for bleeding?'
        spans=detect.split_dispatch_jobs(t,'zello-hatzalah')
        self.assertEqual(len(spans),2)
        a,b=[detect.analyze(t,'zello-hatzalah') for t in spans]
        self.assertFalse(a['nature']);self.assertEqual(b['nature'],'Bleeding')
        self.assertNotIn('Bleeding',a['nature'])
    def test_backup_without_complaint_not_split(self):
        self.assertEqual(len(detect.split_dispatch_jobs(PREFIX+'Any units in the B for 13 and 47? Unit to back up.','zello-hatzalah')),1)
    def test_complaint_without_address_not_split(self):
        self.assertEqual(len(detect.split_dispatch_jobs(PREFIX+'Any units for a bleeding trauma?','zello-hatzalah')),1)
    def test_single_request_not_split(self):
        self.assertEqual(len(detect.split_dispatch_jobs('Any units in the B for 13 and 47 for bleeding trauma?','zello-hatzalah')),1)
    def test_no_cross_job_house_donation(self):
        spans=detect.split_dispatch_jobs(PREFIX+'Any units in the B for 13 and 47 for bleeding trauma?','zello-hatzalah')
        h=detect.analyze(spans[1],'zello-hatzalah');self.assertNotIn('28',h['address']);self.assertNotIn('1301',h['address'])

class HouseCross(unittest.IsolatedAsyncioTestCase):
    async def run_case(self,enabled=True,verified=True,label='106 Battery Avenue, Brooklyn, NY',cross_ok=False,glue=False,prepare=False):
        h=detect.analyze(BATTERY,'fdny');h['box_glue_ambiguous']=glue
        with (patch.dict(os.environ,{'FDNY_VERIFIED_HOUSE_UNVERIFIED_CROSSES':'1' if enabled else '0'}),
              patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(verified,False,label,40.6,-74.0,'Brooklyn')),
              patch('spoken_cross.verify',new_callable=AsyncMock,return_value=cross_ok),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_correct_street_via_crosses',new_callable=AsyncMock,return_value=None),
              patch.object(main,'_cross_streets',new_callable=AsyncMock,return_value=(None,False)),
              patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),
              patch.object(main,'_load_box_cache',return_value={}),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'_save_recent'),patch.object(main,'ops_log'),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send):
            out=await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':BATTERY},prepare_only=prepare)
        return out,h,send
    async def test_default_still_holds(self):
        out,h,send=await self.run_case(enabled=False);self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_opt_in_exact_house_labels_heard_crosses(self):
        out,h,send=await self.run_case();self.assertEqual(out,'sent')
        text=send.await_args.args[0];self.assertIn('106 Battery Avenue',text)
        self.assertIn('Heard crosses (unverified): 90 & 92 Street',text)
        self.assertNotIn('C/s ',text);self.assertNotIn('not confirmed',text)
    async def test_prepare_only_never_sends(self):
        out,h,send=await self.run_case(prepare=True);self.assertEqual(out,'verified');send.assert_not_awaited()
    async def test_wrong_house_holds(self):
        out,h,send=await self.run_case(label='108 Battery Avenue, Brooklyn, NY');self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_wrong_street_holds(self):
        out,h,send=await self.run_case(label='106 Henry Street, Brooklyn, NY');self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_glued_run_not_allowed(self):
        out,h,send=await self.run_case(glue=True);self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_verified_crosses_keep_normal_line(self):
        out,h,send=await self.run_case(cross_ok=True);self.assertEqual(out,'sent');text=send.await_args.args[0]
        self.assertIn('C/s ',text);self.assertNotIn('Heard crosses (unverified)',text)
    def test_unverified_label_distinct_from_verified_line(self):
        h=detect.analyze(BATTERY,'fdny');text=main.format_alert(h,unverified_crosses='90 & 92 Street')
        self.assertIn('Heard crosses (unverified):',text);self.assertNotIn('C/s ',text)
    async def test_geocode_disabled_not_allowed(self):
        with patch.object(main,'GEOCODE_VERIFY',False):
            out,h,send=await self.run_case()
        self.assertEqual(out,'suppressed');send.assert_not_awaited()
    async def test_unverified_house_holds(self):
        out,h,send=await self.run_case(verified=False);self.assertEqual(out,'suppressed');send.assert_not_awaited()
