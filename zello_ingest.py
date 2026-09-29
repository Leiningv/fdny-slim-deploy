"""Zello Channel API ingest - same segment-ring contract as ingest.py.

One supervisor per channel. Each keeps a WebSocket to wss://zello.io/ws,
logs on with a self-minted RS256 JWT (Issuer + Private Key from the Zello
developer console) plus the listener account's username/password, and
listens in listen_only mode. Incoming Opus frames (9-byte stream header
stripped) are muxed into Ogg pages on the fly and piped through ffmpeg to
16 kHz mono PCM, which is sliced into the same 20s WAV segment ring the
Broadcastify supervisors write - so the existing consumer/transcribe/detect
machinery treats Zello channels as just two more feeds.

Zello only sends audio while someone transmits, so segments simply contain
no dead air. A segment is finalized when full (20s) or when audio has been
quiet for FLUSH_SEC, whichever comes first.

Env:
  ZELLO_USER / ZELLO_PASS        listener account credentials (channel 1)
  ZELLO_USER_2 / ZELLO_PASS_2    dedicated account for zello-sullivan (optional)
  ZELLO_ISSUER / ZELLO_PRIVATE_KEY  dev-console key pair (PEM; \n escapes ok)
  ZELLO_CH_HATZOLAH / ZELLO_CH_SULLIVAN  channel name overrides (optional)
"""
from __future__ import annotations

import json
from collections import deque
import logging
import os
import struct
import re
import subprocess
import threading
import time
import wave
from pathlib import Path

WS_URL = "wss://zello.io/ws"
SEG_SEC = int(os.environ.get("SEG_SECONDS", "20"))
SEG_WRAP = int(os.environ.get("SEG_WRAP", "6"))
FLUSH_SEC = int(os.environ.get("ZELLO_FLUSH_SEC", "25"))
PCM_RATE = 16000
PCM_BYTES_PER_SEG = PCM_RATE * 2 * SEG_SEC  # s16le mono

# Trial grouping gap: bounded at 8s, pending live stream-boundary measurements.
# The supplied clips contain edited audio but not original stream event clocks.
GROUP_TRIAL_SEC = float(os.environ.get("ZELLO_GROUP_TRIAL_SEC", "8"))
PRE_ROLL_SEC = float(os.environ.get("ZELLO_PREROLL_SEC", "1.5"))
TAIL_SEC = float(os.environ.get("ZELLO_TAIL_SEC", "0.6"))
STREAM_MAX_SEC = int(os.environ.get("ZELLO_STREAM_MAX_SEC", "90"))

# Cross-consumer ownership ledger for live Zello audio. The legacy ring may
# transcribe only when no PTT stream owns the overlapping audio. Entries move
# from pending to owned after ASR succeeds, or failed when decode/ASR fails.
# A pending entry never times out into a parallel ring send; a stalled decoder
# is a held alert, not permission to race the same voice through two paths.
STREAM_OWNERS: dict[str, dict[str, dict]] = {}
_OWNER_LOCK = threading.RLock()


def stream_owner(profile: str, name: str, start: float, stop: float, state: str) -> None:
    with _OWNER_LOCK:
        STREAM_OWNERS.setdefault(profile, {})[name] = {"start":start,"stop":stop,"state":state}


def stream_owner_state(profile: str, segment_mtime: float) -> str | None:
    with _OWNER_LOCK:
        entries = STREAM_OWNERS.get(profile, {})
        now = time.time()
        for name, e in list(entries.items()):
            if e["state"] != "pending" and now - e["stop"] > 2 * 3600:
                entries.pop(name, None)
        matches = [e["state"] for e in entries.values()
                   if e["start"] - SEG_SEC - 5 <= segment_mtime <= e["stop"] + FLUSH_SEC + 5]
        if "pending" in matches: return "pending"
        if "owned" in matches: return "owned"
        return None


