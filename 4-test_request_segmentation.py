import unittest
import detect
class Requests(unittest.TestCase):
    def test_baby_two_requests(self):
        text='Any units available for West Broadway and Prince Street? 1372 East 24, motion for a baby not breathing.'
        spans=detect.split_dispatch_jobs(text,'zello-hatzalah')
        self.assertEqual(len(spans),2)
        baby=detect.analyze(spans[1],'zello-hatzalah')
        self.assertEqual(baby['address'],'1372 East 24th Street, Brooklyn, NY')
        self.assertEqual(baby['nature'],'Not Breathing')
        self.assertNotIn('West Broadway',baby['excerpt'])
    def test_no_fake_nature_from_first(self):
        text='Any units available for West Broadway and Prince Street? 1372 East 24, private house.'
        self.assertEqual(len(detect.split_dispatch_jobs(text,'zello-hatzalah')),1)
    def test_unit_numbers_not_split(self):
        text='Available for West Broadway and Prince Street. F97 and F214 1372 acknowledged.'
        self.assertEqual(len(detect.split_dispatch_jobs(text,'zello-hatzalah')),1)
    def test_do_not_rewrite_second_court(self):
        h=detect.analyze('1372 East 2nd Court for a baby not breathing.','zello-hatzalah')
        self.assertNotEqual((h or {}).get('address'),'1372 East 24th Street, Brooklyn, NY')
    def test_medical_alert_sullivan(self):
        h=detect.analyze('Dispatch to Bethel, 17 Overlook Drive for an activated medical alert, BLS response.','zello-sullivan')
        self.assertEqual(h['nature'],'Medical Alert Activation')
    def test_alert_negative(self):
        self.assertEqual(detect.get_nature('testing activated medical alert','sullivan'),'')

class StoveComplaint(unittest.TestCase):
    def test_real_carlton_reading(self):
        text="41 Brooklyn Box 38760 Carlton Avenue off of Park Avenue and Myrtle Avenue. That's for a stove fire apartment 12 Frank."
        h=detect.analyze(text,'fdny')
        self.assertEqual(h['address'],'60 Carlton Avenue, Brooklyn, NY')
        self.assertEqual(h['nature'],'Stove Fire, Apartment 12F')
    def test_stove_fire_specific_before_alarm(self):
        self.assertEqual(detect.get_nature('Phone alarm, automatic alarm. Reporting a stove fire apartment 12 Frank.','fdny'),'Stove Fire')
    def test_no_stove_fire_not_created(self):
        self.assertEqual(detect.get_nature('Reporting no stove fire.','fdny'),'')

class FDNYRequests(unittest.TestCase):
    def test_apartment_from_prior_update_not_carried(self):
        t='58 to Brooklyn. Engine 2 trucks 10-26 no extension apartment 1 Bravo units in the process. Phone Alarm Box 3526, 2673 West 33rd Street off Canal Avenue and Bayview Avenue electrical fire third floor hallway.'
        h=detect.analyze(t,'fdny')
        self.assertNotIn('1B',h['nature'])
        self.assertIn('Third Floor',h['nature'])
        self.assertNotIn('apartment 1 Bravo',h['dispatch_source_text'])
    def test_clipped_prefix_then_complete(self):
        t='Off Flatlands Avenue and Skidmore Lane for electrical fire apartment 2. 257 170 10-4. Phone alarm box 2264, 1170 East 95th Street off Flatlands Avenue and Skidmore Lane for electrical fire apartment 2.'
        h=detect.analyze(t,'fdny')
        self.assertEqual(h['address'],'1170 East 95th Street, Brooklyn, NY')
        self.assertFalse(detect.fdny_clipped_cross_only(h['dispatch_source_text']))
    def test_clipped_only_retains_guard(self):
        t='Off Flatlands Avenue and Skidmore Lane for electrical fire apartment 2.'
        self.assertTrue(detect.fdny_clipped_cross_only(detect.fdny_request_text(t)))
    def test_distinct_boxes_not_silently_chosen(self):
        t='Phone alarm box 1234, 100 Main Street for smoke. Phone alarm box 5678, 200 Other Street for fire.'
        self.assertIn('1234',detect.fdny_request_text(t));self.assertIn('5678',detect.fdny_request_text(t))
    def test_sullivan_knee_injury(self):
        h=detect.analyze('Dispatch to Empress, 26 Patricia Place, a ten-year-old knee injury BLS response.','zello-sullivan')
        self.assertEqual(h['nature'],'Knee Injury')
    def test_bls_not_diagnosis(self):
        self.assertEqual(detect.get_nature('Dispatch BLS response','sullivan'),'')
    def test_bayswater_explicit_place(self):
        h=detect.analyze('Any units in Bayswater for Dunbar and Mott Avenue for a child unresponsive.','zello-hatzalah')
        self.assertIn('Queens',h['address'])

