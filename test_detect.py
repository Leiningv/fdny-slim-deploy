"""Unit tests for detect.py — realistic dispatch transcripts + edge cases."""
import unittest

import detect


class TestDetect(unittest.TestCase):
    def test_hatzolah_grid_difficulty_breathing(self):
        t = ("Hatzolah to Boro Park, respond to 13th avenue and 50th street, "
             "for a patient with difficulty breathing")
        hit = detect.analyze(t, "hatzolah")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["address"], "13th Ave & 50th St, Brooklyn, NY")
        self.assertEqual(hit["nature"], "Difficulty Breathing")

    def test_hatzolah_bare_grid(self):
        t = "Hatzolah units respond, 14 and 46, child not breathing"
        hit = detect.analyze(t, "hatzolah")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["address"], "14th Ave & 46th St, Brooklyn, NY")

    def test_grid_command_not_a_street_and_unit_pair_not_a_place(self):
        text = ("Hatzolah to Boro Park, respond to 13th avenue and 50th street, "
                "for a patient with difficulty breathing")
        hit = detect.analyze(text, "hatzolah")
        self.assertEqual(hit["address"], "13th Ave & 50th St, Brooklyn, NY")
        self.assertNotIn("respond", hit["address"].lower())
        self.assertIsNone(detect.analyze(
            "62 and 47 is by the car, patient is unresponsive", "hatzolah"))

    def test_bare_grid_does_not_override_numbered_house(self):
        hit = detect.analyze(
            "Unit 62 and 47 respond for a cardiac arrest at 5014 15th Avenue", "hatzolah")
        self.assertEqual(hit["address"], "5014 15th Avenue, Brooklyn, NY")

    def test_sullivan_route_exit_only_complete_route_exit_candidate(self):
        text = ("Sullivan county dispatch, Beaverkill Valley, route 17 exit 104, "
                "motor vehicle accident with possible entrapment")
        hit = detect.analyze(text, "sullivan")
        self.assertEqual(hit["address"], "Route 17 at Exit 104, Sullivan Co, NY")
        self.assertEqual(hit["nature"], "Motor Vehicle Accident")
        self.assertIsNone(detect.analyze("Route 17 radio check", "sullivan"))

    def test_hatzolah_house_address_fall(self):
        t = "Hatzolah responding to 5014 15th avenue for an elderly fall"
        hit = detect.analyze(t, "hatzolah")
        self.assertIsNotNone(hit)
        self.assertIn("5014 15th Ave", hit["address"])
        self.assertEqual(hit["nature"], "Fall")

    def test_hatzolah_cardiac_arrest(self):
        t = "Hatzolah, cardiac arrest, 18th avenue and 60th street, start CPR"
        hit = detect.analyze(t, "hatzolah")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["nature"], "Cardiac Arrest")

    def test_sullivan_highway_exit_mva(self):
        t = ("Sullivan county dispatch, Beaverkill Valley, route 17 exit 104, "
             "motor vehicle accident with possible entrapment")
        hit = detect.analyze(t, "sullivan")
        self.assertIsNotNone(hit)
        self.assertIn("Route 17 at Exit 104", hit["address"])
        self.assertEqual(hit["nature"], "Motor Vehicle Accident")

    def test_sullivan_area_suffix(self):
        t = "Monticello fire, route 42 and main street, report of a structure fire"
        hit = detect.analyze(t, "sullivan")
        self.assertIsNotNone(hit)
        self.assertTrue(hit["address"].endswith("Monticello, NY"), hit["address"])
        self.assertEqual(hit["nature"], "Structure Fire")

    def test_emergency_but_no_address_no_alert(self):
        t = "Hatzolah responding, patient with difficulty breathing, units stand by"
        self.assertIsNone(detect.analyze(t, "hatzolah"))

    def test_non_emergency_chatter_no_alert(self):
        t = "check your whatsapp for the updated roster and shift change notes"
        self.assertIsNone(detect.analyze(t, "hatzolah"))

    def test_radio_check_no_alert(self):
        t = "radio check, radio check, can you hear me on this channel"
        self.assertIsNone(detect.analyze(t, "sullivan"))

    def test_empty_and_short_no_alert(self):
        self.assertIsNone(detect.analyze("", "hatzolah"))
        self.assertIsNone(detect.analyze("yeah", "hatzolah"))

    def test_negative_fire_not_fire(self):
        t = "units on scene at 12th avenue and 39th street, no fire, just burnt food"
        hit = detect.analyze(t, "hatzolah")
        # emergency pattern matched via address/units; nature must not be "Fire"
        if hit:
            self.assertNotEqual(hit["nature"], "Fire")

    def test_highway_direction(self):
        t = "accident on the belt parkway westbound near bay parkway"
        hit = detect.analyze(t, "hatzolah")
        self.assertIsNotNone(hit)
        self.assertIn("Belt Pkwy", hit["address"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
