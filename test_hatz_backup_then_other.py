import unittest
import audio_review
import detect

P = "zello-hatzalah"
# Real clip 10/3 1:07 PM EDT: sent as "Unconscious, 88th Drive, Queens".
BAD = ("Any backup units for 80th Drive and Surrey Place? Q308 Q64 179 05 80th Drive Q64 Q7 rolling. "
       "Q4 Q7 and a unit for 2904. West 145 83 to 904 Q83 904 Any units in the W for 160 Wilson for a child unconscious?")
# Real clips that were sent correctly and must not be caught.
OK = [
    "Any units for 17 26 48th Street for a patient choking? 238 Any units for 17 26 48th Street for an active choking? 238 238 17 26 48th Street in a private 238 A backup unit 17 and 48 and units for a bus. B25",
    "Any Queens units in Forest Hills, 62nd Drive and 108, patient not feeling well.",
    "17905 80th Drive third party caller patient choking private house",
    "Any backup units for 80th Drive? Any units for 17905 80th Drive for a patient choking?",
    "Any backup units for 160 Wilson Street for a child unconscious?",
    "Backup units for 80th Drive and Surrey Place. Units for 80 Drive for a choking.",
    "Any units available to start 9 for Harold and Fields? 529 Harold, that's Faris to Fields.",
]

class BackupThenOther(unittest.TestCase):
    def test_bad_clip_is_mixed(self):
        self.assertTrue(detect.hatzalah_backup_then_other_request(BAD, P))
        self.assertTrue(audio_review.mixed(BAD, P))

    def test_ordinary_calls_not_caught(self):
        for t in OK:
            self.assertFalse(detect.hatzalah_backup_then_other_request(t, P), t)

    def test_other_profiles_not_caught(self):
        for p in ("zello-sullivan", "fdny"):
            self.assertFalse(detect.hatzalah_backup_then_other_request(BAD, p))

    def test_flow_holds_instead_of_posting(self):
        import asyncio
        from unittest.mock import AsyncMock, Mock, patch
        import main
        hit = {"nature": "Unconscious", "address": "80th Drive, Queens, NY",
               "dispatch_source_text": BAD, "excerpt": BAD}
        with patch.object(main.alert_waha, "send_text", new_callable=AsyncMock) as send:
            out, h = asyncio.run(main.verify_zello_with_second_listen(P, hit, Mock(), "x.wav", fresh_ts=0))
        self.assertEqual(out, "suppressed")
        self.assertIn("mixed dispatch addresses", h["hold_reason"])
        send.assert_not_awaited()

if __name__ == "__main__":
    unittest.main()