CHANNELS = {
    "zello-hatzalah": os.environ.get("ZELLO_CH_HATZOLAH", "TSL-ChevraHatzolah_10"),
    "zello-sullivan": os.environ.get("ZELLO_CH_SULLIVAN", "TSL-SullivanCounty_2003"),
}


def configured() -> bool:
    return all(os.environ.get(k) for k in
               ("ZELLO_USER", "ZELLO_PASS", "ZELLO_ISSUER", "ZELLO_PRIVATE_KEY"))


def mint_token() -> str:
    """RS256 JWT per the Zello Channel API auth guide (iss + 120s exp)."""
    import jwt  # PyJWT
    iss = os.environ["ZELLO_ISSUER"]
    key = os.environ["ZELLO_PRIVATE_KEY"].replace("\\n", "\n")
    return jwt.encode({"iss": iss, "exp": int(time.time()) + 120},
                      key, algorithm="RS256")


# --- minimal Ogg/Opus muxer (pages written incrementally to ffmpeg stdin) ---

def _ogg_crc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC_TABLE[((crc >> 24) & 0xFF) ^ b]
    return crc


def _build_crc_table() -> list[int]:
    table = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if (r & 0x80000000) else (r << 1) & 0xFFFFFFFF
        table.append(r)
    return table


_CRC_TABLE = _build_crc_table()


class OggMuxer:
    def __init__(self, serial: int = 0x5A656C6C, packet_ms: float = 60):
        self.serial = serial
        self.packet_ms = packet_ms
        self.seq = 0
        self.granule = 0

    def page(self, packets: list[bytes], bos: bool = False, eos: bool = False) -> bytes:
        segs = []
        for pkt in packets:
            full, rem = divmod(len(pkt), 255)
            segs.extend([255] * full + [rem])
        data = b"".join(packets)
        flags = (2 if bos else 0) | (4 if eos else 0)
        header = struct.pack("<4sBBqIII", b"OggS", 0, flags, self.granule,
                             self.serial, self.seq, 0)
        header += struct.pack("<B", len(segs)) + bytes(segs)
        crc = _ogg_crc(header + data)
        self.seq += 1
        return header[:22] + struct.pack("<I", crc) + header[26:] + data

    def headers(self) -> bytes:
        head = b"OpusHead" + struct.pack("<BBHIhB", 1, 1, 0, PCM_RATE, 0, 0)
        vendor = b"fdny-slim"
        tags = b"OpusTags" + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0)
        return self.page([head], bos=True) + self.page([tags])

    def audio(self, frames: list[bytes]) -> bytes:
        out = self.page(frames)
        self.granule += round(48 * self.packet_ms) * len(frames)  # Opus clock is 48 kHz
        return out


class SegmentWriter:
    """Slices a PCM byte stream into the shared 20s WAV ring."""

    def __init__(self, profile: str, seg_dir: Path):
        self.profile = profile
        self.seg_dir = seg_dir
        self.idx = 0
        self.wav: wave.Wave_write | None = None
        self.bytes_in = 0
        self.last_write = 0.0
        self.path: Path | None = None

    def _open(self) -> None:
        name = f"{self.profile}-{self.idx:03d}.wav"
        self.idx = (self.idx + 1) % SEG_WRAP
        self.path = self.seg_dir / name
        self.wav = wave.open(str(self.path), "wb")
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)
        self.wav.setframerate(PCM_RATE)
        self.bytes_in = 0
        self.last_write = time.time()

    def write(self, pcm: bytes) -> None:
        if self.wav is None:
            self._open()
        self.wav.writeframesraw(pcm)
        self.bytes_in += len(pcm)
        self.last_write = time.time()
        if self.bytes_in >= PCM_BYTES_PER_SEG:
            self.close()

    def close(self) -> None:
        if self.wav is not None:
            try:
                self.wav.close()
            except Exception:  # noqa: BLE001
                pass
            self.wav = None
            self.bytes_in = 0

    def maybe_flush(self) -> None:
        """Finalize a partial segment after FLUSH_SEC of quiet."""
        if (self.wav is not None and self.bytes_in > 3200
                and time.time() - self.last_write > FLUSH_SEC):
            self.close()


