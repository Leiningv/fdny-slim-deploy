import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import main


class HeldArchive(unittest.IsolatedAsyncioTestCase):
    async def test_zero_byte_archive_is_not_reported_as_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (patch.object(main, 'ARCHIVE_DIR', Path(tmp)),
                  patch.object(main, '_ensure_ogg', return_value='clip.ogg'),
                  patch.object(main, '_uguu_upload', new_callable=AsyncMock) as upload):
                (Path(tmp) / 'clip.ogg').touch()
                self.assertEqual(await main._held_recording('clip.wav'), '')
                upload.assert_not_awaited()

    async def test_success_response_with_empty_download_is_rejected(self):
        class Response:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def read(self): return b''
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            def get(self, *_args, **_kwargs): return Response()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'clip.ogg').write_bytes(b'OggS' + b'1' * 200)
            with (patch.object(main, 'ARCHIVE_DIR', Path(tmp)),
                  patch.object(main, '_ensure_ogg', return_value='clip.ogg'),
                  patch.object(main, '_uguu_upload', new_callable=AsyncMock,
                               return_value='https://n.uguu.se/empty.ogg'),
                  patch.object(main.aiohttp, 'ClientSession', return_value=Session())):
                self.assertEqual(await main._held_recording('clip.wav'), '')
