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
        self.assertEqual(hit['address'], '656 Fire Street, Brooklyn, NY')
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
            sender.assert_not_awaited()
            recording.assert_awaited_once()
            row = stats.mark_alert.call_args
            self.assertEqual(row.args[0:4], ('fdny', 'Phone Alarm', '656 Fire Street, Brooklyn, NY', False))
            self.assertEqual(row.kwargs['outcome'], 'suppressed')
            self.assertIn('dispatch says Queens', row.kwargs['reason'])
            self.assertEqual(row.kwargs['voice_url'], 'https://example.invalid/clip.ogg')
            self.assertFalse(log.call_args.args[0]['sent'])


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
