"""Transcription: AssemblyAI cloud primary, local faster-whisper fallback.

AssemblyAI (universal-3-pro, keyterm-boosted with dispatch geography) massively
outperforms local whisper on scratchy radio audio. Free credit, no card; only
speech segments are sent (RMS gate) so credit burn stays low. If the API key is
unset, the API errors, or it returns empty even after the universal-2 retry, we
fall back to local whisper so the monitor keeps working offline.

Local model from WHISPER_MODEL env (default "tiny.en"). CPU int8, beam 1, VAD on.
The cheap RMS energy gate skips silent segments before they reach any engine -
dispatch feeds are squelched quiet most of the time.
"""
from __future__ import annotations

import logging
import os
import time
import wave
from pathlib import Path

_model = None
RMS_MIN = int(os.environ.get("RMS_MIN", "350"))
AAI_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "").strip()
AAI_TIMEOUT = float(os.environ.get("ASSEMBLYAI_TIMEOUT", "60"))

# Dispatch geography for keyword boosting - the user's calibration loop lives here.
KEYTERMS = {
    "zello-sullivan": ["Windsor Hills Estates", "Petaluga Drive", "Petaluga", "Monticello",
                       "Old Liberty Road", "Sullivan County", "Wurtsboro", "Liberty",
                       "Woodridge", "South Fallsburg", "Kiamesha", "Hatzalah"],
    "zello-hatzalah": ["Woodmere", "Five Towns", "Central Avenue", "Hatzalah", "Inwood",
                       "Cedarhurst", "Lawrence", "Hewlett", "Far Rockaway", "Brooklyn"],
    "fdny": ["FDNY", "Brooklyn", "Manhattan", "Queens", "Bronx", "Staten Island"],
}
DEFAULT_KEYTERMS = ["Hatzalah", "Monticello", "Woodmere", "Brooklyn"]


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # lazy: keeps import light
        name = os.environ.get("WHISPER_MODEL", "tiny.en")
        logging.info("loading whisper model %s (first run downloads it)", name)
        _model = WhisperModel(name, device="cpu", compute_type="int8")
    return _model


def rms(wav_path: Path | str) -> int:
    """RMS energy of a 16kHz mono PCM WAV; 0 on unreadable files."""
    try:
        with wave.open(str(wav_path), "rb") as w:
            frames = w.readframes(w.getnframes())
        import audioop  # stdlib on py<=3.12
        return audioop.rms(frames, 2)
    except ModuleNotFoundError:
        import array, math
        a = array.array("h")
        a.frombytes(frames[: len(frames) - (len(frames) % 2)])
        if not a:
            return 0
        return int(math.sqrt(sum(x * x for x in a) / len(a)))
    except Exception:  # noqa: BLE001
        return 0


def _aai_transcribe(wav_path: str, keyterms: list[str], models: list[str]) -> str:
    """One AssemblyAI job: upload, submit, poll. Returns text or raises."""
    import urllib.request, json

    def req(url: str, data=None, headers=None, method=None):
        r = urllib.request.Request(url, data=data, method=method,
                                   headers={"Authorization": AAI_KEY, **(headers or {})})
        with urllib.request.urlopen(r, timeout=AAI_TIMEOUT) as resp:
            return resp.read()

    with open(wav_path, "rb") as f:
        up = json.loads(req("https://api.assemblyai.com/v2/upload", data=f.read()))
    body = {"audio_url": up["upload_url"], "speech_models": models}
    if keyterms:
        body["keyterms_prompt"] = keyterms
    job = json.loads(req("https://api.assemblyai.com/v2/transcript",
                         data=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"}))
    tid = job["id"]
    deadline = time.time() + AAI_TIMEOUT
    while time.time() < deadline:
        st = json.loads(req(f"https://api.assemblyai.com/v2/transcript/{tid}"))
        if st["status"] == "completed":
            return (st.get("text") or "").strip()
        if st["status"] == "error":
            raise RuntimeError(f"assemblyai job error: {st.get('error')}")
        time.sleep(2)
    raise TimeoutError("assemblyai poll timeout")


def _local_transcribe(wav_path: str) -> str:
    try:
        model = get_model()
    except Exception as e:  # noqa: BLE001
        logging.error("whisper model failed to load: %s", e)
        return ""
    try:
        segments, _info = model.transcribe(
            wav_path, beam_size=1, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500})
        return " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:  # noqa: BLE001
        logging.warning("local transcription failed: %s", e)
        return ""


def transcribe(wav_path: Path | str, profile: str | None = None) -> str:
    """Transcribe a 16kHz mono WAV segment. Returns plain text ("" when silent)."""
    level = rms(wav_path)
    if level < RMS_MIN:
        return ""
    wav_path = str(wav_path)
    if profile is None:  # derive from "<profile>-NNN.wav" / "pair-<profile>.wav"
        base = Path(wav_path).stem
        profile = base.removeprefix("pair-").rsplit("-", 1)[0]
    keyterms = KEYTERMS.get(profile, DEFAULT_KEYTERMS)
    if AAI_KEY:
        try:
            text = _aai_transcribe(wav_path, keyterms, ["universal-3-pro", "universal-2"])
            if text:
                return text
            # u3-pro sometimes blanks on short scratchy clips; u2 handles those.
            text = _aai_transcribe(wav_path, keyterms, ["universal-2"])
            if text:
                return text
            logging.warning("[%s] assemblyai returned empty twice - local fallback", profile)
        except Exception as e:  # noqa: BLE001
            logging.warning("[%s] assemblyai failed (%s) - local fallback", profile, e)
    return _local_transcribe(wav_path)
