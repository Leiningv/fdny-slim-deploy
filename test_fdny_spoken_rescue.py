"""Audio-confirmed dispatch complaints and job-local borough regressions."""
import unittest
import detect
from fdny_borough_gate import spoken_job_borough


class SpokenDispatchRegression(unittest.TestCase):
    def test_1409_new_york_smoke_and_two_typed_crosses(self):
        t = ("Phone alarm box 2427, 1409 New York Avenue, Foster Avenue and "
             "Farragut Road, smoke, caller's in apartment 6 G. "
             "Phone alarm box 2427, 1409 New York Avenue, Foster Avenue and "
             "Farragut Road, smoke, caller's in apartment 6 G.")
        h = detect.analyze(t, "fdny")
        self.assertEqual(h["nature"], "Smoke, Apartment 6G")
        self.assertEqual(h["cross"], "Foster Avenue & Farragut Road")
        self.assertEqual(h["address"], "1409 New York Avenue, Brooklyn, NY")

    def test_queens_one_alarm_opener_beats_later_unit_affiliation(self):
        t = ("19 Queens, one alarm box 2139. The address 93-18 Liberty Avenue. "
             "Reporting a fire in a commercial building. 107 from Brooklyn is assigned.")
        h = detect.analyze(t, "fdny")
        self.assertEqual(h["address"], "93-18 Liberty Avenue, Queens, NY")
        self.assertEqual(h["nature"], "Fire in a Commercial Building")

    def test_borough_not_inferred_from_unit_or_road_name(self):
        self.assertEqual(spoken_job_borough("Engine 107 from Queens assigned to Box 2139"), "")
        self.assertEqual(spoken_job_borough("Queens Boulevard Box 2139 automatic alarm"), "")

    def test_unrelated_smoke_chatter_not_promoted(self):
        t = ("Phone Alarm box 2427, 1409 New York Avenue, "
             "no smoke reported, caller's in apartment 6 G")
        self.assertEqual(detect.analyze(t, "fdny")["nature"], "Phone Alarm, Apartment 6G")

    def test_two_box_smoke_and_borough_are_not_globally_promoted(self):
        t = ("Queens, one alarm Box 2139, 93-18 Liberty Avenue, Phone Alarm. "
             "Brooklyn Box 2427, 1409 New York Avenue, smoke, caller's in apartment 6 G")
        self.assertEqual(spoken_job_borough(t), "")
        self.assertNotEqual(detect.get_nature(t, "fdny"), "Smoke")

    def test_440_atlantic_spoken_odor_of_smoke_beats_phone_alarm(self):
        t = ("Phone alarm box 586, 440 Atlantic Avenue, Nevins Street to Bond "
             "Street, odor of smoke, first floor. "
             "Phone alarm box 586, 440 Atlantic Avenue, Nevins Street to Bond "
             "Street, odor of smoke, first floor.")
        h = detect.analyze(t, "fdny")
        self.assertEqual(h["nature"], "Odor of Smoke, First Floor")
        self.assertEqual(h["address"], "440 Atlantic Avenue, Brooklyn, NY")
        self.assertNotEqual(detect.get_nature(t.replace("odor of smoke", "no odor of smoke"),
                                               "fdny"), "Odor of Smoke")
        self.assertNotEqual(detect.get_nature(t + " Brooklyn Box 1703, automatic alarm",
                                               "fdny"), "Odor of Smoke")

    def test_existing_bare_and_typed_cross_rules(self):
        t = "Box 653, 362 Lafayette Avenue, Classon and Grand Avenue, smoke on the number one floor"
        h = detect.analyze(t, "fdny")
        self.assertEqual(h["cross"], "Classon & Grand Avenue")
        self.assertEqual(h["nature"], "Smoke on the Number One Floor")


if __name__ == '__main__':
    unittest.main()
