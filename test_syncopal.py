import unittest
import detect

T = ("Sergeant dispatch to Empress County 5262 a first response, Tana Thompson 163 Wildcat "
     "Road for a 74-year-old female, syncopal episode, and ALS response.")


class Syncopal(unittest.TestCase):
    def test_syncopal_episode_is_a_nature(self):
        h = detect.analyze(T, 'sullivan')
        self.assertTrue(h['nature'])
        self.assertIn('Wildcat Road', h['address'])

    def test_plain_syncope_unchanged(self):
        self.assertTrue(detect.analyze('163 Wildcat Road for a female, syncope', 'sullivan')['nature'])


if __name__ == '__main__':
    unittest.main()
