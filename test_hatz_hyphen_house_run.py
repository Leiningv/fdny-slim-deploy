import unittest

import main

P = "zello-hatzalah"
# Real clip 10/3 9:45 PM EDT: independent heard 5228 Utrecht Avenue; the service posted 28.
REAL = ("Units 5-2 on the Utrecht, patient not feeling well. 5-4. 5-5, Division Service Medrish, "
        "5-2-28 on the Utrecht Avenue. Take 265. B-903 is going to 5-2-28 Utrecht.")


class HyphenHouseRun(unittest.TestCase):
    def hit(self, text, addr="28 Utrecht Avenue, Brooklyn, NY"):
        return {"nature": "Not Feeling Well", "address": addr, "dispatch_source_text": text}

    def test_real_utrecht_clip_held(self):
        self.assertTrue(main._hyphen_digit_house_run(P, self.hit(REAL)))

    def test_plain_house_number_posts(self):
        self.assertFalse(main._hyphen_digit_house_run(P, self.hit("patient not feeling well 5228 Utrecht Avenue", "5228 Utrecht Avenue, Brooklyn, NY")))
        self.assertFalse(main._hyphen_digit_house_run(P, self.hit("unit 5-2 respond to 28 Utrecht Avenue")))

    def test_unit_number_elsewhere_posts(self):
        self.assertFalse(main._hyphen_digit_house_run(P, self.hit("Units 5-2 on the Utrecht, patient not feeling well. 28 Utrecht Avenue.")))

    def test_other_feeds_not_affected(self):
        self.assertFalse(main._hyphen_digit_house_run("fdny", self.hit(REAL)))
        self.assertFalse(main._hyphen_digit_house_run("zello-sullivan", self.hit(REAL)))

    def test_analyze_reproduces_and_guard_holds(self):
        import detect
        h = detect.analyze(REAL, P)
        self.assertEqual(h["address"], "28 Utrecht Avenue, Brooklyn, NY")
        self.assertTrue(main._hyphen_digit_house_run(P, h))
