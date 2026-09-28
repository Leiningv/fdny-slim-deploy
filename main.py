"""fdny-slim - free-only dispatch monitor, rebuilt and operated by Instinct.

    Broadcastify live audio (continuous, overlapped segments)
      -> faster-whisper (local, energy-gated)
      -> detect (emergency? address?)
      -> WhatsApp (WAHA)

One capture supervisor + one consumer per feed. Alerts deduped for 30 minutes
(persisted to disk, best-effort across restarts). Status/health web server and
self-keepalive run alongside. Timestamps in America/New_York. No paid APIs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
import alert_waha
import detect
import ingest
import transcribe
import zello_ingest
from status import ARCHIVE_DIR, ARCHIVE_KEEP, Stats, keepalive, start_web

_OPS_Q: list[str] = []
_OPS_TASKS: list = []


def ops_log(line: str) -> None:
    logging.info("ops: %s", line)
    _OPS_Q.append(line)


async def _ops_flusher() -> None:
    while True:
        await asyncio.sleep(300)
        if not _OPS_Q:
            continue
        lines, _OPS_Q[:] = _OPS_Q[:12], _OPS_Q[12:]
        try:
            await alert_waha.send_ops("🛠 " + "\n".join(lines))
        except Exception as e:  # noqa: BLE001
            logging.warning("ops flush failed: %s", e)


def _ensure_ogg(clip_name: str):
    src = ARCHIVE_DIR / clip_name
    ogg = src.with_suffix(".ogg")
    if ogg.exists():
        return ogg.name
    try:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001
            ff = "ffmpeg"
        import subprocess
        subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-c:a", "libopus", "-b:a", "32k", str(ogg)],
                       check=True, timeout=60)
        return ogg.name
    except Exception as e:  # noqa: BLE001
        logging.warning("ogg convert failed for %s: %s", clip_name, e)
        return None

NY = ZoneInfo("America/New_York")
DEDUP_SEC = int(os.environ.get("DEDUP_SECONDS", str(30 * 60)))
# Freshness gate (user rule 9/28: "Never post an old recording - has to be on
# time. It's an alert system for first responders."). A stale alert is worse
# than none: suppress + ops-log instead of posting.
FRESH_LIVE_SEC = int(os.environ.get("FRESH_LIVE_SEC", "300"))   # Zello/HLS live: normal lag <2 min
FRESH_FDNY_SEC = int(os.environ.get("FRESH_FDNY_SEC", "600"))   # Broadcastify Calls: normal lag 2-5 min
SEG_DIR = Path(os.environ.get("SEG_DIR", "./segments"))
SEEN_FILE = Path(os.environ.get("SEEN_FILE", "./segments/seen.json"))
FDNY_INBOX = SEG_DIR / "fdny_inbox.jsonl"
FDNY_IDS = SEG_DIR / "fdny_ids.json"

SOURCE_LABEL = {"hatzolah": "Hatzolah Brooklyn", "sullivan": "Sullivan Co Fire/EMS",
                "fdny": "FDNY Brooklyn Dispatch"}


def _load_env_file(path: Path = Path("config.env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


ALERTS_LOG = SEG_DIR / "alerts.jsonl"


def _archive_clip(src: Path, name: str) -> None:
    """Keep a copy of a speech segment for the status page; prune per feed."""
    try:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copyfile(src, ARCHIVE_DIR / name)
    except Exception as e:  # noqa: BLE001
        logging.warning("clip archive failed: %s", e)
        return
    try:
        profile = name.rsplit("-", 1)[0]
        clips = sorted(ARCHIVE_DIR.glob(f"{profile}-*.wav"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in clips[ARCHIVE_KEEP:]:
            old.unlink()
    except Exception:  # noqa: BLE001
        pass


def _append_alert_log(entry: dict) -> None:
    try:
        SEG_DIR.mkdir(parents=True, exist_ok=True)
        with ALERTS_LOG.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _load_seen() -> dict:
    try:
        data = json.loads(SEEN_FILE.read_text())
        now = time.time()
        return {k: v for k, v in data.items() if now - v < DEDUP_SEC}
    except Exception:  # noqa: BLE001
        return {}


def _save_seen(seen: dict) -> None:
    try:
        SEG_DIR.mkdir(parents=True, exist_ok=True)
        SEEN_FILE.write_text(json.dumps(seen))
    except Exception as e:  # noqa: BLE001
        logging.warning("seen save failed: %s", e)



GEOCODE_VERIFY = os.environ.get("GEOCODE_VERIFY", "1") != "0"


_GEOCODE_ABBREV = {"Ave": "Avenue", "St": "Street", "Rd": "Road", "Blvd": "Boulevard",
                   "Pkwy": "Parkway", "Dr": "Drive", "Ln": "Lane", "Ct": "Court", "Pl": "Place"}


def _geocode_variants(addr: str, profile: str) -> list[str]:
    """Query rewrites: expand abbreviations; '14th Ave between 50th & 51st St' ->
    '14th Avenue & 51st Street'; locality hints per feed."""
    base = addr if ", NY" in addr else f"{addr}, NY"
    street, _, tail = base.partition(",")
    for a, b in _GEOCODE_ABBREV.items():
        street = re.sub(rf"\b{a}\b", b, street)
    import re as _re
    m = _re.search(r"(.+?)\s+between\s+(.+?)\s*&\s*(.+)", street)
    variants = []
    if m:
        variants.append(f"{m.group(1).strip()} & {m.group(3).strip()}{',' + tail if tail else ''}")
        variants.append(f"{m.group(1).strip()} & {m.group(2).strip()}{',' + tail if tail else ''}")
    variants.append(street + ("," + tail if tail else ""))
    if profile == "sullivan":
        variants.append(f"{street}, Sullivan County, NY")
        variants.append(f"{street}, Monticello, NY")
    if "hatzal" in profile.lower() or "hatzol" in profile.lower():
        # TSL/Chevra covers NYC + Sullivan/Five Towns: the extracted area suffix
        # is a guess ("Brooklyn" by default) - also try de-biased queries
        variants.append(f"{street}, Sullivan County, NY")
        variants.append(f"{street}, NY")
    return [v for i, v in enumerate(variants) if v not in variants[:i]]


async def _nominatim(q: str):
    import urllib.parse
    import aiohttp
    url = ("https://nominatim.openstreetmap.org/search?" +
           urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "addressdetails": 1}))
    try:
        async with aiohttp.ClientSession(
                headers={"User-Agent": "fdny-slim/1.0 dispatch monitor"}) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                return await r.json()
    except Exception:  # noqa: BLE001
        return None


async def _planning_labs(addr: str, allowed_boroughs: list[str]) -> tuple:
    """NYC Planning Labs geosearch (free, keyless). Returns (label, lat, lon)
    when the top hit is in an allowed borough, else (None, None, None).
    Network error -> ('', None, None)."""
    try:
        q = addr.replace(" ", "%20")
        url = f"https://geosearch.planninglabs.nyc/v2/search?text={q}&size=1"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return "", None, None
                data = await r.json()
        feats = data.get("features") or []
        if not feats:
            return None, None, None
        feat = feats[0]
        props = feat.get("properties") or {}
        borough = (props.get("borough") or "").lower()
        if borough not in [b.lower() for b in allowed_boroughs]:
            return None, None, None
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        lat = lon = None
        if len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
        label = str(props.get("label") or "") or None
        return label, lat, lon
    except Exception:  # noqa: BLE001
        return "", None, None


async def geocode_verify(addr: str, profile: str = "") -> tuple:
    """Returns (verified, in_sullivan_county, verified_label, lat, lon, locality).
    NYC profiles: Planning Labs with the old system's borough filters (FDNY
    Brooklyn-only; Hatzalah Brooklyn/Queens/Manhattan/Bronx), Nominatim fallback.
    Sullivan: Nominatim + county check."""
    p = profile.lower()
    if "fdny" in p or "hatzalah" in p or "hatzolah" in p:
        boroughs = ["Brooklyn"] if "fdny" in p else ["Brooklyn", "Queens", "Manhattan", "Bronx"]
        for q in _geocode_variants(addr, profile):
            label, lat, lon = await _planning_labs(q, boroughs)
            if label == "":
                break  # network failure -> Nominatim fallback
            if label:
                # reject fallback hits on a DIFFERENT street (e.g. "Ganser Road"
                # matching "Shore Road Park") - the label must share a rare
                # street token with the query, else it's not this address
                core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", q.split(",")[0]).strip().lower()
                qtoks = {t for t in re.split(r"[\s,.&'-]+", core)
                         if len(t) >= 4 and t not in _ADDR_GENERIC and not t.isdigit()}
                ltok = label.lower()
                if qtoks and not any(t in ltok for t in qtoks):
                    logging.info("geocode: rejected wrong-street fallback: %s -> %s", q, label)
                    continue
                return True, False, label, lat, lon, (label.split(",")[1].strip() if "," in label else "")
        if "fdny" in p:
            return False, False, "", None, None, ""
        # hatzalah: fall through to Nominatim for non-NYC (5 Towns, Rockland...)
    for q in _geocode_variants(addr, profile):
        res = await _nominatim(q)
        if res is None:
            return False, False, "", None, None, ""  # network/API failure: don't burn retries
        if res:
            disp = str(res[0].get("display_name", ""))
            ad = res[0].get("address") or {}
            if ("hatzal" in p or "hatzol" in p) and str(ad.get("state", "")) not in ("New York", "NY"):
                logging.info("geocode: rejected out-of-state hit: %s -> %s", q, disp)
                await asyncio.sleep(1.1)
                continue
            core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", q.split(",")[0]).strip().lower()
            qtoks = {t for t in re.split(r"[\s,.&'-]+", core)
                     if len(t) >= 4 and t not in _ADDR_GENERIC and not t.isdigit()}
            if qtoks and not any(t in disp.lower() for t in qtoks):
                logging.info("geocode: rejected wrong-street hit: %s -> %s", q, disp)
                await asyncio.sleep(1.1)
                continue
            county = str(ad.get("county", ""))
            locality = str(ad.get("village") or ad.get("town") or ad.get("city")
                           or ad.get("hamlet") or ad.get("borough") or "")
            lat = lon = None
            try:
                lat, lon = float(res[0].get("lat")), float(res[0].get("lon"))
            except (TypeError, ValueError):
                pass
            return True, ("Sullivan" in county or "Sullivan County" in disp), disp, lat, lon, locality
        await asyncio.sleep(1.1)  # nominatim 1 req/s
    return False, False, "", None, None, ""


async def _cross_streets(lat: float, lon: float, address: str) -> tuple:
    """Cross streets via Overpass (free, keyless): ways sharing a node with the
    job's own street truly cross it. Returns (crosses, exact) - ('A & B', True),
    or ('A & B', False) when falling back to nearest streets, or (None, False)."""
    import math
    q = (f'[out:json][timeout:15];way(around:250,{lat},{lon})'
         f'[highway][name];out tags geom;')
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}
    data = None
    for endpoint in ("https://overpass-api.de/api/interpreter",
                     "https://overpass.kumi.systems/api/interpreter"):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(endpoint, data={"data": q}, headers=hdrs,
                                  timeout=aiohttp.ClientTimeout(total=18)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    break
        except Exception:  # noqa: BLE001
            continue
    if data is None:
        return None, False
    skip_hw = {"service", "footway", "path", "track", "cycleway", "pedestrian",
               "steps", "construction", "proposed", "corridor", "bus_stop"}
    own = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", address).strip().lower()
    own = re.sub(r"[,.;].*$", "", own).strip()
    cos_lat = math.cos(math.radians(lat))

    def _dist2(geom):
        return min(((g.get("lon", lon) - lon) * cos_lat * 111320) ** 2 +
                   ((g.get("lat", lat) - lat) * 110540) ** 2 for g in geom)

    own_nodes = set()
    cands = []
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        hw = tags.get("highway")
        geom = el.get("geometry") or []
        if not name or hw in skip_hw or not geom:
            continue
        nl = name.lower().strip()
        is_own = (nl == own or (len(own) >= 6 and own in nl)
                  or (len(nl) >= 6 and nl in own))
        if is_own:
            for g in geom:
                own_nodes.add((round(g.get("lat", 0), 6), round(g.get("lon", 0), 6)))
        else:
            cands.append((name, geom))
    rows = {}
    for name, geom in cands:
        crosses = any((round(g.get("lat", 0), 6), round(g.get("lon", 0), 6)) in own_nodes
                      for g in geom)
        d2 = _dist2(geom)
        nl = name.lower()
        if nl not in rows or (crosses and not rows[nl][1]) or d2 < rows[nl][0]:
            rows[nl] = (d2, crosses, name)
    if not rows:
        return None, False
    exact = sorted((v for v in rows.values() if v[1]))
    approx = sorted((v for v in rows.values() if not v[1]))
    if len(exact) >= 2:
        return f"{exact[0][2]} & {exact[1][2]}", True
    if len(exact) == 1 and approx:
        return f"{exact[0][2]} & {approx[0][2]}", True
    if len(approx) >= 2:
        return f"{approx[0][2]} & {approx[1][2]}", False
    return None, False


async def _map_street_names(lat: float, lon: float, street: str = "") -> set:
    """Canonical street-name pool for fixing whisper-mangled names ('Nickabocker'
    -> 'Knickerbocker'). Primary: every street crossing the incident street - a
    wrong house number can put the geocoded point far from the spoken crosses,
    so a point-radius pool alone misses them. Fallback: names around the point.
    Overpass is free/keyless; failures just skip canonicalization."""
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}
    eps = ("https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter")

    async def _ov(q: str):
        for endpoint in eps:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(endpoint, data={"data": q}, headers=hdrs,
                                      timeout=aiohttp.ClientTimeout(total=12)) as r:
                        if r.status != 200:
                            continue
                        return await r.json()
            except Exception:  # noqa: BLE001
                continue
        return None

    async def _build() -> set:
        pool: set = set()
        if street:
            pat = re.escape(street.strip())
            d1 = await _ov(f"[out:json][timeout:10];way(around:3000,{lat},{lon})"
                           f"[highway][name~\"^{pat}$\",i];node(w);out ids;")
            ids = [str(e["id"]) for e in (d1 or {}).get("elements") or [] if e.get("id")]
            if ids:
                d2 = await _ov(f"[out:json][timeout:10];node(id:{','.join(ids)})->.n;"
                               f"way(bn.n)[highway][name];out tags;")
                pool |= {(el.get("tags") or {}).get("name", "").strip()
                         for el in (d2 or {}).get("elements") or []
                         if (el.get("tags") or {}).get("name")}
        if not pool:
            d3 = await _ov(f"[out:json][timeout:10];way(around:800,{lat},{lon})[highway][name];out tags;")
            pool |= {(el.get("tags") or {}).get("name", "").strip()
                     for el in (d3 or {}).get("elements") or []
                     if (el.get("tags") or {}).get("name")}
        return pool

    try:
        return await asyncio.wait_for(_build(), timeout=30)
    except Exception:  # noqa: BLE001 - never delay an alert over spelling polish
        return set()


def _canon_name(name: str, pool: set) -> str:
    """Fuzzy-normalize a (possibly whisper-mangled) street name to the
    map-canonical spelling from the local pool. Conservative: only replaces
    on a close confident match, otherwise keeps the original."""
    import difflib
    nl = name.lower().strip()
    if not nl or not pool:
        return name
    best, best_r = None, 0.0
    for cand in pool:
        r = difflib.SequenceMatcher(None, nl, cand.lower()).ratio()
        if r > best_r:
            best, best_r = cand, r
    if best and best_r >= 0.75 and best.lower() != nl:
        return best
    return name


RECENT_FILE = Path(os.environ.get("RECENT_FILE", "./segments/recent_posts.json"))
_INCIDENT_DEDUP_SEC = 600
_ADDR_GENERIC = {"street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd",
                 "place", "pl", "drive", "dr", "lane", "ln", "parkway", "pkwy", "court",
                 "ct", "east", "west", "north", "south", "ny", "brooklyn", "new", "york",
                 "queens", "manhattan", "bronx", "and", "the", "between", "county", "co"}


def _rare_tokens(addr: str) -> set:
    return {t for t in re.split(r"[\s,.&'-]+", addr.lower())
            if len(t) >= 4 and t not in _ADDR_GENERIC and not t.isdigit()}


def _load_recent() -> list:
    try:
        data = json.loads(RECENT_FILE.read_text())
        now = time.time()
        return [r for r in data if now - r.get("t", 0) < _INCIDENT_DEDUP_SEC]
    except Exception:  # noqa: BLE001
        return []


def _save_recent(rows: list) -> None:
    try:
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECENT_FILE.write_text(json.dumps(rows[-50:]))
    except Exception:  # noqa: BLE001
        pass


async def verify_and_send(profile: str, hit: dict, stats, clip_name: str | None = None,
                            fresh_ts: float | None = None) -> str:
    """User's posting rules (9/28): verified addresses only; Sullivan feed posts
    only Sullivan-County-verified addresses; unverifiable posts marked not confirmed.
    Returns 'sent' | 'queued' | 'suppressed'."""
    now = time.time()
    if fresh_ts:
        fresh_limit = FRESH_FDNY_SEC if profile == "fdny" else FRESH_LIVE_SEC
        age = time.time() - fresh_ts
        if age > fresh_limit:
            logging.info("[%s] suppressed (stale, %.0fm old, limit %dm): %s @ %s",
                         profile, age / 60, fresh_limit / 60, hit["nature"], hit["address"])
            stats.event(profile, f"suppressed (stale, {age / 60:.0f}m old): {hit['nature']} @ {hit['address']}")
            ops_log(f"suppressed (stale, {age / 60:.0f}m old): {hit['nature']} @ {hit['address']}")
            return "suppressed"
    nat_norm = (hit.get("nature") or "").strip().lower()
    toks = _rare_tokens(hit["address"])
    if nat_norm and toks:
        for r in _load_recent():
            if r.get("nature") == nat_norm and toks & set(r.get("tokens") or []):
                logging.info("[%s] suppressed (duplicate incident): %s @ %s",
                             profile, hit["nature"], hit["address"])
                stats.event(profile, f"suppressed (dup incident): {hit['nature']} @ {hit['address']}")
                ops_log(f"suppressed (dup incident): {hit['nature']} @ {hit['address']}")
                return "suppressed"
    if re.match(r"^FDNY Box \d+", hit["address"]):
        logging.info("[%s] suppressed (bare box, no street address): %s", profile, hit["address"])
        stats.event(profile, f"suppressed (bare box): {hit['address']}")
        ops_log(f"suppressed (bare box): {hit['address']}")
        return "suppressed"
    if not (hit.get("nature") or "").strip():
        logging.info("[%s] suppressed (no discernible nature): %s", profile, hit["address"])
        stats.event(profile, f"suppressed (no nature): {hit['address']}")
        ops_log(f"suppressed (no nature): {hit['address']}")
        return "suppressed"
    if profile.lower().startswith(("hatzalah", "zello-hatzalah")) and hit.get("nature") == "Fall":
        logging.info("[%s] suppressed (Hatzalah Fall excluded): %s", profile, hit["address"])
        stats.event(profile, f"suppressed (Fall excluded): {hit['address']}")
        ops_log(f"suppressed (Fall excluded): {hit['address']}")
        return "suppressed"
    ogg_task = None
    if clip_name:
        # Convert the voice note concurrently with geocode/canonicalization so
        # text and audio can post back-to-back (user rule 9/28: "Job has to be
        # posted same second as audio"). Conversion is ~1-2s, verification is
        # usually slower, so the text post is not delayed.
        ogg_task = asyncio.create_task(asyncio.to_thread(_ensure_ogg, clip_name))
    verified = True
    verified_label = ""
    lat = lon = None
    locality = ""
    if GEOCODE_VERIFY:
        verified, in_sullivan, verified_label, lat, lon, locality = await geocode_verify(hit["address"], profile)
        if (verified and locality and profile.lower().startswith(("hatzalah", "zello-hatzalah"))
                and locality.lower() not in ("brooklyn", "queens", "manhattan", "bronx", "new york")):
            fixed = re.sub(r",\s*[^,]+,\s*NY$", f", {locality}, NY", hit["address"])
            if fixed != hit["address"]:
                logging.info("[%s] area corrected by geocode: %s -> %s", profile, hit["address"], fixed)
                stats.event(profile, f"area corrected: {hit['address']} -> {fixed}")
                hit["address"] = fixed
        if profile == "sullivan" and verified and not in_sullivan:
            logging.info("[%s] suppressed (verified outside Sullivan Co): %s", profile, hit["address"])
            stats.event(profile, f"suppressed (outside Sullivan Co): {hit['nature']} @ {hit['address']}")
            ops_log(f"suppressed (outside Sullivan Co): {hit['nature']} @ {hit['address']}")
            return "suppressed"
        if not verified:
            stats.event(profile, f"unconfirmed address: {hit['address']}")
    cross = (hit.get("cross") or "").strip()
    if not cross and lat is not None and lon is not None and verified_label:
        street_core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", hit["address"])
        street_core = re.sub(r"[,.;].*$", "", street_core).strip().lower()
        if street_core and street_core in verified_label.lower():
            cross, exact = await _cross_streets(lat, lon, hit["address"])
            cross = cross or ""
            if cross:
                tag = "computed" if exact else "approx"
                stats.event(profile, f"cross streets ({tag}): {cross}")
    if cross and lat is not None and lon is not None and verified_label:
        core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", hit["address"].split(",")[0]).strip()
        pool = await _map_street_names(lat, lon, core)
        if pool:
            parts = [p.strip() for p in cross.split("&", 1)]
            canon = [_canon_name(p, pool) for p in parts]
            new_cross = " & ".join(canon)
            if new_cross != cross:
                logging.info("[%s] crosses canonicalized: %s -> %s", profile, cross, new_cross)
                stats.event(profile, f"crosses canonicalized: {cross} -> {new_cross}")
                cross = new_cross
            canon_core = _canon_name(core, pool)
            if canon_core != core:
                fixed_addr = hit["address"].replace(core, canon_core, 1)
                logging.info("[%s] address canonicalized: %s -> %s", profile, hit["address"], fixed_addr)
                stats.event(profile, f"address canonicalized: {hit['address']} -> {fixed_addr}")
                hit["address"] = fixed_addr
    if not cross:
        ops_log(f"cross streets unresolved: {hit['nature']} @ {hit['address']}")
    colony = None
    if profile.lower().startswith(("sullivan", "hatzalah", "zello-sullivan", "zello-hatzalah")):
        try:
            import sullivan_colonies as scol
            if verified_label:
                r0 = scol.match_colony_for_verified_address(verified_label)
                colony = r0.colony_name if r0.found else None
            if not colony:
                colony = scol.match_sullivan_colony(hit.get("excerpt") or "")
        except Exception as e:  # noqa: BLE001
            logging.warning("colony match failed: %s", e)
    text_out = format_alert(hit, crosses=cross, confirmed=verified, footer=colony)
    ogg = None
    if ogg_task is not None:
        try:
            ogg = await ogg_task
        except Exception:  # noqa: BLE001
            ogg = None
    ok = await alert_waha.send_text(text_out)
    if not ok:
        ops_log(f"ALERT POST FAILED: {hit['nature']} @ {hit['address']}")
        return "queued"
    if clip_name:
        if ogg:
            base = os.environ.get("RENDER_EXTERNAL_URL", "https://fdny-slim.onrender.com").rstrip("/")
            vok = await alert_waha.send_voice(f"{base}/audio/{ogg}")
            if not vok:
                ops_log(f"voice-note send failed: {hit['nature']} @ {hit['address']}")
        else:
            ops_log(f"voice-note convert failed: {hit['nature']} @ {hit['address']}")
    if nat_norm and toks:
        recent = _load_recent()
        recent.append({"t": now, "nature": nat_norm, "tokens": sorted(toks)})
        _save_recent(recent)
    return "sent"


def format_alert(hit: dict, crosses: str = "", confirmed: bool = True,
                 footer: str | None = None) -> str:
    """User-picked layout (9/28, option 1): bold caps nature header with fire
    emoji; bold pinned address; plain 'between X & Y' crosses line; time;
    italic source footer at the very bottom. No transcript quote, ever.
    Audio follows separately as a voice-note bubble."""
    now = datetime.now(NY).strftime("%-I:%M %p")
    nature = (hit.get("nature") or "").strip().upper()
    addr_line = f"\N{ROUND PUSHPIN} *{hit['address']}*"
    if not confirmed:
        addr_line += " (not confirmed)"
    lines = [f"*\N{FIRE} {nature}*", "", addr_line]
    if crosses:
        lines.append(f"between {crosses}")
    lines += ["", f"\N{CLOCK FACE ONE OCLOCK} {now}"]
    label = footer or SOURCE_LABEL.get(hit["source"], hit["source"])
    lines.append(f"_{label}_")
    return "\n".join(lines)


def _concat_pcm(a: Path, b: Path, out: Path) -> bool:
    """Concat two 16kHz mono pcm_s16le WAVs into one. Pure stdlib."""
    import wave
    try:
        with wave.open(str(a), "rb") as wa, wave.open(str(b), "rb") as wb:
            frames = wa.readframes(wa.getnframes()) + wb.readframes(wb.getnframes())
        with wave.open(str(out), "wb") as wo:
            wo.setnchannels(1)
            wo.setsampwidth(2)
            wo.setframerate(16000)
            wo.writeframes(frames)
        return True
    except Exception as e:  # noqa: BLE001
        logging.warning("concat failed: %s", e)
        return False


async def consumer(profile: str, stats: Stats, seen: dict) -> None:
    """Pick up finished segments for one feed, transcribe pairs, detect, alert.

    Transcribing the adjacent pair (prev+current) puts every segment boundary
    mid-audio in one of the pairs, so a dispatch split across a boundary is
    still captured whole. The RMS gate on both halves keeps silent periods
    free; the 30-min dedup absorbs the intentional 2x coverage.
    """
    processed: dict[str, float] = {}  # name -> mtime already handled
    prev: Path | None = None
    pair_out = SEG_DIR / f"pair-{profile}.wav"
    while True:
        for wav in ingest.ready_segments(profile, SEG_DIR):
            mtime = wav.stat().st_mtime
            if processed.get(wav.name) == mtime:
                continue
            processed[wav.name] = mtime
            if len(processed) > ingest.SEG_WRAP * 2:
                for name in list(processed):
                    if not (SEG_DIR / name).exists():
                        processed.pop(name, None)
            stats.mark_segment(profile)
            level = transcribe.rms(wav)
            if level < transcribe.RMS_MIN and (prev is None or transcribe.rms(prev) < transcribe.RMS_MIN):
                stats.mark_silence(profile)
                prev = wav
                continue
            target = wav
            if prev is not None and _concat_pcm(prev, wav, pair_out):
                target = pair_out
            prev = wav
            text = await asyncio.to_thread(transcribe.transcribe, target)
            if not text:
                continue
            stats.mark_transcript(profile, text)
            logging.info("[%s] heard: %s", profile, text[:160])
            clip_name = f"{profile}-{int(time.time())}.wav"
            await asyncio.to_thread(_archive_clip, target, clip_name)
            stats.mark_clip(profile, clip_name, text)
            hit = detect.analyze(text, profile)
            if not hit:
                continue
            key = f"{profile}|{hit['nature']}|{hit['address']}"
            now = time.time()
            if now - seen.get(key, 0) < DEDUP_SEC:
                logging.info("[%s] deduped: %s @ %s", profile, hit["nature"], hit["address"])
                stats.event(profile, f"deduped: {hit['nature']} @ {hit['address']}")
                continue
            seen[key] = now
            _save_seen(seen)
            outcome = await verify_and_send(profile, hit, stats, clip_name,
                                            fresh_ts=wav.stat().st_mtime)
            ok = outcome == "sent"
            stats.mark_alert(profile, hit["nature"], hit["address"], ok, failed=(outcome == "queued"))
            _append_alert_log({"t": now, "feed": profile, "nature": hit["nature"],
                               "address": hit["address"], "sent": ok,
                               "excerpt": hit["excerpt"]})
            logging.info("[%s] ALERT %s @ %s - sent=%s", profile, hit["nature"], hit["address"], ok)
        await asyncio.sleep(2)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return default


def _fdny_fetch_clip(url: str, m4a: Path, wav: Path) -> Path | None:
    """Download one Calls audio file and convert to 16kHz mono WAV."""
    import subprocess
    import urllib.request
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "fdny-slim/1.0",
                          "Referer": "https://www.broadcastify.com/calls/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 500:
            return None
        m4a.write_bytes(data)
        rc = subprocess.call([
            ingest.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(m4a), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
        if rc != 0 or not wav.exists():
            return None
        return wav
    except Exception as e:  # noqa: BLE001
        logging.warning("[fdny] clip fetch failed: %s", e)
        return None


async def _fdny_handle_call(call: dict, stats: Stats, seen: dict, tmp: Path) -> None:
    stats.mark_segment("fdny")
    cid = str(call.get("id") or call.get("filename") or int(time.time()))
    text = (call.get("transcription") or "").strip()
    wav = None
    url = call.get("audio_url") or ""
    if url:
        tmp.mkdir(parents=True, exist_ok=True)
        wav = await asyncio.to_thread(_fdny_fetch_clip, url, tmp / f"{cid}.m4a", tmp / f"{cid}.wav")
    if not text and wav is not None:
        text = await asyncio.to_thread(transcribe.transcribe, wav)
    if not text:
        stats.event("fdny", "call with no transcription - detect skipped")
        return
    stats.mark_transcript("fdny", text)
    logging.info("[fdny] heard: %s", text[:160])
    if wav is not None:
        clip_name = f"fdny-{int(time.time())}.wav"
        await asyncio.to_thread(_archive_clip, wav, clip_name)
        stats.mark_clip("fdny", clip_name, text)
    for suffix in (".m4a", ".wav"):
        try:
            (tmp / f"{cid}{suffix}").unlink()
        except Exception:  # noqa: BLE001
            pass
    hit = detect.analyze(text, "fdny")
    if not hit:
        return
    key = f"fdny|{hit['nature']}|{hit['address']}"
    now = time.time()
    if now - seen.get(key, 0) < DEDUP_SEC:
        logging.info("[fdny] deduped: %s @ %s", hit["nature"], hit["address"])
        stats.event("fdny", f"deduped: {hit['nature']} @ {hit['address']}")
        return
    seen[key] = now
    _save_seen(seen)
    try:
        call_ts = float(call.get("ts") or 0) or None
    except Exception:  # noqa: BLE001
        call_ts = None
    outcome = await verify_and_send("fdny", hit, stats, clip_name, fresh_ts=call_ts)
    ok = outcome == "sent"
    stats.mark_alert("fdny", hit["nature"], hit["address"], ok, failed=(outcome == "queued"))
    _append_alert_log({"t": now, "feed": "fdny", "nature": hit["nature"],
                       "address": hit["address"], "sent": ok,
                       "excerpt": hit["excerpt"]})
    logging.info("[fdny] ALERT %s @ %s - sent=%s", hit["nature"], hit["address"], ok)


async def fdny_consumer(stats: Stats, seen: dict) -> None:
    """Process FDNY Calls pushed by the off-box poller.

    www.broadcastify.com refuses Render egress, so the Calls poll/login runs
    in the sandbox relay (same as the HLS URL relay) and POSTs new calls to
    /fdny_calls, which appends them to FDNY_INBOX. The call AUDIO lives on
    the calls CDN, which Render can reach, so clips are downloaded here.
    Server-side transcription rides along free with each call; the local
    whisper is only the fallback. From here on it is the exact same
    detect -> 30-min dedup -> WAHA -> status-page path as the live feeds.
    """
    ids: dict = _load_json(FDNY_IDS, {})
    offset = 0
    tmp = SEG_DIR / "fdny_tmp"
    while True:
        try:
            if FDNY_INBOX.exists():
                size = FDNY_INBOX.stat().st_size
                if size < offset:
                    offset = 0
                if size > offset:
                    with FDNY_INBOX.open("r") as fh:
                        fh.seek(offset)
                        chunk = fh.read()
                        offset = fh.tell()
                    for line in chunk.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            call = json.loads(line)
                        except Exception:  # noqa: BLE001
                            continue
                        cid = str(call.get("id") or call.get("filename") or "")
                        if not cid or cid in ids:
                            continue
                        now = time.time()
                        ids = {k: v for k, v in ids.items() if now - v < 48 * 3600}
                        ids[cid] = now
                        try:
                            FDNY_IDS.write_text(json.dumps(ids))
                        except Exception:  # noqa: BLE001
                            pass
                        await _fdny_handle_call(call, stats, seen, tmp)
        except Exception as e:  # noqa: BLE001
            logging.warning("[fdny] consumer error: %s", e)
        await asyncio.sleep(2)


async def waha_watch(stats: Stats) -> None:
    while True:
        stats.waha_status = await alert_waha.check_session()
        await asyncio.sleep(300)


async def amain() -> None:
    _load_env_file()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    ingest.check_ffmpeg()
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("BROADCASTIFY_USER"):
        logging.warning("BROADCASTIFY_USER not set - streams will refuse the connection")

    stats = Stats()
    try:
        if ALERTS_LOG.exists():
            for line in ALERTS_LOG.read_text().splitlines()[-100:]:
                a = json.loads(line)
                if time.time() - a.get("t", 0) < 7 * 86400:
                    stats.alerts.append({"t": a["t"], "feed": a["feed"], "nature": a["nature"],
                                         "address": a["address"], "sent": a.get("sent", True)})
            stats.alerts_sent = sum(1 for a in stats.alerts if a["sent"])
    except Exception as e:  # noqa: BLE001
        logging.warning("alert log restore failed: %s", e)
    stats.waha_status = await alert_waha.check_session()
    logging.info("WAHA session status: %s", stats.waha_status)
    if not alert_waha.configured():
        logging.warning("WAHA not fully configured - alerts will fail until WAHA_URL/API_KEY/CHAT_ID are set")

    loop = asyncio.get_running_loop()
    hls_profiles = [] if os.environ.get("HLS_DISABLED", "1") == "1" else list(ingest.FEEDS)
    # legacy broadcastify HLS is 403-blocked from Render egress and replaced by
    # the Zello listener; set HLS_DISABLED=0 to re-enable
    for profile in hls_profiles:
        loop.run_in_executor(None, ingest.supervisor, profile, SEG_DIR, stats)
    for profile in zello_ingest.CHANNELS:
        loop.run_in_executor(None, zello_ingest.supervisor, profile, SEG_DIR, stats)
    stats.mark_ffmpeg_start("fdny")  # push-driven capture; keeps the card honest
    stats.event("fdny", "calls ingest armed (sandbox poller -> /fdny_calls)")
    seen = _load_seen()
    logging.info("monitoring feeds: %s", ", ".join(f"{p}={fid}" for p, fid in ingest.FEEDS.items()))
    await start_web(stats)
    _OPS_TASKS.append(asyncio.create_task(_ops_flusher()))
    await asyncio.gather(
        *(consumer(p, stats, seen) for p in hls_profiles),
        *(consumer(p, stats, seen) for p in zello_ingest.CHANNELS),
        fdny_consumer(stats, seen),
        keepalive(stats),
        waha_watch(stats),
    )


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        logging.info("stopped")


if __name__ == "__main__":
    main()
