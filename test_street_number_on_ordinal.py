import unittest

import detect


class StreetNumberOnOrdinal(unittest.TestCase):
    def test_84_on_3rd_avenue_is_not_a_house(self):
        t = "84 on 3rd Avenue for an elderly AMS 8th floor. Any units for East 84 on Third Avenue?"
        for profile in ("hatzolah", "fdny"):
            self.assertEqual(detect.extract_dispatch_address(t, profile), "3rd Avenue, Brooklyn, NY")

    def test_real_houses_unchanged(self):
        f = detect.extract_dispatch_address
        self.assertEqual(f("1255 on 5th avenue chest pain", "hatzolah"), "1255 5th Avenue, Brooklyn, NY")
        self.assertEqual(f("5014 15th Avenue chest pain", "hatzolah"), "5014 15th Avenue, Brooklyn, NY")
        self.assertEqual(f("67 Old Ryan Road ALS chest pain", "hatzolah"), "67 Old Ryan Road, Brooklyn, NY")


if __name__ == "__main__":
    unittest.main()
