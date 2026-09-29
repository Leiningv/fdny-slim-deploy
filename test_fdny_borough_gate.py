import unittest
from fdny_borough_gate import spoken_borough_conflict, exact_numbered_fdny_match, box_street_conflict, unnumbered_with_spoken_building


class TestFdnyBoroughGate(unittest.TestCase):
    def test_fire_street_transcript(self):
        transcript = ("We're in Queens, phone alarm box 1766, 656 Fire Street, "
                      "closing to Wortman Avenue. Engine 225 assigned.")
        self.assertEqual(spoken_borough_conflict(transcript, '656 Fire Street, Brooklyn, NY'), 'Queens')

    def test_explicit_job_local_variants(self):
        for phrase, borough in [('The job is in Manhattan', 'Manhattan'),
                                ('Incident at the Bronx', 'Bronx'),
                                ("We're at Staten Island", 'Staten Island'),
                                ('Phone alarm, 12 Main Street, Queens', 'Queens')]:
            with self.subTest(phrase=phrase):
                self.assertEqual(spoken_borough_conflict(phrase, '12 Main Street, Brooklyn, NY'), borough)

    def test_owner_audio_independent_hearing_variants(self):
        # Owner-provided recording of the 01:54 incident was independently
        # heard as F Eye/Sapphire Street and a disputed complaint. Neither
        # hearing justifies the vendor's Brooklyn Fire Street output.
        for heard in ("We're in Queens, box 1766, 656 F Eye Street, "
                      "closing to Wortman Avenue, motor vehicle.",
                      "We're in Queens, box 1766, 656 Sapphire Street, "
                      "closing to Wortman Avenue, phone alarm."):
            with self.subTest(heard=heard):
                self.assertEqual(spoken_borough_conflict(
                    heard, '656 Fire Street, Brooklyn, NY'), 'Queens')
        # A partial radio reading that sounds like Queens Boulevard is not
        # enough to prove the incident borough; the exact-map gate still
        # blocks the 656 Fire Street -> 184 Fire Fighter false match.
        self.assertEqual(spoken_borough_conflict(
            'Queens Boulevard 1766, 656 F Eye Street',
            '656 Fire Street, Brooklyn, NY'), '')
        self.assertFalse(exact_numbered_fdny_match(
            '656 Fire Street, Brooklyn, NY',
            '184 FIRE FIGHTER BOCCHINO STREET, Brooklyn, NY, USA'))

    def test_brooklyn_and_unit_regressions(self):
        address = '123 Main Street, Brooklyn, NY'
        for transcript in ('Phone alarm box 1234, 123 Main Street, Brooklyn',
                           'Queens unit responding to 123 Main Street',
                           'Engine 24 from Queens responds to 123 Main Street',
                           'The unit is in Queens, job at 123 Main Street, Brooklyn',
                           'Phone alarm at 123 Queens Street, Brooklyn',
                           "We're in Queens Street at house 123", 
                           'Phone alarm at 123 Main Street'):
            with self.subTest(transcript=transcript):
                self.assertEqual(spoken_borough_conflict(transcript, address), '')

    def test_non_brooklyn_address(self):
        self.assertEqual(spoken_borough_conflict("We're in Queens", '123 Main Street, Queens, NY'), '')


class TestExactFdnyAddress(unittest.TestCase):
    def test_fuzzy_fire_fighter_is_rejected(self):
        self.assertFalse(exact_numbered_fdny_match(
            '656 Fire Street, Brooklyn, NY',
            '184 FIRE FIGHTER BOCCHINO STREET, Brooklyn, NY, USA'))

    def test_exact_brooklyn_house_and_street(self):
        examples = [
            ('225 Wortman Avenue, Brooklyn, NY', '225 WORTMAN AVE, Brooklyn, NY, USA'),
            ('53 East 84th Street, Brooklyn, NY', '53 EAST 84TH ST, Brooklyn, NY, USA'),
            ('12 Main St, Brooklyn, NY', '12 MAIN STREET, Brooklyn, NY, USA'),
            ('8015 13th Avenue, Brooklyn, NY', '8015 13 AVENUE, Brooklyn, NY, USA'),
            ('1701 86th Street, Brooklyn, NY', '1701 86 STREET, Brooklyn, NY, USA'),
        ]
        for addr, label in examples:
            with self.subTest(addr=addr):
                self.assertTrue(exact_numbered_fdny_match(addr, label))
        self.assertFalse(exact_numbered_fdny_match(
            '225 Wortman Avenue, Brooklyn, NY', '226 WORTMAN AVE, Brooklyn, NY, USA'))


