"""Runtime control-panel state (token-gated via status.py routes).

Stored at SEG_DIR/control.json; reloaded on change (mtime check). All values
have safe defaults matching long-standing production behavior.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_lock = threading.Lock()
_path = Path(os.environ.get("SEG_DIR", "./segments")) / "control.json"
_cache: dict = {"mtime": -1.0, "state": None}

DEFAULTS = {"excluded_natures": ["Fall"], "keyword_watches": [], "muted_feeds": []}


def load() -> dict:
    with _lock:
        try:
            m = _path.stat().st_mtime
        except OSError:
            m = 0.0
        if _cache["state"] is not None and m == _cache["mtime"]:
            return _cache["state"]
        st = {k: list(v) for k, v in DEFAULTS.items()}
        try:
            d = json.loads(_path.read_text())
            for k in DEFAULTS:
                if isinstance(d.get(k), list):
                    st[k] = [str(x) for x in d[k][:50]]
        except Exception:
            pass
        _cache["state"] = st
        _cache["mtime"] = m
        return st


def save(st: dict) -> None:
    with _lock:
        clean = {k: [str(x) for x in st.get(k, [])][:50] for k in DEFAULTS}
        _path.parent.mkdir(parents=True, exist_ok=True)
        _path.write_text(json.dumps(clean, indent=1))
        _cache["state"] = clean
        try:
            _cache["mtime"] = _path.stat().st_mtime
        except OSError:
            _cache["mtime"] = 0.0


def excluded_natures() -> set:
    return {x.strip().lower() for x in load()["excluded_natures"] if x.strip()}


def muted_feeds() -> set:
    return set(load()["muted_feeds"])


def keyword_watches() -> list:
    return [x.strip() for x in load()["keyword_watches"] if x.strip()]