class FDNYMultiJobs(unittest.TestCase):
    def test_two_complete_jobs_pair_locally(self):
        t='Phone alarm box 1234, 100 Grand Street for odor of gas apartment 1 Bravo. Phone alarm box 5678, 200 Henry Street for stove fire apartment 2 Frank.'
        spans=detect.split_dispatch_jobs(t,'fdny')
        self.assertEqual(len(spans),2)
        left,right=[detect.analyze(x,'fdny') for x in spans]
        self.assertIn('100 Grand',left['address']);self.assertIn('Gas',left['nature']);self.assertNotIn('2F',left['nature'])
        self.assertIn('200 Henry',right['address']);self.assertIn('Stove Fire',right['nature']);self.assertNotIn('1B',right['nature'])
    def test_missing_complaint_does_not_borrow(self):
        t='Phone alarm box 1234, 100 Grand Street. Phone alarm box 5678, 200 Henry Street for stove fire.'
        self.assertEqual(len(detect.split_dispatch_jobs(t,'fdny')),1)
    def test_nonbrooklyn_prefix_needs_review(self):
        t='Queens Phone alarm box 1234, 100 Grand Street for smoke. Brooklyn phone alarm box 5678, 200 Henry Street for stove fire.'
        self.assertEqual(len(detect.split_dispatch_jobs(t,'fdny')),1)

class Areas(unittest.TestCase):
    def test_paramus_does_not_become_street(self):
        h=detect.analyze('Any units available in Paramus for Forest Avenue and Continental Avenue for an MVA.','zello-hatzalah')
        self.assertEqual(h['address'],'Forest Avenue, Paramus, NJ')
        self.assertEqual(h['direct_cross_candidate'],'Continental Avenue')
    def test_southern_and_bruckner_pair(self):
        h=detect.analyze('Southern Boulevard and the Bruckner Expressway difficulty breathing.','zello-hatzalah')
        self.assertIn('Southern Boulevard',h['address'])
        self.assertNotIn('Units',h['address'])

class PumpOut(unittest.TestCase):
    def test_explicit_public_service(self):
        h=detect.analyze('Sullivan dispatch Liberty public service call for a cellar pump out number four Irving Lane.','zello-sullivan')
        self.assertEqual(h['nature'],'Cellar Pump-Out')
    def test_number_house_not_street_name(self):
        h=detect.analyze('Sullivan dispatch Liberty cellar pump out number 4 Irving Lane, cross streets of Bloom Road and Twin Bridge Road.','zello-sullivan')
        self.assertEqual(h['address'],'4 Irving Lane, Liberty, NY')

class PriorityDraft(unittest.TestCase):
    def test_priority_explicit_held_no_guessed_borough(self):
        import main
        h={'nature':'Unresponsive','address':'Dunbar & Mott Avenue, Brooklyn, NY','hold_reason':'no verified location','voice_url':'https://example.invalid/audio'}
        text=main._priority_hold_text('zello-hatzalah',h)
        self.assertIn('HELD - NOT POSTED',text);self.assertNotIn('Brooklyn',text);self.assertIn('Unresponsive',text)
    def test_nonpriority_is_not_routed(self):
        import main
        self.assertEqual(main._priority_hold_text('fdny',{'nature':'Automatic Alarm'}),'')

class RepeatAndScope(unittest.TestCase):
    def test_suffixless_private_house_repeat_no_invented_complaint(self):
        t='1372 East 24, private house. ALS units responding.'
        self.assertEqual(detect.extract_dispatch_address(t,'hatzolah'),'1372 East 24th Street, Brooklyn, NY')
        self.assertFalse(detect.get_nature(t,'hatzolah'))
    def test_prior_numbered_job_never_dropped(self):
        t='100 Henry Street for smoke. Engine 2 to Brooklyn Phone alarm box 3526, 2673 West 33rd Street electrical fire.'
        self.assertEqual(detect.fdny_request_text(t),t)

from unittest.mock import AsyncMock,Mock,patch
import main
class AreaVerification(unittest.IsolatedAsyncioTestCase):
    async def test_southern_boulevard_uses_unique_map_borough(self):
        h=detect.analyze('Southern Boulevard and the Bruckner Expressway for difficulty breathing.','zello-hatzalah')
        with (patch('locality_gate.plausible_boroughs',new_callable=AsyncMock,return_value={'Bronx'}),
              patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'Southern Boulevard, Bronx',40.82,-73.89,'Bronx')),
              patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),
              patch.object(main,'_cross_streets',new_callable=AsyncMock,return_value=(None,False)),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            outcome=await main.verify_and_send('zello-hatzalah',h,Mock(),prepare_only=True)
        self.assertEqual(outcome,'verified');self.assertIn('Bronx',h['address']);self.assertNotIn('Bruckner',h['address']);send.assert_not_awaited()

