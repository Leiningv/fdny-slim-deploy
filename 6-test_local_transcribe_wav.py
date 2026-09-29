"""Local ASR fallback must not use the incompatible PyAV path decoder."""
import io
import unittest
import wave
from unittest.mock import patch
import numpy as np
import transcribe


class LocalWavTests(unittest.TestCase):
    def test_pcm_wav_decodes_to_float_samples_without_pyav(self):
        import tempfile
        from pathlib import Path
        class Model:
            def transcribe(self, samples, **kwargs):
                self.samples = samples
                return iter([type("Seg", (), {"text": "assault"})()]), None
        model = Model()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(np.array([0, -32768, 16384], dtype="<i2").tobytes())
            with patch.object(transcribe, "get_model", return_value=model):
                self.assertEqual(transcribe._local_transcribe(str(path)), "assault")
            np.testing.assert_allclose(model.samples, [0, -1, 0.5])

    def test_rejects_wrong_audio_format(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wrong.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\0\0" * 100)
            with patch.object(transcribe, "get_model", return_value=object()):
                self.assertEqual(transcribe._local_transcribe(str(path)), "")