class StreamRecorder:
    """Separate Ogg files by Zello's 32-bit stream ID; legacy PCM is fallback.

    Packet buffering before a delayed start event provides up to PRE_ROLL_SEC,
    and after a stop event up to TAIL_SEC. The decoder never sees two senders
    spliced into one file. A bad/missing ID uses the old continuous recorder.
    """
    def __init__(self, profile: str, seg_dir: Path, ffmpeg: str, stats):
        self.profile, self.seg_dir, self.ffmpeg, self.stats = profile, seg_dir, ffmpeg, stats
        self.active = {}  # id -> {mux, file, start, last, packet_ms, tail_until}
        self.early = {}  # id -> deque[(wall time, opus payload)]
        self.seq = 0
        self.lock = threading.RLock()
        self.last_good = 0.0

    def start(self, msg: dict, now: float | None = None):
        now = now or time.time(); sid = msg.get("stream_id")
        if not isinstance(sid, int) or isinstance(sid, bool) or not 0 <= sid <= 0xffffffff or msg.get("codec") != "opus":
            return False
        with self.lock:
            if sid in self.active: self.finish(sid, "repeated start", now)
            self.seq += 1
            name = f"{self.profile}-ptt-{int(now*1000)}-{sid}-{self.seq}"
            path = self.seg_dir / (name + ".ogg.part")
            self.seg_dir.mkdir(parents=True, exist_ok=True)
            f = path.open("wb")
            dur = float(msg.get("packet_duration") or 20)
            if not 2.5 <= dur <= 60: dur = 20
            mux = OggMuxer(serial=(sid ^ self.seq) & 0xffffffff, packet_ms=dur)
            f.write(mux.headers())
            rec = {"mux": mux, "file": f, "path": path, "start": now,
                   "last": now, "packet_ms": dur, "tail_until": None, "count": 0}
            self.active[sid] = rec
            stream_owner(self.profile, name, now, now, "pending")
            for ts, data in self.early.pop(sid, ()):
                if now - ts <= PRE_ROLL_SEC: self.packet(sid, data, ts)
            self.stats.event(self.profile, f"PTT start id={sid} at={now:.3f}")
            return True

    def packet(self, sid: int, opus: bytes, now: float | None = None):
        now = now or time.time()
        with self.lock:
            rec = self.active.get(sid)
            if rec is None:
                q = self.early.setdefault(sid, deque())
                q.append((now, opus))
                while q and (now-q[0][0] > PRE_ROLL_SEC or len(q) > 100): q.popleft()
                return False
            if now - rec["start"] > STREAM_MAX_SEC:
                self.finish(sid, "max duration", now)
                return False
            rec["file"].write(rec["mux"].audio([opus]))
            rec["last"] = now; rec["count"] += 1
            stream_owner(self.profile, rec["path"].name.removesuffix(".ogg.part"), rec["start"], now, "pending")
            return True

    def stop(self, sid: int, now: float | None = None):
        now = now or time.time()
        with self.lock:
            rec = self.active.get(sid)
            if rec:
                rec["tail_until"] = now + TAIL_SEC
                self.stats.event(self.profile, f"PTT stop id={sid} at={now:.3f} duration={now-rec['start']:.2f}s")
                return True
            return False

    def tick(self, now: float | None = None):
        now = now or time.time()
        with self.lock:
            for sid, rec in list(self.active.items()):
                if rec["tail_until"] and now >= rec["tail_until"]:
                    self.finish(sid, "stop tail", now)
                elif now - rec["start"] > STREAM_MAX_SEC:
                    self.finish(sid, "timeout", now)
            for sid, q in list(self.early.items()):
                while q and now-q[0][0] > PRE_ROLL_SEC: q.popleft()
                if not q: self.early.pop(sid, None)

    def finish(self, sid: int, reason: str, now: float | None = None):
        now = now or time.time()
        with self.lock:
            rec = self.active.pop(sid, None)
            if not rec: return
            rec["file"].close()
            path = rec["path"]
            if rec["count"] == 0:
                stream_owner(self.profile, path.name.removesuffix(".ogg.part"), rec["start"], now, "failed")
                path.unlink(missing_ok=True); return
            wav = path.with_suffix("").with_suffix(".wav")
            stream_owner(self.profile, path.name.removesuffix(".ogg.part"), rec["start"], now, "pending")
            threading.Thread(target=self._convert, args=(path, wav, sid, reason, rec["start"], now), daemon=True).start()

    def _convert(self, path, wav, sid, reason, start, end):
        try:
            subprocess.run([self.ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "ogg", "-i", str(path),
                            "-ar", str(PCM_RATE), "-ac", "1", "-f", "wav", str(wav)+".part"],
                           check=True, timeout=15)
            os.replace(str(wav)+".part", wav)
            self.last_good = time.time()
            wav.with_suffix(".json").write_text(json.dumps({"stream_id":sid,"start":start,"stop":end,"reason":reason,"source":"zello-ptt"}))
            self.stats.event(self.profile, f"PTT finished id={sid} reason={reason} wav={wav.name}")
        except Exception as e:
            logging.warning("[%s] PTT decode failed id=%s: %s", self.profile, sid, e)
            stream_owner(self.profile, path.name.removesuffix(".ogg.part"), start, end, "failed")
            Path(str(wav)+".part").unlink(missing_ok=True)
        finally:
            path.unlink(missing_ok=True)

    def close(self):
        for sid in list(self.active): self.finish(sid, "reconnect")


