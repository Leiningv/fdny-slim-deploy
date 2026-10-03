import unittest
import detect

class NumberStreetDirection(unittest.TestCase):
    def test_west_number_5_street_keeps_house(self):
        t = "Box 3577 2940 West Number 5 Street. Sea Breeze to Neptune Avenue is reporting smoke, apartment 12 Frank."
        self.assertEqual(detect.extract_dispatch_address(t, "fdny"), "2940 West 5th Street, Brooklyn, NY")

    def test_plain_number_street_unchanged(self):
        t = "261 Number 9 Street. Sea Breeze to Neptune Avenue reporting smoke"
        self.assertEqual(detect.extract_dispatch_address(t, "fdny"), "261 9th Street, Brooklyn, NY")

if __name__ == "__main__":
    unittest.main()