class TestBoxStreetConflict(unittest.TestCase):
    def test_fire_street_box(self):
        rows = [('BENNETT AVE & W 184 ST', 'Manhattan'),
                ('Pitkin Ave & Jerome St', 'Brooklyn'),
                ('156th Ave & 79th St', 'Queens'),
                ('Carmel Ave & Caro St', 'Staten Island')]
        self.assertTrue(box_street_conflict('656 Fire Street, Brooklyn, NY', 'Brooklyn', rows))

    def test_correlated_brooklyn_address(self):
        self.assertFalse(box_street_conflict('1238 East 84th Street, Brooklyn, NY',
                          'Brooklyn', [('AVE M at E 84 ST', 'Brooklyn')]))
        self.assertFalse(box_street_conflict('1701 86th Street, Brooklyn, NY',
                          'Brooklyn', [('86 ST at 17 AVE', 'Brooklyn')]))
        self.assertFalse(box_street_conflict('1701 86th Street, Brooklyn, NY', 'Brooklyn', []))

class TestFdnyHandlerHold(unittest.IsolatedAsyncioTestCase):
    async def test_park_avenue_held_with_recording_and_no_send(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import AsyncMock, Mock, patch
        import main
        transcript = ('Alarm 395, 56 North Oxford Walk to Park Avenue, alarm activation 3C, '
                      '3 Charles. Alarm, Box 395, 56 North Oxford Walk, I said Park Avenue, '
                      'alarm activation 3C, 3 Charles.')
        stats = Mock()
        with tempfile.TemporaryDirectory() as d:
            with (patch.object(main, '_fdny_fetch_clip', return_value=Path(d)/'clip.wav'),
                  patch.object(main, '_archive_clip'),
                  patch.object(main, '_save_seen'),
                  patch.object(main, '_held_recording', new_callable=AsyncMock, return_value='https://example.invalid/park.ogg') as recording,
                  patch.object(main, 'verify_and_send', new_callable=AsyncMock) as sender,
                  patch.object(main, '_append_alert_log'),
                  patch.object(main, 'ops_log'),
                  patch.object(main, '_kw_check', new_callable=AsyncMock)):
                await main._fdny_handle_call({'id':'park-test','transcription':transcript,
                                             'audio_url':'https://example.invalid/source.m4a'},
                                            stats, {}, Path(d))
        sender.assert_not_awaited()
        recording.assert_awaited_once()
        row = stats.mark_alert.call_args
        self.assertEqual(row.args[3], False)
        self.assertEqual(row.kwargs['outcome'], 'suppressed')
        self.assertIn('numbered building (56 North Oxford Walk)', row.kwargs['reason'])
        self.assertEqual(row.kwargs['voice_url'], 'https://example.invalid/park.ogg')

    async def test_cortelyou_numbered_cross_held_with_recording(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import AsyncMock, Mock, patch
        import detect, main
        transcript = ('101-2457, 2129 Cortelyou Road, Flatbush Avenue to East 2nd Street, '
                      'alarm activation C2, Charlie 2. 101-2457, 2129 Cortelyou Road, '
                      'Flatbush Avenue to East 2nd Street, alarm activation apartment C2, Charlie 2.')
        self.assertIsNone(detect.analyze(transcript, 'fdny')['box_heard'])
        stats = Mock()
        with tempfile.TemporaryDirectory() as d:
            with (patch.object(main, '_fdny_fetch_clip', return_value=Path(d)/'clip.wav'),
                  patch.object(main, '_archive_clip'),
                  patch.object(main, '_save_seen'),
                  patch.object(main, '_held_recording', new_callable=AsyncMock, return_value='https://example.invalid/cortelyou.ogg') as recording,
                  patch.object(main, 'verify_and_send', new_callable=AsyncMock) as sender,
                  patch.object(main, '_append_alert_log'),
                  patch.object(main, 'ops_log'),
                  patch.object(main, '_kw_check', new_callable=AsyncMock)):
                await main._fdny_handle_call({'id':'cortelyou-test','transcription':transcript,
                                             'audio_url':'https://example.invalid/source.m4a'},
                                            stats, {}, Path(d))
        sender.assert_not_awaited()
        recording.assert_awaited_once()
        row = stats.mark_alert.call_args
        self.assertEqual(row.kwargs['outcome'], 'suppressed')
        self.assertIn('numbered cross street', row.kwargs['reason'])
        self.assertEqual(row.kwargs['voice_url'], 'https://example.invalid/cortelyou.ogg')

    async def test_floor_and_apartment_do_not_trigger_qualifier_hold(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import AsyncMock, Mock, patch
        import main
        cases = [
            ('Phone alarm, Brooklyn Box 573, 363 Bond Street, smoke the second floor.',
             'floor'),
            ('Brooklyn Box 1869, 251 Patchen Avenue, electrical fire apartment 2.',
             'apartment'),
            ('Brooklyn Box 573, 363 Bond Street, smoke.', 'no qualifier'),
        ]
        for transcript, name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                stats = Mock()
                with (patch.object(main, '_fdny_fetch_clip', return_value=Path(d)/'clip.wav'),
                      patch.object(main, '_archive_clip'),
                      patch.object(main, '_save_seen'),
                      patch.object(main, 'geocode_verify', new_callable=AsyncMock,
                                   return_value=(True, False, '363 BOND STREET, Brooklyn, NY', 40.0, -73.9, 'Brooklyn')),
                      patch.object(main, 'verify_and_send', new_callable=AsyncMock, return_value='sent') as sender,
                      patch.object(main, '_append_alert_log'),
                      patch.object(main, 'ops_log'),
                      patch.object(main, '_kw_check', new_callable=AsyncMock)):
                    await main._fdny_handle_call({'id':name,'transcription':transcript,
                                                 'audio_url':'https://example.invalid/source.m4a'},
                                                stats, {}, Path(d))
                sender.assert_awaited_once()
                self.assertEqual(stats.mark_alert.call_args.kwargs['outcome'], 'sent')

    async def test_fire_street_held_with_recording_and_no_send(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import AsyncMock, Mock, patch
        import detect, main
        transcript = ("We're in Queens, phone alarm box 1766, 656 Fire Street, "
                      "closing to Wortman Avenue. Engine 225, Ladder 107 are assigned.")
        hit = detect.analyze(transcript, 'fdny')
        self.assertEqual(hit['address'], '656 Fire Street, Queens, NY')
        stats = Mock()
        with tempfile.TemporaryDirectory() as d:
            with (patch.object(main, '_fdny_fetch_clip', return_value=Path(d)/'clip.wav'),
                  patch.object(main, '_archive_clip'),
                  patch.object(main, '_save_seen'),
                  patch.object(main, '_held_recording', new_callable=AsyncMock, return_value='https://example.invalid/clip.ogg') as recording,
                  patch.object(main, 'verify_and_send', new_callable=AsyncMock) as sender,
                  patch.object(main, '_append_alert_log') as log,
                  patch.object(main, 'ops_log'),
                  patch.object(main, '_kw_check', new_callable=AsyncMock)):
                await main._fdny_handle_call({'id':'test','transcription':transcript,
                                             'audio_url':'https://example.invalid/source.m4a'},
                                            stats, {}, Path(d))
            # The parser now preserves Queens; verification, rather than a
            # Brooklyn-default conflict, must reject the unverified location.
            sender.assert_awaited_once()
            self.assertEqual(sender.call_args.args[1]['address'], '656 Fire Street, Queens, NY')


class TestNumberedAddressDropped(unittest.TestCase):
    def test_park_avenue_live_transcript(self):
        transcript = ('Alarm 395, 56 North Oxford Walk to Park Avenue, alarm activation 3C, '
                      '3 Charles. Alarm, Box 395, 56 North Oxford Walk, I said Park Avenue.')
        self.assertEqual(unnumbered_with_spoken_building(
            transcript, 'Park Avenue, Brooklyn, NY'), '56 North Oxford Walk')

    def test_numbered_parsed_address_passes(self):
        self.assertEqual(unnumbered_with_spoken_building(
            'Box 4002, 519 Gateway Drive at Erskine Street, automatic alarm',
            '519 Gateway Drive, Brooklyn, NY'), '')

    def test_box_number_and_numbered_street_are_not_buildings(self):
        self.assertEqual(unnumbered_with_spoken_building(
            'Box 1766, 13th Avenue at 50th Street, phone alarm',
            '13th Avenue, Brooklyn, NY'), '')
        self.assertEqual(unnumbered_with_spoken_building(
            'Box 1766 Fire Street phone alarm',
            'Fire Street, Brooklyn, NY'), '')


class TestNoDerivedBox(unittest.TestCase):
    def test_formatter_omits_box_when_not_spoken(self):
        import main
        hit = {'source':'fdny','nature':'Alarm Activation',
               'address':'2129 Cortelyou Road, Brooklyn, NY'}
        out = main.format_alert(hit, crosses='Flatbush Avenue & East 22nd Street',
                                confirmed=True, box='')
        self.assertNotIn('Box ', out)
        self.assertIn('2129 Cortelyou Road', out)

    def test_no_nearest_box_fallback_in_fdny_send_tail(self):
        import inspect, main
        body = inspect.getsource(main.verify_and_send)
        self.assertNotIn('nb_digits, nb_loc', body)
        self.assertNotIn('no box obtainable', body)


class TestSullivanManDown(unittest.TestCase):
    def test_varnell_audio_transcript(self):
        import detect
        text = ('5263 first respond. First respond, man down, unknown life status, '
                '82 Varnell Road off of West Broadway, 228.')
        hit = detect.analyze(text, 'sullivan')
        self.assertEqual(hit['nature'], 'Man Down, Unknown Life Status')
        self.assertEqual(hit['address'], '82 Varnell Road, Sullivan Co, NY')

    def test_no_diagnosis_inferred(self):
        import detect
        hit = detect.analyze('Man down at 82 Varnell Road, Sullivan County', 'sullivan')
        self.assertEqual(hit['nature'], 'Man Down')


class TestNewHeldCaseParser(unittest.TestCase):
    def test_queens_second_alarm_hyphenated_house(self):
        import detect
        t = ("We're announcing the Borough Queens, a second alarm transmitted, "
             "Box 4374, 159-22 Hillside Avenue, Parsons Boulevard to 160th Street. "
             "Fire is in a two-story mixed occupancy.")
        hit = detect.analyze(t, "fdny")
        self.assertEqual(hit["address"], "159-22 Hillside Avenue, Queens, NY")
        self.assertEqual(hit["nature"], "Second Alarm")
        self.assertEqual(hit["cross"], "Parsons Boulevard & 160th Street")
        self.assertTrue(exact_numbered_fdny_match(hit["address"],
            "159-22 HILLSIDE AVENUE, Jamaica, NY, USA"))
        self.assertFalse(exact_numbered_fdny_match(hit["address"],
            "159-24 HILLSIDE AVENUE, Jamaica, NY, USA"))

    def test_sullivan_groq_asr_keeps_town_but_road_needs_map(self):
        import detect
        hit = detect.analyze("Dispatch to lock sheltering, activated fire alarm, 48 anemone lane", "sullivan")
        self.assertEqual(hit["address"], "48 Anemone Lane, Loch Sheldrake, NY")
        self.assertEqual(hit["nature"], "Activated Fire Alarm")

    def test_hatzalah_without_complaint_remains_held(self):
        import detect
        hit = detect.analyze("W106, 357 Fraser Road in a private house", "hatzolah")
        self.assertEqual(hit["nature"], "")

    def test_fdny_smoke_address_not_released_by_a_parser_test(self):
        import detect
        hit = detect.analyze("Box 2684, 974 45th Street, 9th to 10th Avenues, odor of smoke in the area", "fdny")
        self.assertEqual(hit["address"], "974 45th Street, Brooklyn, NY")
        self.assertEqual(hit["nature"], "Smoke in the area")
        # This historical call stays held by the owner's one-off instruction.


class TestBoroughGeocoder(unittest.IsolatedAsyncioTestCase):
    async def test_queens_address_matches_neighborhood_label_only_with_queens_feature(self):
        from unittest.mock import AsyncMock, patch
        import main
        with patch.object(main, "_planning_labs", new_callable=AsyncMock,
                          return_value=("159-22 HILLSIDE AVENUE, Jamaica, NY, USA", 40.707685, -73.801896)) as pl:
            out = await main.geocode_verify("159-22 Hillside Avenue, Queens, NY", "fdny")
        self.assertTrue(out[0])
        self.assertEqual(out[5], "Queens")
        self.assertEqual(pl.call_args.args[1], ["Queens"])
        with patch.object(main, "_planning_labs", new_callable=AsyncMock,
                          return_value=(None, None, None)):
            no = await main.geocode_verify("159-22 Hillside Avenue, Queens, NY", "fdny")
        self.assertFalse(no[0])

    async def test_spoken_borough_does_not_let_unit_affiliation_move_job(self):
        from fdny_borough_gate import spoken_job_borough
        self.assertEqual(spoken_job_borough("We're announcing the Borough Queens, box 4374"), "Queens")
        self.assertEqual(spoken_job_borough("Queens unit responding to 123 Main Street"), "")
        self.assertEqual(spoken_job_borough("Phone alarm 123 Queens Street, Brooklyn"), "")


class TestSullivanTextNoGenericCounty(unittest.TestCase):
    def test_held_review_unverified_road_has_no_county_suffix(self):
        import main
        hit = {"address": "48 Anemone Lane, Sullivan Co, NY", "nature": "",
               "hold_reason": "no nature"}
        text = main._held_review_text("zello-sullivan", hit)
        self.assertIn("48 Anemone Lane", text)
        self.assertNotIn("Sullivan Co, NY", text)
        self.assertNotIn("Loch Sheldrake", text)
        hit["address"] = "48 Anemone Lane, Loch Sheldrake, NY"
        text = main._held_review_text("zello-sullivan", hit)
        self.assertIn("48 Anemone Lane", text)
        self.assertNotIn("Loch Sheldrake", text)

    def test_formatted_alert_uses_only_road_and_verified_area(self):
        import main
        hit = {"source": "zello-sullivan", "address": "48 Anemone Lane, Sullivan Co, NY",
               "nature": "Activated Fire Alarm", "verified_area": "Loch Sheldrake"}
        text = main.format_alert(hit, crosses="Bridge Circle", confirmed=True)
        self.assertIn("*48 Anemone Lane*", text)
        self.assertIn("*LOCH SHELDRAKE*", text)
        self.assertNotIn("Sullivan Co, NY", text)
        del hit["verified_area"]
        text = main.format_alert(hit, confirmed=False)
        self.assertIn("*48 Anemone Lane*", text)
        self.assertNotIn("Sullivan Co, NY", text)
        self.assertNotIn("*LOCH SHELDRAKE*", text)


class TestFdnySpokenBoroughFooter(unittest.TestCase):
    def test_queens_announcement_not_labeled_brooklyn(self):
        import main
        msg = main.format_alert({"source": "fdny", "nature": "Second Alarm",
                                 "address": "159-22 Hillside Avenue, Queens, NY"})
        self.assertIn("FDNY Brooklyn feed - Queens borough announcement", msg)
        self.assertNotIn("FDNY Brooklyn Dispatch", msg)


class TestSecondListenGate(unittest.IsolatedAsyncioTestCase):
    async def test_off_by_default_and_only_after_hold(self):
        import main
        from unittest.mock import AsyncMock, Mock, patch
        hit = {"address": "48 Anemone Lane, Loch Sheldrake, NY", "nature": "",
               "hold_reason": "no nature"}
        with patch.object(main.transcribe, "GROQ_ENABLED", False), patch.object(
                main, "verify_and_send", new_callable=AsyncMock, return_value="suppressed") as verify, patch.object(
                main.transcribe, "second_listen") as groq:
            result, same = await main.verify_zello_with_second_listen(
                "zello-sullivan", hit, Mock(), "a.wav", fresh_ts=100)
        self.assertEqual(result, "suppressed")
        self.assertIs(same, hit)
        verify.assert_awaited_once()
        groq.assert_not_called()

    async def test_same_road_recovery_gets_full_reverification_once(self):
        import main
        from unittest.mock import AsyncMock, Mock, patch
        hit = {"address": "48 Anemone Lane, Loch Sheldrake, NY", "nature": "",
               "hold_reason": "no nature"}
        fake = "Dispatch to Loch Sheldrake, activated fire alarm, 48 Anemone Lane"
        with patch.object(main.transcribe, "GROQ_ENABLED", True), patch.object(
                main.ARCHIVE_DIR.__class__, "is_file", return_value=True), patch.object(
                main, "verify_and_send", new_callable=AsyncMock,
                side_effect=["suppressed", "sent"]) as verify, patch.object(
                main.transcribe, "second_listen", return_value=fake) as groq:
            result, revised = await main.verify_zello_with_second_listen(
                "zello-sullivan", hit, Mock(), "a.wav", fresh_ts=100)
        self.assertEqual(result, "sent")
        self.assertEqual(revised["nature"], "Activated Fire Alarm")
        self.assertEqual(verify.await_count, 2)
        groq.assert_called_once()

    async def test_second_ear_cannot_change_known_complaint(self):
        import main
        from unittest.mock import AsyncMock, Mock, patch
        hit = {"address": "48 Anemone Lane, Loch Sheldrake, NY",
               "nature": "Activated Fire Alarm", "hold_reason": "no verified location"}
        fake = "Dispatch to Loch Sheldrake, structure fire, 48 Anemone Lane"
        with patch.object(main.transcribe, "GROQ_ENABLED", True), patch.object(
                main.ARCHIVE_DIR.__class__, "is_file", return_value=True), patch.object(
                main, "verify_and_send", new_callable=AsyncMock,
                return_value="suppressed") as verify, patch.object(
                main.transcribe, "second_listen", return_value=fake):
            result, same = await main.verify_zello_with_second_listen(
                "zello-sullivan", hit, Mock(), "a.wav", fresh_ts=100)
        self.assertEqual(result, "suppressed")
        self.assertIs(same, hit)
        verify.assert_awaited_once()

    async def test_different_road_stays_held(self):
        import main
        from unittest.mock import AsyncMock, Mock, patch
        hit = {"address": "48 Anemone Lane, Loch Sheldrake, NY", "nature": "",
               "hold_reason": "no nature"}
        fake = "Dispatch to Loch Sheldrake, activated fire alarm, 48 Different Road"
        with patch.object(main.transcribe, "GROQ_ENABLED", True), patch.object(
                main.ARCHIVE_DIR.__class__, "is_file", return_value=True), patch.object(
                main, "verify_and_send", new_callable=AsyncMock, return_value="suppressed") as verify, patch.object(
                main.transcribe, "second_listen", return_value=fake):
            result, same = await main.verify_zello_with_second_listen(
                "zello-sullivan", hit, Mock(), "a.wav", fresh_ts=100)
        self.assertEqual(result, "suppressed")
        self.assertIs(same, hit)
        verify.assert_awaited_once()


class TestThirdAlarmAndIntersection(unittest.TestCase):
    def test_queens_third_alarm_despite_brooklyn_chatter(self):
        import detect
        t = ("Brooklyn Housing, Queens, a third alarm transmitted Box 4374, "
             "159-22 Hillside Avenue, Parsons Boulevard to 160th Street. "
             "Fire is in a two-story mixed occupancy.")
        h = detect.analyze(t, "fdny")
        self.assertEqual(h["address"], "159-22 Hillside Avenue, Queens, NY")
        self.assertEqual(h["nature"], "Third Alarm")

    def test_spoken_intersection_is_not_a_house_number(self):
        import detect
        h = detect.analyze("6th Avenue at 65th Street, motor vehicle accident", "fdny")
        self.assertEqual(h["address"], "6th Ave & 65th St, Brooklyn, NY")
        self.assertEqual(h["nature"], "Motor Vehicle Accident")
        self.assertEqual(unnumbered_with_spoken_building(h["excerpt"], h["address"]), "")


class TestIntersectionPosting(unittest.IsolatedAsyncioTestCase):
    async def test_mva_intersection_uses_two_road_map_gate(self):
        import main, detect
        from unittest.mock import AsyncMock, Mock, patch
        hit = detect.analyze("6th Avenue at 65th Street, motor vehicle accident", "fdny")
        sent = []
        with patch.object(main, "_intersection_point", new_callable=AsyncMock,
                          return_value=(40.6352161, -74.0170054)) as crossing, patch.object(
                main.alert_waha, "send_text", new_callable=AsyncMock,
                side_effect=lambda text: sent.append(text) or True), patch.object(
                main, "_load_recent", return_value=[]), patch.object(
                main, "_save_recent"), patch.object(main, "ops_log"), patch.object(
                main, "_map_street_names", new_callable=AsyncMock, return_value=set()):
            outcome = await main.verify_and_send("fdny", hit, Mock(), None)
        self.assertEqual(outcome, "sent")
        self.assertEqual(len(sent), 1)
        self.assertIn("6th Ave & 65th St", sent[0])
        crossing.assert_awaited()

    async def test_mva_unverified_intersection_stays_held(self):
        import main, detect
        from unittest.mock import AsyncMock, Mock, patch
        hit = detect.analyze("6th Avenue at 65th Street, motor vehicle accident", "fdny")
        with patch.object(main, "_intersection_point", new_callable=AsyncMock,
                          return_value=(None, None)), patch.object(
                main, "geocode_verify", new_callable=AsyncMock,
                return_value=(False, False, "", None, None, "")), patch.object(
                main, "_correct_street_via_crosses", new_callable=AsyncMock,
                return_value=""), patch.object(
                main.alert_waha, "send_text", new_callable=AsyncMock) as sender, patch.object(
                main, "_load_recent", return_value=[]), patch.object(
                main, "_save_recent"), patch.object(main, "ops_log"):
            outcome = await main.verify_and_send("fdny", hit, Mock(), None)
        self.assertEqual(outcome, "suppressed")
        sender.assert_not_awaited()


class TestRepeatedFdnyHouse(unittest.TestCase):
    def test_class_three_then_1500_east_92(self):
        import detect
        t = ("East 92 Street, Avenue M to Avenue L, automatic alarm, PS 115. "
             "Unassigned Class 3, 2287, 1500 East 92 Street, Avenue M/Mary "
             "to Avenue L/Lincoln, automatic alarm, PS 115.")
        h = detect.analyze(t, "fdny")
        self.assertEqual(h["address"], "1500 East 92 Street, Brooklyn, NY")
        self.assertEqual(h["nature"], "Automatic Alarm")
        self.assertTrue(exact_numbered_fdny_match(h["address"],
                        "1500 EAST 92 STREET, Brooklyn, NY, USA"))
