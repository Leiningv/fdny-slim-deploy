import unittest
import detect
class JumperDown(unittest.TestCase):
    def test_explicit_police_request(self):
        t='Any units in Far Rockaway? Neilson and Carnegie PD requesting jumper down.'
        self.assertEqual(detect.get_nature(t,'hatzolah'),'Pd Requesting Jumper Down')
    def test_no_injury_inference(self):
        h=detect.analyze('Any units in Far Rockaway? Neilson and Carnegie PD requesting jumper down.','zello-hatzalah')
        self.assertEqual(h['nature'],'Pd Requesting Jumper Down')
        self.assertNotIn('trauma',h['nature'].lower())
    def test_negated_and_training(self):
        for prefix in ['no ','not ','negative ','training ','drill ','test ']:
            self.assertFalse(detect.get_nature(prefix+'PD requesting jumper down','hatzolah'))
    def test_no_bare_unit_or_new_diagnosis(self):
        for t in ['PD requesting a unit','jumper unit down','jumped down','jumper down']:
            self.assertFalse(detect.get_nature(t,'hatzolah'))
    def test_other_feeds_unchanged(self):
        self.assertFalse(detect.get_nature('PD requesting jumper down','sullivan'))

    def test_police_request_they_have_variant(self):
        for phrase in ['PD requesting they have a jumper down', 'pd REQUESTING they HAVE a JUMPER down']:
            self.assertEqual(detect.get_nature(phrase,'hatzolah'),'Pd Requesting Jumper Down')
    def test_they_have_variant_negative_training(self):
        for prefix in ['no ', 'not ', 'negative ', 'training ', 'drill ', 'test ']:
            self.assertFalse(detect.get_nature(prefix+'PD requesting they have a jumper down','hatzolah'))
    def test_they_have_variant_no_generalization(self):
        for phrase in ['they have a jumper down', 'PD requesting they have a jumper unit down', 'PD requesting they have a unit down']:
            self.assertFalse(detect.get_nature(phrase,'hatzolah'))
        self.assertFalse(detect.get_nature('PD requesting they have a jumper down','sullivan'))
