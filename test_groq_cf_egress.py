import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import transcribe
class Egress(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.wav=Path(self.tmp.name)/'clip.wav';self.wav.write_bytes(b'RIFF'+bytes(40))
 def tearDown(self):self.tmp.cleanup()
 def call(self,body):
  with patch.object(transcribe,'GROQ_EGRESS_URL','https://fdny-groq-egress-0930.yeshivehboy.workers.dev/transcribe'),patch.object(transcribe,'GROQ_KEY','test-only-key'),patch('urllib.request.OpenerDirector.open',return_value=io.BytesIO(body)) as req:
   text=transcribe._groq_transcribe(str(self.wav));r=req.call_args.args[0]
   self.assertEqual(r.full_url,transcribe.GROQ_EGRESS_URL);self.assertEqual(r.data,self.wav.read_bytes());self.assertEqual(r.get_header('Content-type'),'audio/wav')
   return text
 def test_text_only(self):self.assertEqual(self.call(b'{"text":"hello"}'),'hello')
 def test_no_text_rejected(self):
  with self.assertRaises(ValueError):self.call(b'{"text":null}')
 def test_oversized_response(self):
  with self.assertRaises(ValueError):self.call(b'x'*65537)
 def test_no_local_fallback_on_failure(self):
  with patch.object(transcribe,'GROQ_ENABLED',True),patch.object(transcribe,'GROQ_KEY','test-only-key'),patch.object(transcribe,'_groq_transcribe',side_effect=ValueError('bad')),patch.object(transcribe,'_local_transcribe') as local:
   self.assertEqual(transcribe.second_listen(self.wav,'zello-hatzalah'),'');local.assert_not_called()
 def test_other_target_rejected(self):
  with patch.object(transcribe,'GROQ_EGRESS_URL','https://example.com/transcribe'),self.assertRaises(ValueError):transcribe._groq_transcribe(str(self.wav))

 def test_redirect_rejected(self):
  with patch.object(transcribe,'GROQ_EGRESS_URL','https://fdny-groq-egress-0930.yeshivehboy.workers.dev/transcribe'),patch('urllib.request.build_opener') as build:
   build.return_value.open.return_value=io.BytesIO(b'{"text":"ok"}')
   self.assertEqual(transcribe._groq_transcribe(str(self.wav)),'ok')
   handler=build.call_args.args[0]()
   with self.assertRaises(ValueError):
    handler.redirect_request(None,None,302,'redirect',{},'https://other.example/')
 def test_nonstandard_port_rejected(self):
  with patch.object(transcribe,'GROQ_EGRESS_URL','https://fdny-groq-egress-0930.yeshivehboy.workers.dev:444/transcribe'),self.assertRaises(ValueError):transcribe._groq_transcribe(str(self.wav))
