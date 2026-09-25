"""Local transcription with faster-whisper. Free, no API, no cloud.

Model from WHISPER_MODEL env (default "tiny.en"; "base.en" is more accurate).
CPU int8, beam 1, VAD on. A cheap RMS energy gate skips silent segments before
they reach whisper - dispatch feeds are squelched quiet most of the time, and
on a free-tier shared CPU this is what keeps two feeds sustainable 24/7.
"""
from __future__ import annotations

import audioop
import logging
import os
import wave
from pathlib import Path

_model = None
RMS_MIN = int(os.environ.get("RMS_MIN", "350"))


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
        return audioop.rms(frames, 2)
    except Exception:  # noqa: BLE001
        return 0


def transcribe(wav_path: Path | str) -> str:
    """Transcribe a 16kHz mono WAV segment. Returns plain text ("" when silent)."""
    level = rms(wav_path)
    if level < RMS_MIN:
        return ""
    try:
        model = get_model()
    except Exception as e:  # noqa: BLE001
        logging.error("whisper model failed to load: %s", e)
        return ""
    try:
        segments, _info = model.transcribe(
            str(wav_path),
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        return " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:  # noqa: BLE001
        logging.warning("transcription failed: %s", e)
        return ""
