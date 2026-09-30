import unittest
from detect import analyze, extract_apartment

class ApartmentPunctuation(unittest.TestCase):
    def test_ralph_vendor_comma_after_label(self):
        t = "283, 37-3. 283 to follow on 1621. The address, 468 Ralph Avenue, cross street place to St. Mark's Avenue. Smoke apartment, 3 Robert, Engine 283. 283."
        a = analyze(t, 'fdny')
        self.assertEqual(a['nature'], 'Smoke, Apartment 3R')
        self.assertEqual(a['address'], '468 Ralph Avenue, Brooklyn, NY')

    def test_ralph_vendor_comma_after_number(self):
        t = "10-4, respond. Box. 1621, the address 468 Ralph Avenue between Prospect Place and St. Mark's Avenue for smoke, apartment 3, Robert."
        self.assertEqual(analyze(t, 'fdny')['nature'], 'Smoke, Apartment 3R')

    def test_explicit_comma_forms(self):
        for t in ['apartment, 3 Robert', 'apartment 3, Robert', 'apt, 3, Robert', 'apartment, 3R']:
            self.assertEqual(extract_apartment(t), 'Apartment 3R')
        self.assertEqual(extract_apartment('apartment, 3'), 'Apartment 3')

    def test_no_new_phonetic_or_unit_inference(self):
        self.assertEqual(extract_apartment('apartment, 3 Rainbow'), 'Apartment 3')
        self.assertEqual(extract_apartment('Engine, 3 Robert'), '')
        self.assertEqual(extract_apartment('unit, 3 Robert'), '')
        self.assertEqual(extract_apartment('apartment, Engine 283'), '')
        self.assertEqual(extract_apartment('apartment 3. Robert'), 'Apartment 3')

if __name__ == '__main__': unittest.main()