def _pcm_reader(proc: subprocess.Popen, writer: SegmentWriter, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            chunk = proc.stdout.read(65536)
        except Exception:  # noqa: BLE001
            break
        if not chunk:
            break
        writer.write(chunk)


def _stderr_drain(proc: subprocess.Popen, profile: str) -> None:
    try:
        for line in iter(proc.stderr.readline, b""):
            if line:
                logging.warning("[%s] ffmpeg: %s", profile, line.decode(errors="replace").strip()[:200])
    except Exception:  # noqa: BLE001
        pass


def run_session(profile: str, channel: str, seg_dir: Path, stats) -> None:
    """One WS session: logon, stream audio through ffmpeg, write segments."""
    import websocket  # websocket-client
    from ingest import ffmpeg_bin

    token = mint_token()
    # zello-sullivan gets its own dedicated account when ZELLO_USER_2 is set:
    # Zello allows ONE active session per account, two channels need two accounts.
    sfx = "_2" if profile == "zello-sullivan" and os.environ.get("ZELLO_USER_2") else ""
    user = os.environ[f"ZELLO_USER{sfx}"].strip()
    pw = os.environ[f"ZELLO_PASS{sfx}"]
    logging.info("[%s] zello login as account%s", profile, sfx or "1")
    proc = subprocess.Popen(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
         "-f", "ogg", "-i", "pipe:0",
         "-ar", str(PCM_RATE), "-ac", "1", "-f", "s16le", "pipe:1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stop = threading.Event()
    writer = SegmentWriter(profile, seg_dir)
    recorder = StreamRecorder(profile, seg_dir, ffmpeg_bin(), stats)
    readers = [
        threading.Thread(target=_pcm_reader, args=(proc, writer, stop), daemon=True),
        threading.Thread(target=_stderr_drain, args=(proc, profile), daemon=True),
    ]
    for t in readers:
        t.start()
    mux = OggMuxer()
    pending: list[bytes] = []
    ws = None
    try:
        proc.stdin.write(mux.headers())
        proc.stdin.flush()
        ws = websocket.create_connection(WS_URL, timeout=30)
        ws.send(json.dumps({
            "command": "logon", "seq": 1, "auth_token": token,
            "username": user, "password": pw,
            "channels": [channel], "listen_only": True,
            "features": {"transcriptions": True}}))
        stats.mark_ffmpeg_start(profile)
        stats.event(profile, f"zello session up: {channel}")
        logging.info("[%s] zello session up on %s", profile, channel)
        while True:
            writer.maybe_flush()
            recorder.tick()
            try:
                ws.settimeout(1)
                frame = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if isinstance(frame, str):
                try:
                    msg = json.loads(frame)
                except Exception:  # noqa: BLE001
                    continue
                if msg.get("error"):
                    raise RuntimeError(f"zello logon/session error: {msg['error']}")
                cmd = msg.get("command")
                if cmd == "on_stream_start":
                    recorder.start(msg)
                    stats.event(profile, f"stream from {msg.get('from', '?')}")
                    logging.info("[%s] stream start from %s", profile, msg.get("from"))
                elif cmd == "on_stream_stop":
                    recorder.stop(msg.get("stream_id"))
                    writer.maybe_flush()
                elif cmd == "on_transcription":
                    text = msg.get("text") or ""
                    if text:
                        stats.event(profile, "zello server transcript: " + text[:240])
                        logging.info("[%s] zello transcription: %s", profile, text[:160])
                elif cmd == "on_channel_status":
                    logging.info("[%s] channel %s %s (%s users)", profile,
                                 msg.get("channel"), msg.get("status"), msg.get("users_online"))
            elif isinstance(frame, (bytes, bytearray)) and len(frame) > 9 and frame[0] == 1:
                sid = struct.unpack("!I", frame[1:5])[0]
                recorder.packet(sid, bytes(frame[9:]))
                pending.append(bytes(frame[9:]))
                if len(pending) >= 20:
                    proc.stdin.write(mux.audio(pending))
                    proc.stdin.flush()
                    pending = []
    finally:
        if pending:
            try:
                proc.stdin.write(mux.audio(pending))
                proc.stdin.flush()
            except Exception:  # noqa: BLE001
                pass
        stop.set()
        try:
            ws and ws.close()
        except Exception:  # noqa: BLE001
            pass
        writer.close()
        recorder.close()
        try:
            proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        stats.mark_ffmpeg_exit(profile)


# Zello allows ONE active session per account: two channels on one account
# kick each other. Until a second account exists, PASSIVE channels back off
# hard so the primary channel holds the account 24/7. Remove a profile from
# ZELLO_PASSIVE once it has its own credentials.
_DEFAULT_PASSIVE = "" if os.environ.get("ZELLO_USER_2") else "zello-sullivan"
PASSIVE = {p.strip() for p in os.environ.get("ZELLO_PASSIVE", _DEFAULT_PASSIVE).split(",") if p.strip()}
PASSIVE_BACKOFF = int(os.environ.get("ZELLO_PASSIVE_BACKOFF", "300"))


def supervisor(profile: str, seg_dir: Path, stats) -> None:
    """Keep one Zello listener session running forever (blocking)."""
    seg_dir.mkdir(parents=True, exist_ok=True)
    channel = CHANNELS[profile]
    passive = profile in PASSIVE
    backoff = PASSIVE_BACKOFF if passive else 5
    if not configured():
        logging.warning("[%s] Zello env not configured - listener idle", profile)
        stats.event(profile, "zello env missing (ZELLO_USER/PASS/ISSUER/PRIVATE_KEY)")
        while True:
            time.sleep(300)
    while True:
        try:
            run_session(profile, channel, seg_dir, stats)
        except Exception as e:  # noqa: BLE001
            logging.warning("[%s] zello session ended: %s", profile, e)
            stats.event(profile, f"zello reconnect: {str(e)[:200]}")
        logging.warning("[%s] zello reconnecting in %ss", profile, backoff)
        time.sleep(backoff)
        if not passive:
            backoff = min(backoff * 2, 120)
