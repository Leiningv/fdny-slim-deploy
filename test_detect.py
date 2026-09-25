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
        self.assertEqual(hit["nature"], "MVA")

    def test_sullivan_area_suffix(self):
        t = "Monticello fire, route 42 and main street, report of a structure fire"
        hit = detect.analyze(t, "sullivan")
        self.assertIsNotNone(hit)
        self.assertTrue(hit["address"].endswith("Monticello, NY"), hit["address"])
        self.assertEqual(hit["nature"], "Fire")

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
