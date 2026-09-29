"""Regression for the 10:20 Union Street Hatzalah source recordings.

The first clip independently says both the complaint and the numbered location.
Do not borrow a complaint from a different job merely because clips are adjacent.
"""
import unittest

import detect
import main


FIRST = ("It's in the CH for 1339 Union Street between Brooklyn and New York "
         "for the unresponsive.")
SECOND = ("CH-61, you're heading to 1339 Union Street between Brooklyn and "
          "New York Avenue. CH-61. To back up to Union, Brooklyn to New York. "
          "CH-84-43. CH-84-43, you're heading to 1339 Union.")


class UnionStreetDispatch(unittest.TestCase):
    def test_first_clip_keeps_numbered_address_and_nature(self):
        hit = detect.analyze(FIRST, "zello-hatzalah")
        self.assertEqual(hit["address"], "1339 Union Street, Brooklyn, NY")
        self.assertEqual(hit["nature"], "Unresponsive")
        self.assertEqual(hit["cross"], "Brooklyn & New York")

    def test_repeated_clip_keeps_numbered_address_but_does_not_invent_nature(self):
        hit = detect.analyze(SECOND, "zello-hatzalah")
        self.assertEqual(hit["address"], "1339 Union Street, Brooklyn, NY")
        self.assertEqual(hit["nature"], "")

    def test_concatenated_repeats_remain_one_full_job(self):
        spans = detect.split_dispatch_jobs(FIRST + " " + SECOND, "zello-hatzalah")
        self.assertEqual(len(spans), 1)
        hit = detect.analyze(spans[0], "zello-hatzalah")
        self.assertEqual((hit["nature"], hit["address"]),
                         ("Unresponsive", "1339 Union Street, Brooklyn, NY"))

    def test_different_numbered_address_cannot_join_the_incident(self):
        rec = {"start": 100., "stop": 105., "address": "1339 Union Street, Brooklyn, NY",
               "nature": "Unresponsive", "opener": False}
        self.assertFalse(main._ptt_group_match(
            rec, 107., "1340 Union Street, Brooklyn, NY", 8., "Unresponsive"))

    def test_bare_crosses_with_no_number_do_not_invent_a_house(self):
        text = "Unresponsive at Brooklyn and New York."
        hit = detect.analyze(text, "zello-hatzalah")
        self.assertFalse(hit and hit["address"].startswith("1339 Union"))

    def test_separate_medic_job_does_not_launder_nature_to_first_address(self):
        text = ("Backup at 1339 Union Street. Medic call at Brooklyn and New York "
                "for unresponsive.")
        hit = detect.analyze(text, "zello-hatzalah")
        self.assertFalse(hit and hit["nature"] == "Unresponsive" and
                         hit["address"] == "1339 Union Street, Brooklyn, NY")

    def test_distinct_nature_cannot_join_the_incident(self):
        rec = {"start": 100., "stop": 105., "address": "1339 Union Street, Brooklyn, NY",
               "nature": "Unresponsive", "opener": False}
        self.assertFalse(main._ptt_group_match(
            rec, 107., "1339 Union Street, Brooklyn, NY", 8., "Difficulty Breathing"))


class AvenueUDispatch(unittest.TestCase):
    def test_spoken_numbered_letter_avenue_and_manual_alarm(self):
        text = ("Class 3-33-36, Terminal 6, 1111 Avenue U, East 12 to "
                "Coney Island Avenue, on a manual alarm.")
        hit = detect.analyze(text, "fdny")
        self.assertEqual((hit["address"], hit["nature"]),
                         ("1111 Avenue U, Brooklyn, NY", "Manual Alarm"))
        from fdny_borough_gate import unnumbered_with_spoken_building
        self.assertEqual(unnumbered_with_spoken_building(text, hit["address"]), "")
        self.assertIsNone(hit["box_heard"])

    def test_repeated_location_keeps_full_address_without_inventing_nature(self):
        text = ("Class 33336, Terminal 6. 1111 Avenue U, East 12 to "
                "Coney Island Avenue and Avenue U.")
        hit = detect.analyze(text, "fdny")
        self.assertEqual(hit["address"], "1111 Avenue U, Brooklyn, NY")
        self.assertEqual(hit["nature"], "")

    def test_cross_number_is_not_spoken_building(self):
        from fdny_borough_gate import unnumbered_with_spoken_building
        self.assertEqual(unnumbered_with_spoken_building(
            "East 12 to Coney Island Avenue, manual alarm",
            "Coney Island Avenue, Brooklyn, NY"), "")

    def test_older_park_walk_building_hold_remains(self):
        from fdny_borough_gate import unnumbered_with_spoken_building
        self.assertEqual(unnumbered_with_spoken_building(
            "Alarm 395, 56 North Oxford Walk to Park Avenue, alarm activation",
            "Park Avenue, Brooklyn, NY"), "56 North Oxford Walk")

class SullivanAreaPresentation(unittest.IsolatedAsyncioTestCase):
    async def test_verified_town_replaces_county_and_crosses_below(self):
        from unittest.mock import AsyncMock, Mock, patch
        hit = {"source": "zello-sullivan", "nature": "Difficulty Breathing",
               "address": "888 Resorts World Drive, Sullivan Co, NY",
               "excerpt": "Town of Thompson, 888 Resorts World Drive, difficulty breathing",
            "cross": "Conklin Drive & Lynn Road",
               "box_heard": None}
        label = ("Resorts World Catskills, 888, Resorts World Drive, Village of Monticello, "
                 "Town of Thompson, Sullivan County, New York")
        with (patch.object(main, 'geocode_verify', new_callable=AsyncMock,
                           return_value=(True, True, label, 41.65, -74.64,
                                         'Village of Monticello')),
              patch.object(main, 'control') as control,
              patch.object(main, '_load_recent', return_value=[]),
              patch.object(main, '_cross_streets', new_callable=AsyncMock,
                           return_value=("Conklin Drive & Lynn Road", True)),
              patch.object(main, '_map_street_names', new_callable=AsyncMock,
                           return_value=set()),
              patch.object(main, '_uguu_upload', new_callable=AsyncMock),
              patch.object(main.alert_waha, 'send_text', new_callable=AsyncMock,
                           return_value=True) as send,
              patch.object(main, 'ops_log')):
            control.muted_feeds.return_value = set()
            outcome = await main.verify_and_send('zello-sullivan', hit, Mock())
        self.assertEqual(outcome, 'sent')
        sent = send.await_args.args[0]
        self.assertIn('📍 *888 Resorts World Drive*\n*THOMPSON*\nC/s Conklin Drive & Lynn Road', sent)
        self.assertNotIn('Sullivan Co, NY', sent)

    def test_without_verified_area_formatter_does_not_guess(self):
        hit = {'source': 'zello-sullivan', 'nature': 'Difficulty Breathing',
               'address': '888 Resorts World Drive, Sullivan Co, NY'}
        sent = main.format_alert(hit)
        self.assertIn('📍 *888 Resorts World Drive*', sent)
        self.assertNotIn('Sullivan Co, NY', sent)
        self.assertNotIn('*THOMPSON*', sent)
