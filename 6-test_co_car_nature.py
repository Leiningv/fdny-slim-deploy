import time,unittest
from unittest.mock import AsyncMock,Mock,patch
import detect,main
BASE='Phone Alarm Box 1016,1556 Carroll Street,Troy Avenue to Schenectady Avenue for a '
class Nature(unittest.TestCase):
 def test_car_fire_not_classifier_co_bug(self):
  self.assertEqual(detect.analyze(BASE+'car fire.','fdny')['nature'],'Car Fire')
 def test_real_co_not_rewritten(self):
  self.assertEqual(detect.analyze(BASE+'CO alarm.','fdny')['nature'],'Co Alarm')
 def test_both_phrases_car_precedence(self):
  self.assertEqual(detect.analyze(BASE+'CO alarm. Repeating car fire.','fdny')['nature'],'Car Fire')
