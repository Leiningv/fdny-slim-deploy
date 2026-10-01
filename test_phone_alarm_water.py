import unittest
from unittest.mock import patch,AsyncMock,Mock
import detect,main
BELT='Brooklyn phone number box 8230. Yeah, 65th Street and the Belt Parkway for a person in the water by the 8th Avenue overpass. Brooklyn phone number box 8230. The address is going to be at 65th Street and the Belt Parkway for a person in the water by the 8th Avenue overpass. 290 your message.'
MOORE="35 to Brooklyn. 35. box 703 we're coming from that last box, we're delayed. box 703 the address 260 Moore Street. Street, White Street. Smoke in apartment 208. Brooklyn box 703 the address 260"
BUSH='222 Temple, Interbox 742, the address 757 Bushwick Avenue, between Cedar Street, Dodworth Street, smoking apartment three boy. Engine 277. Remaining service.'
class Nature(unittest.TestCase):
 def test_belt(self):
  h=detect.analyze(BELT,'fdny');self.assertEqual(h['nature'],'Person in the Water');self.assertEqual(h['address'],'Belt Pkwy, Brooklyn, NY')
 def test_moore(self):self.assertEqual(detect.analyze(MOORE,'fdny')['nature'],'Smoke, Apartment 208')
 def test_bush(self):self.assertEqual(detect.analyze(BUSH,'fdny')['nature'],'Smoke in Apartment, Apartment 3B')
 def test_phone_alarm_never_nature(self):
  for t in ('Brooklyn phone alarm box 8230 the address is Belt Parkway 65th Street overpass.','Phone alarm box 742 757 Bushwick Avenue apartment 3B'):
   h=detect.analyze(t,'fdny');self.assertNotRegex((h or {}).get('nature',''),r'(?i)phone alarm')
 def test_water_variants(self):
  for t,n in (('Box 100 Shore Parkway for a water rescue','Water Rescue'),('Box 100 Shore Parkway for an ice rescue','Ice Rescue'),('Box 100 Shore Parkway person in the water','Person in the Water'),('Box 100 Shore Parkway for a boat in distress','Boat in Distress')):
   self.assertEqual(detect.get_nature(t,'fdny'),n)
 def test_negated_water(self):self.assertEqual(detect.get_nature('Box 100 Belt Parkway no person in the water','fdny'),'')
class Post(unittest.IsolatedAsyncioTestCase):
 async def _run(self,text):
  h=detect.analyze(text,'fdny')
  with (patch.object(main,'_box_lookup',new_callable=AsyncMock,return_value=[]),patch.object(main,'_load_box_cache',return_value={}),patch.object(main,'_map_street_names',new_callable=AsyncMock,return_value=set()),patch.object(main,'_load_recent',return_value=[]),patch.object(main,'ops_log'),patch.object(main.control,'muted_feeds',return_value=set()),patch.object(main,'geocode_verify',new_callable=AsyncMock,return_value=(False,'',None,None,None,'')),patch.object(main.alert_waha,'send_text',new_callable=AsyncMock,return_value=True) as send,patch.object(main.alert_waha,'send_voice',new_callable=AsyncMock,return_value=True)):
   r=await main.verify_and_send('fdny',h,Mock(),prepare_only=False)
  return r,send
 async def test_unverified_belt_posts_street_and_nature(self):
  r,send=await self._run(BELT)
  self.assertEqual(r,'sent');body=send.await_args.args[0];self.assertIn('PERSON IN THE WATER',body.upper());self.assertIn('Belt Pkwy',body);self.assertIn('not confirmed',body);self.assertNotIn('PHONE ALARM',body.upper())
 async def test_no_nature_still_held(self):
  r,send=await self._run('Brooklyn phone alarm box 8230 the address is Belt Parkway 65th Street overpass.')
  self.assertEqual(r,'suppressed');send.assert_not_awaited()
if __name__=='__main__':unittest.main()
