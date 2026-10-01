import unittest
from unittest.mock import AsyncMock, Mock, patch

import detect


class TestSpokenNature(unittest.TestCase):
    def test_smoke_in_post_office_beats_phone_alarm(self):
        text=('Phone Alarm, Box 957, 35 Herkimer Place, Nostrand Avenue to Perry Place, '
              'reporting smoke in the post office. Phone Alarm, Box 957, '
              '35 Herkimer Place, reporting smoke in the post office.')
        h=detect.analyze(text,'fdny')
        self.assertEqual(h['nature'],'Smoke in the Post Office')
        self.assertEqual(h['address'],'35 Herkimer Place, Brooklyn, NY')

    def test_explicit_fdny_complaint_family_beats_phone_alarm(self):
        for speech, expected in [
            ('reporting a bedroom fire', 'Bedroom Fire'),
            ('reporting an electrical fire', 'Electrical Fire'),
            ('reporting smoke on the third floor', 'Smoke on the Third Floor'),
            ('reporting a fire in the basement', 'Fire in the Basement'),
            ('reporting an odor of smoke', 'Odor of Smoke'),
            ('reporting smoke', 'Smoke'),
        ]:
            with self.subTest(speech=speech):
                self.assertEqual(detect.get_nature('Phone Alarm Box 1234, '
                                 '12 Main Street, '+speech, 'fdny'), expected)
        self.assertEqual(detect.get_nature('Phone Alarm Box 1234, '
                         '12 Main Street, no fire', 'fdny'), '')

    def test_stove_fire_beats_phone_alarm(self):
        text = ('Phone Alarm Box 3243, 3021 Avenue Z, Ford Street to Batchelder Street, '
                'reporting a stove fire apartment 6K. Phone Alarm Box 3243, '
                '3021 Avenue Z, Ford Street to Batchelder Street, stove fire apartment 6K.')
        h = detect.analyze(text, 'fdny')
        self.assertEqual(h['nature'], 'Stove Fire, Apartment 6K')
        self.assertEqual(h['address'], '3021 Avenue Z, Brooklyn, NY')
        self.assertEqual(h['box_heard'], '3243')

    def test_odor_outside_is_nature_but_not_odor_gas(self):
        text = 'Brooklyn Box 615, Carlton Avenue and Lafayette Avenue, odor outside.'
        h = detect.analyze(text, 'fdny')
        self.assertEqual(h['nature'], 'Odor Outside')
        self.assertNotIn('gas', h['nature'].lower())

    def test_odor_gas_without_of_beats_phone_alarm(self):
        h = detect.analyze('Phone Alarm Box 1671, 301 Center Avenue, odor gas, apartment 14 boy', 'fdny')
        self.assertEqual(h['nature'], 'Odor Gas, Apartment 14B')

    def test_odor_in_area_is_nature(self):
        h = detect.analyze('343 Carlton Avenue for an odor in the area.', 'fdny')
        self.assertEqual(h['nature'], 'Odor in the Area')


class TestCrossDecision(unittest.IsolatedAsyncioTestCase):
    async def test_unverified_spoken_cross_holds_numbered_fdny(self):
        import main
        hit = detect.analyze('Phone Alarm Box 3243, 3021 Avenue Z, Ford Street to Batchelder Street, stove fire', 'fdny')
        sent = []
        with patch.object(main, 'geocode_verify', new_callable=AsyncMock,
                          return_value=(True, False, '3021 AVENUE Z, Brooklyn, NY, USA', 40.590409, -73.935932, 'Brooklyn')), \
             patch.object(main, '_box_lookup', new_callable=AsyncMock, return_value=[('AVENUE Z AT BATCHELDER STREET', 'Brooklyn')]), \
             patch.object(main, '_cross_streets', new_callable=AsyncMock, return_value=('Ford Street & Batchelder Street', True)), \
             patch('spoken_cross.verify', new_callable=AsyncMock, side_effect=[False, True]), \
             patch.object(main, '_map_street_names', new_callable=AsyncMock, return_value=set()), \
             patch.object(main, '_load_recent', return_value=[]), \
             patch.object(main, '_save_recent'), \
             patch.object(main, 'ops_log'), \
             patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock,
                          side_effect=lambda text: sent.append(text) or True):
            result = await main.verify_and_send('fdny', hit, Mock(), None)
        self.assertEqual(result, 'suppressed')
        self.assertEqual(len(sent), 0)
        self.assertIn('spoken cross pair',hit['hold_reason'])


