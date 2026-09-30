import tempfile,unittest
import incident_updates as u

class UpdateShadow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=self.tmp.name
        self.h={'box_heard':'3047','address':'1878 New York Avenue, Brooklyn, NY','outbound_message_id':'original-test'}
        u.register(self.d,self.h,{'id':'initial','ts':1000})
    def check(self,text,ts=1100):return u.proposal(self.d,{'id':'update','ts':ts},text,now=ts)
    def test_live_escalation_proposal_not_send(self):
        r=self.check('Battalion 41 to Brooklyn,10-75 Box 3047. Fire in the rear.')
        self.assertFalse(r['release']);self.assertIn('UPDATE - 10-75',r['would_post'])
        self.assertEqual(r['original_post_id'],'original-test')
    def test_repeat_dedup(self):
        t='Battalion 41 to Brooklyn,10-75 Box 3047.'
        self.check(t);self.assertEqual(self.check(t)['reason'],'repeated update fingerprint')
    def test_multiple_boxes_hold(self):self.assertNotIn('would_post',self.check('10-75 Box 3047 and Box 3413'))
    def test_no_anchor_hold(self):self.assertNotIn('would_post',self.check('Battalion 41,10-75 at that box'))
    def test_conflicting_house_hold(self):self.assertNotIn('would_post',self.check('10-75 Box 3047,1800 New York Avenue'))
    def test_negated_hold(self):self.assertNotIn('would_post',self.check('No 10-75 Box 3047'))
    def test_battalion_before_escalation_hold(self):self.assertNotIn('would_post',self.check('Battalion 41 Box 3047, two lines operating'))
    def test_subsequent_battalion_allowed_only_shadow(self):
        self.check('10-75 Box 3047')
        r=self.check('Battalion 41 to Brooklyn Box 3047, two lines operating',1200)
        self.assertFalse(r['release']);self.assertIn('two lines operating',r['would_post'])
    def test_expired_incident_hold(self):self.assertNotIn('would_post',self.check('10-75 Box 3047',9000))
    def test_original_post_untouched(self):
        self.check('10-75 Box 3047');self.assertEqual(next(iter(u.load(self.d).values()))['original_post_id'],'original-test')

    def test_allhands_is_not_spoken_1075(self):
        self.assertNotIn('would_post',self.check('All hands going to work, private dwelling Box 3047 Brooklyn'))
    def test_negated_indirect_hold(self):
        self.assertNotIn('would_post',self.check('We are not transmitting a 10-75 Box 3047'))
    def test_multi_incident_hold(self):
        self.assertNotIn('would_post',self.check('10-75 Box 3047, another job at 1800 New York Avenue'))
    def test_borough_conflict_hold(self):
        self.assertNotIn('would_post',self.check('10-75 Box 3047 in Queens'))
    def test_subsequent_missing_borough_hold(self):
        self.check('10-75 Box 3047')
        self.assertNotIn('would_post',self.check('Battalion 41 Box 3047, two lines operating',1200))
    def test_anchor_does_not_renew_indefinitely(self):
        self.check('10-75 Box 3047',8000)
        self.assertNotIn('would_post',self.check('Battalion 41 to Brooklyn Box 3047, two lines operating',8500))
