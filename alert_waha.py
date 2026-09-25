"""WhatsApp alerts via the WAHA REST API (self-hosted WAHA or WAHA Cloud — both free tiers).

Pattern mirrors the original waha_client.py:
    POST {WAHA_URL}/api/sendText
    header X-Api-Key: <key>   (falls back to X-API-KEY)
    json: {"session": ..., "chatId": ..., "text": ...}

Env: WAHA_URL, WAHA_API_KEY, WAHA_CHAT_ID, WAHA_SESSION (default "default").
"""
from __future__ import annotations

import logging
import os

import aiohttp

_API_KEY_HEADERS = ("X-Api-Key", "X-API-KEY")


def _base() -> str:
    return os.environ.get("WAHA_URL", "").strip().rstrip("/")


def _key() -> str:
    return os.environ.get("WAHA_API_KEY", "").strip()


def _chat() -> str:
    return os.environ.get("WAHA_CHAT_ID", "").strip()


def _session() -> str:
    return os.environ.get("WAHA_SESSION", "default").strip() or "default"


def configured() -> bool:
    return bool(_base() and _key() and _chat())


async def send_text(text: str, chat_id: str | None = None) -> bool:
    """Send a WhatsApp text message. Returns True on success."""
    if not configured():
        logging.error("WAHA not configured (need WAHA_URL, WAHA_API_KEY, WAHA_CHAT_ID)")
        return False
    url = f"{_base()}/api/sendText"
    payload = {"session": _session(), "chatId": chat_id or _chat(), "text": text[:4000]}
    last_err = ""
    for hdr in _API_KEY_HEADERS:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    url, json=payload,
                    headers={"Content-Type": "application/json", hdr: _key()},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    body = (await r.text())[:200]
                    if r.status in (200, 201):
                        return True
                    last_err = f"HTTP {r.status}: {body}"
                    if r.status not in (401, 403):
                        break
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
    logging.error("WAHA sendText failed: %s", last_err)
    return False


async def check_session() -> str:
    """Return the WAHA session status string (e.g. 'WORKING') for startup logging."""
    if not configured():
        return "OFF (not configured)"
    url = f"{_base()}/api/sessions/{_session()}"
    for hdr in _API_KEY_HEADERS:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers={hdr: _key()},
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        if r.status not in (401, 403):
                            return f"ERROR HTTP {r.status}"
                        continue
                    data = await r.json()
                    return str(data.get("status", "UNKNOWN")).upper()
        except Exception as e:  # noqa: BLE001
            return f"ERROR {e}"
    return "ERROR (auth failed)"
