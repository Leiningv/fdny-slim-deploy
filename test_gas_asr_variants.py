import unittest
import detect,fdny_audio_gate
class GasVariants(unittest.TestCase):
    def test_madison_bounded_order_of_gas(self):
        t='Brooklyn Phone Alarm Box 934, address is 381 Madison Street between Troop Avenue and Tompkins Avenue, order of gas in basement.'
        h=detect.analyze(t,'fdny')
        self.assertEqual(h['nature'],'Odor of Gas, Basement')
        self.assertEqual(h['address'],'381 Madison Street, Brooklyn, NY')
    def test_zero_odor_uncertain_not_upgraded(self):
        t='Phone Alarm Box 3282, East 29th Street, Avenue Z, zero odor, gas in the area.'
        h=detect.analyze(t,'fdny')
        self.assertEqual(h['nature'],'Phone Alarm')
        self.assertTrue(fdny_audio_gate.generic_nature_invariant(t,h['nature']))
    def test_variants_veto_fallback(self):
        self.assertTrue(fdny_audio_gate.generic_nature_invariant('order of gas in basement','Phone Alarm'))
    def test_negatives_not_promoted(self):
        for p in ['no ','not ','test ','training ']:
            t='Box 934 381 Madison Street '+p+'order of gas in basement'
            self.assertNotIn('Odor of Gas',detect.get_nature(t,'fdny'))
            self.assertFalse(fdny_audio_gate.generic_nature_invariant(p+'zero odor, gas in the area','Phone Alarm'))
    def test_no_global_replacement(self):
        self.assertNotIn('Odor of Gas',detect.get_nature('order of gas equipment','fdny'))
        self.assertNotIn('Odor of Gas',detect.get_nature('Box 934 order of gas in basement. Box 3282 100 Other Street','fdny'))
    def test_other_feed_not_rewritten(self):
        self.assertNotIn('Odor of Gas',detect.get_nature('Box 934 order of gas in basement','hatzolah'))
