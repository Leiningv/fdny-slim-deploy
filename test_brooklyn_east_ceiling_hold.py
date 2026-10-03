import unittest
from unittest.mock import AsyncMock, Mock, patch
import main

class EastCeiling(unittest.IsolatedAsyncioTestCase):
    async def _run(self, profile, addr):
        h = {"nature": "Fumes", "address": addr, "excerpt": "x"}
        with patch.object(main.alert_waha, "send_text", new_callable=AsyncMock) as send:
            try:
                out = await main.verify_and_send(profile, h, Mock())
            except Exception:
                out = None
        return out, h, send

    async def test_above_108_held(self):
        for a in ["East 152 Street, Brooklyn, NY", "123 East 152nd Street, Brooklyn, NY", "East 110 Street, Brooklyn, NY"]:
            out, h, send = await self._run("fdny", a)
            self.assertEqual(out, "suppressed")
            self.assertIn("above 108", h["hold_reason"])
            send.assert_not_awaited()

    async def test_real_brooklyn_blocks_not_caught(self):
        for p, a in [("fdny", "East 108 Street, Brooklyn, NY"), ("fdny", "1001 East 108th Street, Brooklyn, NY"),
                     ("fdny", "East 29 Street, Brooklyn, NY"), ("fdny", "East 152 Street, Bronx, NY"),
                     ("zello-hatzalah", "East 152 Street, Brooklyn, NY")]:
            out, h, send = await self._run(p, a)
            self.assertNotIn("above 108", h.get("hold_reason", ""))

if __name__ == "__main__":
    unittest.main()
