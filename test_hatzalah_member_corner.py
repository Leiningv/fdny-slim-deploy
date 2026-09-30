import unittest
import detect

class MemberCorner(unittest.TestCase):
    def test_eastern_dispatch_corner_beats_member_numbers(self):
        text=('Any units in Crown Heights, Eastern Parkway and Albany, full trauma. '
              'CH-51 Eastern Parkway, Albany to Kingston, 51. '
              'CH-65 Eastern Parkway, Albany to Kingston, 65.')
        h=detect.analyze(text,'zello-hatzalah')
        self.assertEqual(h['address'],'Eastern Parkway, Brooklyn, NY')
        self.assertEqual(h['direct_cross_candidate'],'Albany')
        self.assertEqual(h['nature'],'Full Trauma')
    def test_asr_bare_member_readout_cannot_replace_earlier_corner(self):
        text=('Crown Heights, Eastern Parkway and Albany, full trauma. '
              '51 Eastern Parkway, Albany to Kingston, 51. '
              '65 Eastern Parkway, Albany to Kingston, 65.')
        h=detect.analyze(text,'zello-hatzalah')
        self.assertEqual(h['address'],'Eastern Parkway, Brooklyn, NY')
        self.assertEqual(h['direct_cross_candidate'],'Albany')
    def test_explicit_members_cannot_create_numbered_house(self):
        for unit in ['CH-51','K48','PH-906']:
            h=detect.analyze('Any units available, '+unit+' Eastern Parkway, full trauma','zello-hatzalah')
            self.assertTrue(h is None or not h['address'].split(',')[0][0].isdigit())
    def test_true_numbered_house_stays_available(self):
        h=detect.analyze('Any units to 3288 Bedford Avenue, K to L, unresponsive','zello-hatzalah')
        self.assertEqual(h['address'],'3288 Bedford Avenue, Brooklyn, NY')