if __name__ == '__main__':
    unittest.main()

class TestCorrectionGuard(unittest.TestCase):
    def test_same_batch_explicit_correction_suppresses_old_address(self):
        import time
        from fdny_correction_guard import CorrectionGuard
        base = time.time()-60
        first = {'id':'initial', 'audio_start_ts':base,
                 'transcription':'Phone Alarm Box 2427, 1368 New York Avenue, Foster to Newkirk, smoke.'}
        correction = {'id':'correction', 'audio_start_ts':base+48,
                      'transcription':'Ladder 157, correct address gonna be 1358 New York Avenue. 1358.'}
        g = CorrectionGuard()
        g.ingest([first,correction])
        self.assertEqual(g.reason(detect.analyze(first['transcription'],'fdny'),first),
                         'superseded by explicit later address correction')
        correct = {'id':'correct-dispatch','audio_start_ts':base+110,
                   'transcription':'Phone Alarm Box 2427, 1358 New York Avenue, smoke.'}
        self.assertFalse(g.reason(detect.analyze(correct['transcription'],'fdny'),correct))

    def test_already_sent_different_house_same_spoken_box_held(self):
        import time
        from fdny_correction_guard import CorrectionGuard
        g=CorrectionGuard()
        first=detect.analyze('Phone Alarm Box 2427, 1368 New York Avenue, smoke','fdny')
        second=detect.analyze('Phone Alarm Box 2427, 1358 New York Avenue, smoke','fdny')
        g.mark_sent(first)
        self.assertIn('same spoken box already posted',g.reason(second,{'audio_start_ts':time.time()}))
        unrelated=detect.analyze('Phone Alarm Box 9999, 1358 New York Avenue, smoke','fdny')
        self.assertFalse(g.reason(unrelated,{'audio_start_ts':time.time()}))

    def test_distinct_unboxed_jobs_on_same_street_are_not_assumed_corrections(self):
        import time
        from fdny_correction_guard import CorrectionGuard
        g=CorrectionGuard()
        first=detect.analyze('Phone Alarm 1358 New York Avenue, smoke','fdny')
        second=detect.analyze('Phone Alarm 1368 New York Avenue, smoke','fdny')
        g.mark_sent(first)
        self.assertFalse(g.reason(second,{'audio_start_ts':time.time()}))

    def test_no_unspoken_or_different_street_suppression(self):
        import time
        from fdny_correction_guard import CorrectionGuard
        base=time.time()-50
        g=CorrectionGuard()
        g.ingest([{'audio_start_ts':base+40,'transcription':'Correct address 1358 New York Avenue'}])
        different=detect.analyze('Phone Alarm Box 2427, 1368 Brooklyn Avenue, smoke','fdny')
        self.assertFalse(g.reason(different,{'audio_start_ts':base}))
        first=detect.analyze('Phone Alarm Box 2427, 1368 New York Avenue, smoke','fdny')
        self.assertFalse(g.reason(first,{'audio_start_ts':base+45}))

class TestCorrectionSendGate(unittest.IsolatedAsyncioTestCase):
    async def test_superseded_address_never_reaches_waha(self):
        import main, time
        from fdny_correction_guard import CorrectionGuard
        base=time.time()-70
        first={'id':'initial','audio_start_ts':base,
               'transcription':'Phone Alarm Box 2427, 1368 New York Avenue, smoke'}
        correction={'id':'correction','audio_start_ts':base+48,
                    'transcription':'Ladder 157 correct address gonna be 1358 New York Avenue'}
        guard=CorrectionGuard();guard.ingest([first,correction])
        hit=detect.analyze(first['transcription'],'fdny')
        with patch.object(main,'geocode_verify',new_callable=AsyncMock,
                          return_value=(True,False,'1368 NEW YORK AVENUE, Brooklyn, NY, USA',40.64,-73.94,'Brooklyn')), \
             patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]), \
             patch.object(main,'_cross_streets',new_callable=AsyncMock,return_value=('',False)), \
             patch.object(main,'_load_recent',return_value=[]), \
             patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()), \
             patch.object(main,'ops_log'), \
             patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as sender:
            result=await main.verify_and_send('fdny',hit,Mock(),None,
                correction_guard=guard,source_call=first)
        self.assertEqual(result,'suppressed')
        sender.assert_not_awaited()
        self.assertTrue(hit['hold_reason'])  # held (no nature now precedes the supersede check)

