import unittest
from unittest.mock import AsyncMock, Mock, patch
import detect, main

class PsychSituation(unittest.TestCase):
    def test_explicit_spoken_forms_kept(self):
        for text,nature in [('Any units in Valley Stream for Laurel Hill Drive and Rosedale Road for a EDP situation?','Edp Situation'),
                            ('Any RL units for Valley Stream for a psych situation?','Psych Situation')]:
            self.assertEqual(detect.get_nature(text,'hatzolah'),nature)
    def test_repeat_keeps_first_spoken_phrase(self):
        self.assertEqual(detect.get_nature('Any units for Laurel Hill Drive and Rosedale Road for a EDP situation? Any RL units for a psych situation?','hatzolah'),'Edp Situation')
    def test_bare_labels_and_negated_training_not_promoted(self):
        for text in ['EDP units available','psych training at Laurel Hill Drive','No EDP situation at Laurel Hill Drive','training psych situation at Laurel Hill Drive']:
            self.assertFalse(detect.get_nature(text,'hatzolah'))
    def test_other_feeds_unchanged(self):
        self.assertFalse(detect.get_nature('EDP situation at Laurel Hill Drive','sullivan'))

class LocationHold(unittest.IsolatedAsyncioTestCase):
    async def test_complaint_does_not_exempt_map(self):
        h=detect.analyze('Any units in Valley Stream for Laurel Hill Drive and Rosedale Road for a EDP situation?','zello-hatzalah')
        self.assertEqual(h['nature'],'Edp Situation')
        with (patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,False,'',None,None,'')),
              patch.object(main,'_intersection_point',new_callable=AsyncMock,return_value=(None,None)),
              patch.object(main.control,'muted_feeds',return_value=set()),
              patch.object(main,'_load_recent',return_value=[]),
              patch.object(main.alert_waha,'send_text',new_callable=AsyncMock) as send,
              patch.object(main,'ops_log')):
            self.assertEqual(await main.verify_and_send('zello-hatzalah',h,Mock()),'suppressed')
        send.assert_not_awaited()
