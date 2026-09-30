import unittest
import detect
class NearSyncope(unittest.TestCase):
    def test_spoken_qualifier(self):
        self.assertEqual(detect.get_nature('Female near syncope,75HerschelDrive','sullivan'),'Near Syncope')
    def test_unqualified_stays(self):
        self.assertEqual(detect.get_nature('Female syncope,75HerschelDrive','sullivan'),'Syncope')
    def test_no_invented_near(self):
        self.assertEqual(detect.get_nature('Near75HerschelDrive,female fainting','sullivan'),'Fainting')