class TestCorrectionConflict(unittest.TestCase):
    def test_explicit_correction_after_send_flags_once(self):
        import time
        from fdny_correction_guard import CorrectionGuard
        g=CorrectionGuard()
        g.mark_sent(detect.analyze('Phone Alarm Box 2427, 1368 New York Avenue, smoke','fdny'))
        item={'id':'correct-1','audio_start_ts':time.time()-20,
              'transcription':'Ladder 157, correct address gonna be 1358 New York Avenue.'}
        got=g.ingest([item])
        self.assertEqual(len(got),1)
        self.assertEqual(got[0][0],'2427')
        self.assertEqual(g.ingest([item]),[])

    def test_unrelated_box_not_used_to_flag_same_street(self):
        import time
        from fdny_correction_guard import CorrectionGuard
        g=CorrectionGuard()
        g.mark_sent(detect.analyze('Phone Alarm Box 2427, 1368 New York Avenue, smoke','fdny'))
        item={'audio_start_ts':time.time()-20,
              'transcription':'Box 9999, correct address 1358 New York Avenue.'}
        self.assertEqual(g.ingest([item]),[])

class TestFdnyGroqHeldRescue(unittest.IsolatedAsyncioTestCase):
    async def test_301_center_to_sutter_only_with_independent_house_box_nature_and_cross(self):
        import main, tempfile, time
        from pathlib import Path
        old_text=('Phone Alarm Box 1671, 301 Center Avenue, Rockaway Avenue to Osborne Street, '
                  'odor gas, apartment 14 boy.')
        second=('Phone Alarm Box 1671, 301 Sutter Avenue, Rockaway Avenue to Osborne Street, '
                'odor gas, apartment 14 boy.')
        call={'id':'held-center','ts':time.time()-80,'audio_start_ts':time.time()-95}
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'clip.wav';src.write_bytes(b'RIFFdry')
            stats=Mock()
            hit=detect.analyze(old_text,'fdny')
            revised=[]
            with patch.object(main.transcribe,'GROQ_ENABLED',True), \
                 patch.object(main.transcribe,'GROQ_KEY','present'), \
                 patch.object(main.transcribe,'second_listen',return_value=second), \
                 patch.object(main,'geocode_verify',new_callable=AsyncMock,
                              return_value=(True,False,'301 SUTTER AVENUE, Brooklyn, NY, USA',40.6676,-73.909094,'Brooklyn')), \
                 patch('spoken_cross.verify',new_callable=AsyncMock,side_effect=[True,False]), \
                 patch.object(main,'verify_and_send',new_callable=AsyncMock,
                              side_effect=lambda profile,candidate,*args,**kwargs: revised.append(candidate.copy()) or 'sent'):
                outcome=await main._fdny_recover_held_street(hit,src,stats,call,'clip.wav')
        self.assertEqual(outcome,'sent')
        self.assertEqual(revised[0]['address'],'301 Sutter Avenue, Brooklyn, NY')
        self.assertEqual(revised[0]['nature'],'Odor Gas, Apartment 14B')
        self.assertEqual(revised[0]['cross'],'')

    async def test_independent_disagreement_stays_held_without_sender(self):
        import main,tempfile,time
        from pathlib import Path
        base='Phone Alarm Box 1671, 301 Center Avenue, Rockaway Avenue to Osborne Street, odor gas.'
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'clip.wav';src.write_bytes(b'RIFFdry')
            with patch.object(main.transcribe,'GROQ_ENABLED',True), \
                 patch.object(main.transcribe,'GROQ_KEY','present'), \
                 patch.object(main.transcribe,'second_listen',
                              return_value='Phone Alarm Box 1671, 303 Sutter Avenue, odor gas.'), \
                 patch.object(main,'verify_and_send',new_callable=AsyncMock) as sender:
                outcome=await main._fdny_recover_held_street(detect.analyze(base,'fdny'),src,Mock(),
                    {'ts':time.time()-70},'clip.wav')
        self.assertEqual(outcome,'suppressed')
        sender.assert_not_awaited()

