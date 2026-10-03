import unittest
import detect

class LabelWordAddress(unittest.TestCase):
    def test_address_label_not_street(self):
        t = "238 238 respond to 118 address White Avenue North 13 Street for a commercial fire."
        self.assertEqual(detect.extract_dispatch_address(t, "fdny"), "118 White Avenue, Brooklyn, NY")

    def test_location_label_not_street(self):
        t = "Box 238 118 location White Avenue North 13 Street fire"
        self.assertEqual(detect.extract_dispatch_address(t, "fdny"), "118 White Avenue, Brooklyn, NY")

if __name__ == "__main__":
    unittest.main()