class HandlerPairing(unittest.IsolatedAsyncioTestCase):
    async def test_complete_jobs_reach_verify_as_separate_candidates(self):
        import tempfile,time
        from pathlib import Path
        t='Phone alarm box 1234, 100 Grand Street for odor of gas apartment 1 Bravo. Phone alarm box 5678, 200 Henry Street for stove fire apartment 2 Frank.'
        with tempfile.TemporaryDirectory() as d:
            with (patch.object(main,'_kw_check',new_callable=AsyncMock),
                  patch.object(main,'_fdny_clip_sanity',return_value=''),
                  patch.object(main,'_save_seen'),patch.object(main,'_append_alert_log'),patch.object(main,'_fdny_call_record'),
                  patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(True,False,'',40.6,-73.9,'Brooklyn')),
                  patch.object(main,'verify_and_send',new_callable=AsyncMock,return_value='suppressed') as verify,
                  patch.object(main,'_held_recording',new_callable=AsyncMock,return_value=''),
                  patch.object(main,'_post_held_review',new_callable=AsyncMock),
                  patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
                await main._fdny_handle_call({'id':'fixture','ts':time.time(),'transcription':t},Mock(),{},Path(d))
        self.assertEqual(verify.await_count,2)
        candidates=[c.args[1] for c in verify.await_args_list]
        self.assertIn('100 Grand',candidates[0]['address']);self.assertIn('Gas',candidates[0]['nature'])
        self.assertIn('200 Henry',candidates[1]['address']);self.assertIn('Stove',candidates[1]['nature']);send.assert_not_awaited()

class ActualReads(unittest.TestCase):
    def test_w33_actual_vendor_without_box_word(self):
        t='58 the Brooklyn. Engine 2 trucks 10 26 no extension apartment 1 Bravo units in the process 58 10 8. 3526 2673 West 33rd Street off of Canal Avenue and Bayview Avenue electrical fire third floor hallway. 3526 2673 West 33rd Street'
        h=detect.analyze(t,'fdny')
        self.assertEqual(h['address'],'2673 West 33rd Street, Brooklyn, NY')
        self.assertEqual(h['nature'],'Electrical Fire, Third Floor')
        self.assertNotIn('1 Bravo',h['dispatch_source_text'])
    def test_e95_actual_clipped_read(self):
        t='off Flatlands Avenue and Skidmore Lane for electrical fire, apartment two. 257 57 104 170 170 104 box 2264 1170 East 95 Street. That\'s off of Flatlands Avenue and Skidmore Lane for electrical fire, apartment two. 1801 the time 278'
        h=detect.analyze(t,'fdny')
        self.assertEqual(h['address'],'1170 East 95 Street, Brooklyn, NY')
        self.assertFalse(detect.fdny_clipped_cross_only(h['dispatch_source_text']))
        self.assertIn('Apartment 2',h['nature'])

class SendBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_full_repeat_cannot_fail_original_clipped_guard(self):
        t="off Flatlands Avenue and Skidmore Lane for electrical fire. box 2264 1170 East 95 Street. That's off Flatlands Avenue and Skidmore Lane for electrical fire apartment 2."
        h=detect.analyze(t,'fdny')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),
              patch.object(main,'_load_box_cache',return_value={}),
              patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            result=await main.verify_and_send('fdny',h,Mock(),source_call={'transcription':t},prepare_only=True)
        self.assertEqual(result,'suppressed');self.assertNotIn('clipped primary',h['hold_reason']);send.assert_not_awaited()
    async def test_baby_exact_map_failure_never_sends(self):
        h=detect.analyze('1372 East 24, motion for a baby not breathing.','zello-hatzalah')
        with (patch('locality_gate.plausible_boroughs',new_callable=AsyncMock,return_value={'Brooklyn'}),
              patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send):
            result=await main.verify_and_send('zello-hatzalah',h,Mock(),prepare_only=True)
        self.assertEqual(result,'suppressed');send.assert_not_awaited()

class MoreSafety(unittest.TestCase):
    def test_other_borough_prefix_not_dropped(self):
        t='Queens responding. Phone alarm box 2264, 1170 East 95 Street for electrical fire.'
        self.assertEqual(detect.fdny_request_text(t),t)
    def test_glued_multi_box_not_split(self):
        t='Box 38760 Carlton Avenue stove fire. Box 1234 100 Henry Street smoke.'
        self.assertEqual(len(detect.split_dispatch_jobs(t,'fdny')),1)
    def test_knee_negative(self):
        self.assertFalse(detect.get_nature('no knee injury BLS response','sullivan'))
