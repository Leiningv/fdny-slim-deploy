"""One marked test post, never a general manual dispatch API."""
import re
import unittest
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
import status


class TestSend(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stats = status.Stats()
        self.stats.waha_status = 'WORKING'
        self.client = TestClient(TestServer(status.make_app(self.stats)))
        await self.client.start_server()
        self.path = '/c/private-test-token/'

    async def asyncTearDown(self):
        await self.client.close()

    async def form(self):
        with patch.dict(status.os.environ, {'CONTROL_TOKEN': 'private-test-token'}):
            r = await self.client.get(self.path)
            self.assertEqual(r.status, 200)
            page = await r.text()
        self.assertIn('ONE-TIME TEST ALERT', page)
        nonce = re.search(r'name="nonce" value="([^"]+)"', page).group(1)
        return nonce

    async def post(self, nonce, text='TEST ALERT', origin=True, path=None):
        path = path or (self.path + 'test-send')
        hdr = {'Origin': str(self.client.make_url(path).origin())} if origin else {}
        with patch.dict(status.os.environ, {'CONTROL_TOKEN': 'private-test-token'}):
            return await self.client.post(path, data={'nonce': nonce, 'text': text}, headers=hdr)

    async def test_exact_alert_one_time_to_configured_chat(self):
        nonce = await self.form()
        with (patch('alert_waha.configured', return_value=True),
              patch('alert_waha._chat', return_value='alert@g.us'),
              patch('alert_waha.send_text', new_callable=AsyncMock, return_value=True) as send):
            r = await self.post(nonce)
            self.assertEqual(r.status, 200, await r.text())
            self.assertIn('does not prove receipt', await r.text())
            send.assert_awaited_once_with('TEST ALERT', chat_id='alert@g.us')
            again = await self.post(nonce)
            self.assertEqual(again.status, 409)
            send.assert_awaited_once()

    async def test_rejects_bad_token_origin_nonce_and_incident_text(self):
        nonce = await self.form()
        with (patch('alert_waha.configured', return_value=True),
              patch('alert_waha.send_text', new_callable=AsyncMock) as send):
            self.assertEqual((await self.post(nonce, path='/c/wrong/test-send')).status, 404)
            self.assertEqual((await self.post(nonce, origin=False)).status, 403)
            self.assertEqual((await self.post('wrong')).status, 403)
            self.assertEqual((await self.post(nonce, text='FIRE AT 123 MAIN')).status, 400)
            send.assert_not_awaited()

    async def test_render_tls_termination_accepts_public_https_origin(self):
        nonce = await self.form()
        with (patch.dict(status.os.environ, {'CONTROL_TOKEN': 'private-test-token'}),
              patch('alert_waha.configured', return_value=True),
              patch('alert_waha._chat', return_value='alert@g.us'),
              patch('alert_waha.send_text', new_callable=AsyncMock, return_value=True) as send):
            r = await self.client.post(self.path + 'test-send',
                data={'nonce': nonce, 'text': 'TEST ALERT'},
                headers={'Origin': 'https://fdny-slim.onrender.com', 'Host': 'fdny-slim.onrender.com'})
            self.assertEqual(r.status, 200, await r.text())
            send.assert_awaited_once()

    async def test_failed_send_does_not_retry_automatically(self):
        nonce = await self.form()
        with (patch('alert_waha.configured', return_value=True),
              patch('alert_waha._chat', return_value='alert@g.us'),
              patch('alert_waha.send_text', new_callable=AsyncMock, return_value=False) as send):
            self.assertEqual((await self.post(nonce)).status, 502)
            self.assertEqual((await self.post(nonce)).status, 409)
            send.assert_awaited_once()