class TestCrossFragment(unittest.TestCase):
    def test_west23_trailing_street_not_cross(self):
        text=('Unassigned Class 3 Brooklyn Box 3544 2860 West 23 Street '
              'Neptune to Mermaid Avenue automatic alarm.')
        h=detect.analyze(text,'fdny')
        self.assertEqual(h['address'],'2860 West 23 Street, Brooklyn, NY')
        self.assertEqual(h['cross'],'Neptune & Mermaid Avenue')

    def test_period_after_primary_road(self):
        h=detect.analyze('Brooklyn Box 3544 2860 West 23rd Street. Neptune to Mermaid Avenue, automatic alarm.','fdny')
        self.assertEqual(h['cross'],'Neptune & Mermaid Avenue')

    def test_fragment_after_primary_road_is_not_cross(self):
        h=detect.analyze('Brooklyn Box 3544 2860 West 23 Street Neptune to units, automatic alarm.','fdny')
        self.assertNotIn('Street Neptune',h.get('cross') or '')

    def test_full_named_pair_still_kept(self):
        h=detect.analyze('Phone Alarm Box 957, 35 Herkimer Place, Nostrand Avenue '
                         'to Perry Place, reporting smoke in the post office','fdny')
        self.assertEqual(h['cross'],'Nostrand Avenue & Perry Place')


class TestNumberStreetHouse(unittest.TestCase):
    def test_spoken_number_street_has_distinct_house(self):
        speech=('Class 3 Brooklyn Box 1308 Terminal 14, 261 Number 9 Street, '
                '4th to 5th Avenues, automatic alarm.')
        h=detect.analyze(speech,'fdny')
        self.assertEqual(h['address'],'261 9th Street, Brooklyn, NY')
        self.assertEqual(h['box_heard'],'1308')
        self.assertEqual(h['nature'],'Automatic Alarm')

    def test_box_is_not_the_house_on_number_street(self):
        h=detect.analyze('Class 3 Brooklyn Box 1308, Number 9 Street, automatic alarm.','fdny')
        self.assertNotEqual(h['address'],'1308 9th Street, Brooklyn, NY')


class TestBareBoxRoad(unittest.TestCase):
    def test_spoken_box_does_not_become_house(self):
        speech=('Follow up on the call Box 3734, Clarendon Road between East 31 and '
                'East 32 Streets, odor of gas in the area. Follow up on the call '
                'Box 3734 on Clarendon Road between East 31 and East 32, '
                'reporting an odor of gas in the area.')
        h=detect.analyze(speech,'fdny')
        self.assertEqual(h['address'],'Clarendon Road, Brooklyn, NY')
        self.assertEqual(h['box_heard'],'3734')
        self.assertEqual(h['nature'],'Odor of Gas')

    def test_distinct_house_after_box_preserved(self):
        h=detect.analyze('Phone Alarm Box 957, 35 Herkimer Place, reporting smoke in the post office','fdny')
        self.assertEqual(h['address'],'35 Herkimer Place, Brooklyn, NY')


class TestExitNumberNotHouse(unittest.TestCase):
    def test_mta_exit_identifiers_not_house_numbers(self):
        h=detect.analyze('Advise MTA we are opening subway emergency exit number 103 '
            'on Fulton and Jay, and number 264 on Tillery Street and Jay Street '
            'for inspection.','fdny')
        self.assertNotEqual(h['address'],'264 Tillery Street, Brooklyn, NY')
        self.assertNotEqual(h['address'],'103 Fulton Street, Brooklyn, NY')

    def test_real_house_still_wins_after_unrelated_exit(self):
        h=detect.analyze('Subway emergency exit number 264 on Tillery Street. '
            'Phone Alarm Box 957, 35 Herkimer Place, smoke.','fdny')
        self.assertEqual(h['address'],'35 Herkimer Place, Brooklyn, NY')


class TestFdnyClipSanity(unittest.TestCase):
    def test_rejects_long_transcript_on_tiny_silent_clip(self):
        import tempfile, wave
        from pathlib import Path
        import main
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"short.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
                w.writeframes(b"\0\0"*24000)
            transcript="Engine 35 to Brooklyn. 35. Box 316. " * 6
            self.assertIn("duration mismatch",main._fdny_clip_sanity(path,transcript))
            self.assertEqual(main._fdny_clip_sanity(None,transcript),"FDNY audio missing")
    def test_real_voiced_capture_passes(self):
        import tempfile, wave, math, struct
        from pathlib import Path
        import main
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"voiced.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
                w.writeframes(b"".join(struct.pack("<h",int(2200*math.sin(2*math.pi*440*i/16000)))
                                      for i in range(16000*12)))
            self.assertEqual(main._fdny_clip_sanity(path,'Engine 35 to Brooklyn. Box 316. Making an 18 for a code 2.'),'')
