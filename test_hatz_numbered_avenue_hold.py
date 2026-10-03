import unittest
from unittest.mock import AsyncMock, Mock, patch
import main

SRC = "2nd Avenue in Queens for 83rd Avenue off 139th Street for an elderly difficulty breathing."

class HatzNumberedAvenueHold(unittest.IsolatedAsyncioTestCase):
    async def test_numbered_avenue_only_is_held(self):
        for addr in ["2 Avenue, Queens, NY", "2nd Avenue, Queens, NY"]:
            h = {"nature": "Difficulty Breathing", "address": addr, "dispatch_source_text": SRC, "excerpt": SRC}
            with patch.object(main.alert_waha, "send_text", new_callable=AsyncMock) as send:
                self.assertEqual(await main.verify_and_send("zello-hatzalah", h, Mock()), "suppressed")
            self.assertIn("numbered avenue only", h["hold_reason"])
            send.assert_not_awaited()

    async def test_other_cases_not_caught_by_guard(self):
        cases = [
            ("zello-hatzalah", {"address": "2 Avenue, Queens, NY", "cross": "83rd Avenue", "dispatch_source_text": SRC}),
            ("zello-hatzalah", {"address": "120 2nd Avenue, Queens, NY", "dispatch_source_text": SRC}),
            ("zello-hatzalah", {"address": "2 Avenue, Queens, NY", "dispatch_source_text": "2nd Avenue Queens elderly"}),
            ("fdny", {"address": "2 Avenue, Queens, NY", "dispatch_source_text": SRC}),
        ]
        for p, h in cases:
            h = dict(h, nature="Difficulty Breathing", excerpt=SRC)
            try:
                await main.verify_and_send(p, h, Mock())
            except Exception:
                pass
            self.assertNotIn("numbered avenue only", h.get("hold_reason", ""))

if __name__ == "__main__":
    unittest.main()
