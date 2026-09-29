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
import control
import detect
from fdny_correction_guard import CorrectionGuard
import ingest
import transcribe
import zello_ingest
from status import ARCHIVE_DIR, ARCHIVE_KEEP, Stats, keepalive, start_web, plain_event

_OPS_Q: list[str] = []
_OPS_TASKS: list = []


def ops_log(line: str) -> None:
    line = plain_event(line)
    logging.info("ops: %s", line)
    _OPS_Q.append(line)


async def _kw_check(profile: str, text: str) -> None:
    """Post a heads-up to the ops group when a transcript hits a watched keyword."""
    try:
        watches = control.keyword_watches()
    except Exception:  # noqa: BLE001
        return
    low = text.lower()
    hits = [w for w in watches if w.lower() in low]
    if hits:
        stats.event(profile, f"watch hit ({', '.join(hits)}): {text[:120]}")
        ops_log(f"\U0001F440 watch hit [{profile}] ({', '.join(hits)}): {text[:200]}")


async def _uguu_upload(path: Path) -> str:
    """Upload a short-lived archive copy of the voice-note OGG."""
    try:
        data = aiohttp.FormData()
        data.add_field("files[]", path.read_bytes(), filename=path.name,
                       content_type="audio/ogg")
        async with aiohttp.ClientSession() as s:
            async with s.post("https://uguu.se/upload?output=json", data=data,
                              timeout=aiohttp.ClientTimeout(total=45)) as r:
                d = await r.json(content_type=None)
        url = str(((d.get("files") or [{}])[0]).get("url") or "")
        if d.get("success") and url.startswith("https://"):
            return url
        logging.warning("uguu upload rejected: %s", str(d)[:200])
    except Exception as e:  # noqa: BLE001
        logging.warning("uguu upload failed: %s", e)
    return ""


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
    # A previous interrupted conversion may have left a zero-byte OGG. Never
    # publish that path as a recording; force a fresh conversion instead.
    if ogg.exists():
        if ogg.stat().st_size > 100:
            return ogg.name
        ogg.unlink(missing_ok=True)
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

SOURCE_LABEL = {"hatzolah": "Hatzolah Dispatch", "sullivan": "Sullivan Co Fire/EMS",
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
    base = addr if re.search(r",\s*(?:NY|NJ)$", addr, re.I) else f"{addr}, NY"
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
    # digit-word road names: the map spells them out ('Marcel 4 Road' ->
    # 'Marcel Four Road', Eldred 9/28). Lookahead to the street type keeps
    # house numbers and ordinals untouched.
    _SPELL = {"1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five",
              "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine", "10": "Ten"}
    _md = re.search(r"\b(\d{1,2})\b(?=\s+(?:road|rd|street|st|avenue|ave|drive|dr|"
                    r"lane|ln|court|ct|place|pl|boulevard|blvd)\b)", street, re.I)
    if _md and _md.group(1) in _SPELL:
        spelled = street[:_md.start()] + _SPELL[_md.group(1)] + street[_md.end():]
        variants.append(spelled + ("," + tail if tail else ""))
    if profile == "sullivan":
        variants.append(f"{street}, Sullivan County, NY")
        variants.append(f"{street}, Monticello, NY")
    if "hatzal" in profile.lower() or "hatzol" in profile.lower():
        # TSL/Chevra covers NYC + Sullivan/Five Towns: the extracted area suffix
        # is a guess ("Brooklyn" by default) - also try de-biased queries
        variants.append(f"{street}, Sullivan County, NY")
        variants.append(f"{street}, NY")
        if base.endswith(", NJ"):
            variants.insert(0, f"{street}, Bergen County, NJ")
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
        from urllib.parse import quote
        q = quote(addr, safe="")
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


def _street_sides(core: str) -> list:
    return [s.strip() for s in re.split(r"\s+&\s+", core) if s.strip()]


def _street_token_groups(side: str) -> list:
    """Rare street tokens as groups of equivalent forms: an ordinal and its
    digit form ('64th'/'64') are ONE requirement - the map normalizes to the
    digit form. Every group of at least one side must hit for a street to
    verify ('Israel Ocean Parkway' passed on 'ocean' alone 9/28 12:46 PM;
    'Monticello 4 Road' matched the VILLAGE name 9/28 7:38 AM)."""
    toks = {t for t in re.split(r"[\s,.&'-]+", side.lower())
            if ((len(t) >= 4) or (len(t) == 1 and t.isalpha()))
            and t not in _ADDR_GENERIC and not t.isdigit()}
    groups = []
    for t in toks:
        m_ord = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", t)
        groups.append({t, m_ord.group(1)} if m_ord else {t})
    return groups


def _side_verifies(side: str, target: str) -> bool:
    gs = _street_token_groups(side)
    return bool(gs) and all(any(_tok_hit(v, target) for v in g) for g in gs)


async def geocode_verify(addr: str, profile: str = "") -> tuple:
    """Returns (verified, in_sullivan_county, verified_label, lat, lon, locality).
    NYC profiles: Planning Labs, with FDNY restricted to the spoken borough.
    Sullivan: Nominatim plus county check."""
    p = profile.lower()
    if "fdny" in p or "hatzalah" in p or "hatzolah" in p:
        boroughs = ["Brooklyn", "Queens", "Manhattan", "Bronx", "Staten Island"]
        requested_area = addr.split(",")[1].strip().lower() if "," in addr else ""
        if addr.upper().endswith(", NJ") or (requested_area and requested_area not in
                ("brooklyn", "queens", "manhattan", "bronx", "staten island", "riverdale", "new york")):
            boroughs = []  # Non-borough NY towns must resolve with county/town-aware Nominatim.
        for q in _geocode_variants(addr, profile):
            if not boroughs:
                break  # NJ uses county-aware Nominatim; NYC search is invalid.
            allowed = ([requested_area.title()] if "fdny" in p and requested_area in
                       ("brooklyn", "queens", "manhattan", "bronx", "staten island")
                       else boroughs)
            label, lat, lon = await _planning_labs(q, allowed)
            if label == "":
                break  # network failure -> Nominatim fallback
            if label:
                # reject fallback hits on a DIFFERENT street (e.g. "Ganser Road"
                # matching "Shore Road Park") - the label must share a rare
                # street token with the query, else it's not this address
                core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", q.split(",")[0]).strip().lower()
                ltok = label.lower()
                # (the query's '&' reaches PL unencoded, so intersection
                # queries geocode the LEFT street - side-aware matching is
                # what keeps 'X & Y' verifiable at all)
                sides = _street_sides(core)
                if not any(_street_token_groups(s) for s in sides):
                    # Numbered NYC avenues like 8th Avenue have no rare word.
                    # The map's borough feature is checked in _planning_labs;
                    # demand the SAME house and normalized road here. Without
                    # this, 1615 8th Avenue is rejected despite an exact map
                    # label. Unnumbered generic chatter still fails closed.
                    from fdny_borough_gate import exact_numbered_fdny_match
                    exact_house = ("fdny" in p and
                                   exact_numbered_fdny_match(q, label) and
                                   bool(re.match(r"^\s*\d{1,5}(?:-\d{1,3})?[A-Za-z]?\s+", q)))
                    if not exact_house and (len(core.split()) <= 2 or core not in ltok):
                        logging.info("geocode: rejected generic-street fallback: %s -> %s", q, label)
                        continue
                elif not any(_side_verifies(s, ltok) for s in sides):
                    # EVERY distinctive word of one side must hit - 'Israel
                    # Ocean Parkway' verified on 'ocean' alone while 'israel'
                    # (the shul name) was ignored (bad post 9/28 12:46 PM)
                    logging.info("geocode: rejected partial-token fallback: %s -> %s", q, label)
                    continue
                if "fdny" in p:
                    from fdny_borough_gate import exact_numbered_fdny_match
                    if not exact_numbered_fdny_match(q, label):
                        logging.info("geocode: rejected mismatched numbered FDNY address: %s -> %s", q, label)
                        continue
                # Planning Labs labels use neighborhoods (Jamaica, NY) rather
                # than boroughs (Queens); the feature borough property is
                # checked by _planning_labs, and exact numbered house/road is
                # verified again by the caller. Do not reject Jamaica as not
                # Queens just because its label names the neighborhood.
                found_borough = label.split(",")[1].strip() if "," in label else ""
                requested_area = addr.split(",")[1].strip() if "," in addr else ""
                if "hatzal" in p or "hatzol" in p:
                    permitted_boroughs = {
                        "brooklyn": {"brooklyn"}, "queens": {"queens"},
                        "manhattan": {"manhattan", "new york"},
                        "bronx": {"bronx"}, "riverdale": {"bronx"},
                        "staten island": {"staten island"},
                    }
                    expected = permitted_boroughs.get(requested_area.lower())
                    if expected is not None and found_borough.lower() not in expected:
                        continue
                    if requested_area.lower() in ("rockland", "monsey"):
                        continue
                return True, False, label, lat, lon, (requested_area.title() if "fdny" in p and requested_area else found_borough)
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
            state = str(ad.get("state", ""))
            county_name = str(ad.get("county", ""))
            if "hatzal" in p or "hatzol" in p:
                # An explicit NJ address must resolve to Bergen County. NY hits
                # must not cross into excluded Rockland or unspecified Catskills.
                permitted = ((state in ("New York", "NY") and
                              ("Rockland" not in county_name) and
                              (not addr.upper().endswith(", NJ")) and
                              (county_name in ("Kings County", "Queens County", "New York County",
                                               "Bronx County", "Richmond County", "Sullivan County",
                                               "Nassau County") or
                               any(x in county_name for x in ("Kings", "Queens", "Bronx", "Richmond", "Sullivan", "Nassau"))))
                             or (state in ("New Jersey", "NJ") and "Bergen" in county_name
                                 and addr.upper().endswith(", NJ")))
                if not permitted:
                    logging.info("geocode: rejected outside Hatzalah coverage: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
            # coverage gate: these channels serve NYC metro + the Catskills -
            # in-state is not enough ('3457 Northland Avenue' fuzzy-matched
            # Buffalo, 470km away, and posted to the Brooklyn group 9/28 14:26)
            try:
                _la, _lo = float(res[0].get("lat")), float(res[0].get("lon"))
                import math as _math
                def _km(a1, o1, a2, o2):
                    r = _math.pi / 180
                    h = (_math.sin((a2 - a1) * r / 2) ** 2
                         + _math.cos(a1 * r) * _math.cos(a2 * r)
                         * _math.sin((o2 - o1) * r / 2) ** 2)
                    return 6371 * 2 * _math.asin(_math.sqrt(h))
                if min(_km(_la, _lo, 40.7128, -74.0060),
                       _km(_la, _lo, 41.6556, -74.6893)) > 130:
                    logging.info("geocode: rejected out-of-coverage hit: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
            except (TypeError, ValueError):
                pass
            core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", q.split(",")[0]).strip().lower()

            def _toks_of(side: str) -> set:
                toks = {t for t in re.split(r"[\s,.&'-]+", side)
                        if ((len(t) >= 4) or (len(t) == 1 and t.isalpha()))
                        and t not in _ADDR_GENERIC and not t.isdigit()}
                toks |= {re.sub(r"(\d+)(?:st|nd|rd|th)$", r"\1", t)
                         for t in list(toks)
                         if re.fullmatch(r"\d+(?:st|nd|rd|th)", t)}
                return toks

            typed = bool(re.search(
                r"\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|place|pl|"
                r"lane|ln|parkway|pkwy|highway|hwy|court|ct|terrace|ter|way)\b", core))
            if typed:
                # street query: the heard street must match the returned ROAD
                # component, not the locality half of the display name -
                # 'Monticello 4 Road' fuzzy-matched a house on FORESTBURGH
                # Road because 'monticello' appears as the VILLAGE (real
                # dispatch: '2 Marcel Four Road', Eldred; bad post 9/28 7:38
                # AM). And EVERY rare token of one side must hit - 'Israel
                # Ocean Parkway' passed on 'ocean' alone (9/28 12:46 PM).
                road = " ".join(str(ad.get(k) or "") for k in
                                ("road", "pedestrian", "footway", "residential",
                                 "cycleway", "path")).lower()
                if not road.strip():
                    logging.info("geocode: rejected no-road hit: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
                ok = False
                for side in _street_sides(core):
                    if _side_verifies(side, road):
                        ok = True
                        break
                    if not _street_token_groups(side) and side and side in road:
                        ok = True
                        break
                if not ok:
                    logging.info("geocode: rejected wrong-road hit: %s -> %s (road: %s)",
                                 q, disp, road)
                    await asyncio.sleep(1.1)
                    continue
            else:
                qtoks = _toks_of(core)
                if not qtoks:
                    if len(core.split()) <= 2 or core not in disp.lower():
                        logging.info("geocode: rejected generic-street hit: %s -> %s", q, disp)
                        await asyncio.sleep(1.1)
                        continue
                elif not any(_tok_hit(t, disp.lower()) for t in qtoks):
                    logging.info("geocode: rejected wrong-street hit: %s -> %s", q, disp)
                    await asyncio.sleep(1.1)
                    continue
            county = str(ad.get("county", ""))
            locality = str(ad.get("village") or ad.get("town") or ad.get("city")
                           or ad.get("hamlet") or ad.get("borough") or "")
            # Nominatim sometimes reports NYC roads with city="New York"
            # even when county=Queens. The county is the borough evidence.
            if "hatzal" in p or "hatzol" in p:
                locality = {"Kings County": "Brooklyn", "Queens County": "Queens",
                            "New York County": "Manhattan", "Bronx County": "Bronx",
                            "Richmond County": "Staten Island"}.get(county_name, locality)
            if "fdny" in p:
                requested_boro = addr.split(",")[1].strip().lower() if "," in addr else ""
                county_expected = {"brooklyn": "Kings", "queens": "Queens",
                                   "manhattan": "New York", "bronx": "Bronx",
                                   "staten island": "Richmond"}.get(requested_boro)
                if not county_expected or (county_expected not in county_name and
                    requested_boro not in str(ad.get("borough", "")).lower()):
                    continue
                locality = requested_boro.title()
            if "sullivan" in p and "Sullivan" not in county_name:
                continue
            # Explicit dispatch locality wins over a fuzzy same-road hit in
            # another city. This check is intentionally stricter for Bergen.
            requested_area = addr.split(",")[1].strip() if "," in addr else ""
            if ("hatzal" in p or "hatzol" in p) and requested_area:
                location_names = " ".join(str(ad.get(k) or "") for k in
                                          ("city", "town", "village", "hamlet", "borough", "suburb"))
                if addr.upper().endswith(", NJ") and requested_area.lower() not in location_names.lower():
                    continue
                if requested_area.lower() in ("brooklyn", "queens", "manhattan", "bronx", "staten island"):
                    county_expected = {"brooklyn": "Kings", "queens": "Queens",
                                       "manhattan": "New York", "bronx": "Bronx",
                                       "staten island": "Richmond"}[requested_area.lower()]
                    if county_expected not in county_name and requested_area.lower() not in location_names.lower():
                        continue
                if requested_area.lower() == "riverdale" and "Bronx" not in county_name:
                    continue
                if requested_area.lower() in ("rockland", "monsey"):
                    continue
                # For a named small NY locality, a permitted county alone is
                # not proof: "Corbett" must not become Franklin Square.
                # Only use a normalized exact town/hamlet token, not a
                # substring in an unrelated administrative label.
                known_boroughs = ("brooklyn", "queens", "manhattan", "bronx",
                                  "staten island", "riverdale", "new york")
                if state in ("New York", "NY") and requested_area.lower() not in known_boroughs:
                    names = [str(ad.get(k) or "").lower() for k in
                             ("city", "town", "village", "hamlet", "suburb")]
                    normalized = [re.sub(r"^(?:village|town|city|hamlet) of\s+", "", x).strip()
                                  for x in names if x]
                    if requested_area.lower() not in normalized:
                        continue
            lat = lon = None
            try:
                lat, lon = float(res[0].get("lat")), float(res[0].get("lon"))
            except (TypeError, ValueError):
                pass
            return True, ("Sullivan" in county or "Sullivan County" in disp), disp, lat, lon, locality
        await asyncio.sleep(1.1)  # nominatim 1 req/s
    return False, False, "", None, None, ""


_OVERPASS_EPS = ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter")


async def _intersection_point(address: str, cross: str) -> tuple:
    """Bare-street verification: the heard street truly crosses a spoken cross
    street (shared OSM way node) -> (lat, lon) of a shared node, else
    (None, None). '15th & 16th Avenue' shares its suffix with the bare side."""
    street = re.sub(r"[,.;].*$", "", address).strip()
    parts = [p.strip() for p in (cross or "").split("&", 1) if p.strip()]
    if not street or not parts:
        return None, None
    _T = r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln|Parkway|Pkwy|Court|Ct|Terrace|Ter)"
    # A dispatcher may omit the first suffix ("Coleridge and Hampton Avenue").
    # Try plausible typed variants; verify by an ACTUAL shared OSM node,
    # rather than trusting a fuzzy hit on the second street alone.
    alt = []
    for p in ([street] + parts if "&" not in street else street.split("&", 1)):
        p = p.strip()
        # OSM uses full street types; the FDNY parser often abbreviates them.
        p = re.sub(r"\b(St|Ave|Rd|Blvd|Dr|Pl|Ln|Pkwy|Ct|Ter)$",
                   lambda m: {"st":"Street", "ave":"Avenue", "rd":"Road",
                              "blvd":"Boulevard", "dr":"Drive", "pl":"Place",
                              "ln":"Lane", "pkwy":"Parkway", "ct":"Court",
                              "ter":"Terrace"}[m.group(1).lower()], p, flags=re.I)
        if re.search(rf"\b{_T}\b", p, re.I):
            alt.append([p])
        else:
            alt.append([f"{p} {suffix}" for suffix in
                        ("Street", "Avenue", "Road", "Boulevard", "Place",
                         "Drive", "Court", "Terrace", "Lane")])
    names = list(dict.fromkeys([x for group in alt for x in group]))
    pat = "^(" + "|".join(re.escape(n) for n in names) + ")$"
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}
    # The old Brooklyn-only bbox silently rejected Fair Lawn and Queens.
    # Use the spoken region to search the appropriate map; a NJ candidate
    # remains subject to Bergen County verification by the address geocoder.
    area = address.lower()
    bbox = ("40.75,-74.30,41.13,-73.87" if area.endswith(", nj") else
            "41.35,-75.10,42.00,-74.25" if "sullivan" in area or any(
                n in area for n in ("monticello", "fallsburg", "woodridge", "liberty")) else
            "40.48,-74.26,40.94,-73.70")
    q = f'[out:json][timeout:15];way["name"~"{pat}",i]({bbox});out geom;'
    data = None
    for ep in _OVERPASS_EPS:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(ep, data={"data": q}, headers=hdrs,
                                  timeout=aiohttp.ClientTimeout(total=18)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    break
        except Exception:  # noqa: BLE001
            continue
    if data is None:
        return None, None
    nodes: dict = {}
    for el in data.get("elements") or []:
        nm = (el.get("tags") or {}).get("name", "").strip().lower()
        for g in el.get("geometry") or []:
            nodes.setdefault(nm, {})[(round(g.get("lat", 0), 6),
                                      round(g.get("lon", 0), 6))] = (g.get("lat"), g.get("lon"))
    if "&" in street:
        # Address itself is the intersection: both sides must meet spatially.
        for left in alt[0]:
            own = nodes.get(left.strip().lower()) or {}
            for right in alt[1]:
                other = nodes.get(right.strip().lower()) or {}
                shared = set(own) & set(other)
                if shared:
                    return own[sorted(shared)[0]]
                # OSM splits crossing ways at independently rounded nodes on
                # map exports; tight ~25m snap is acceptable when map names
                # identify both roads, never one road alone.
                for a in own.values():
                    for z in other.values():
                        if abs(a[0] - z[0]) < 0.00017 and abs(a[1] - z[1]) < 0.00023:
                            return ((a[0]+z[0])/2, (a[1]+z[1])/2)
        return None, None
    own = nodes.get(street.lower()) or {}
    if not own:
        return None, None
    for p in names[1:]:
        shared = set(own) & set(nodes.get(p.lower()) or {})
        if shared:
            return own[sorted(shared)[0]]
    return None, None

async def _correct_street_via_crosses(heard_addr: str, cross: str) -> str:
    """User rule 9/28: when the heard street can't be confirmed but the cross
    streets are known, the real street is the one that truly crosses BOTH -
    fuzzy-match its map name against the heard name ('4-0 Haywood' + crosses
    Bedford/Wythe -> '40 Heyward Street'). Returns the corrected address, or
    '' when the intersection evidence doesn't pin it (keep 'not confirmed')."""
    import difflib
    parts = [p.strip() for p in (cross or "").split("&", 1)]
    if len(parts) != 2 or not all(parts):
        return ""
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}

    async def _ov(q: str, timeout: int = 15):
        for ep in _OVERPASS_EPS:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(ep, data={"data": q}, headers=hdrs,
                                      timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                        if r.status != 200:
                            continue
                        return await r.json()
            except Exception:  # noqa: BLE001
                continue
        return None

    heard_core = re.sub(r"^\s*\d+(?:-\d+)?[A-Za-z]?\s+", "", heard_addr)
    heard_core = re.sub(r"[,.;].*$", "", heard_core).strip().lower()
    if not heard_core:
        return ""
    pat = "^(" + "|".join(re.escape(p) for p in parts) + ")$"
    d1 = await _ov(f'[out:json][timeout:15];way["name"~"{pat}",i]'
                   f'(40.55,-74.06,40.75,-73.85);out geom;')
    cross_nodes = []
    for want in parts:
        nodes = set()
        for el in (d1 or {}).get("elements") or []:
            nm = (el.get("tags") or {}).get("name", "").strip().lower()
            if nm != want.lower():
                continue
            for g in el.get("geometry") or []:
                nodes.add((round(g.get("lat", 0), 6), round(g.get("lon", 0), 6)))
        if not nodes:
            return ""
        cross_nodes.append(nodes)
    allpts = [p for ns in cross_nodes for p in ns]
    la = [p[0] for p in allpts]
    lo = [p[1] for p in allpts]
    bbox = f"{min(la)-0.008},{min(lo)-0.008},{max(la)+0.008},{max(lo)+0.008}"
    d2 = await _ov(f'[out:json][timeout:20];way[highway][name]({bbox});out geom;',
                   timeout=24)
    best = (0.0, "")
    for el in (d2 or {}).get("elements") or []:
        nm = (el.get("tags") or {}).get("name", "").strip()
        if not nm or nm.lower() in (parts[0].lower(), parts[1].lower()):
            continue
        nset = {(round(g.get("lat", 0), 6), round(g.get("lon", 0), 6))
                for g in el.get("geometry") or []}
        if not nset or any(not (nset & ns) for ns in cross_nodes):
            continue  # must truly cross BOTH cross streets
        score = difflib.SequenceMatcher(None, heard_core, nm.lower()).ratio()
        if nm.lower()[:1] == heard_core[:1] and score > best[0]:
            best = (score, nm)
    if best[0] < 0.70 or not best[1]:
        logging.info("cross-correction: no street pinning '%s' via [%s] (best %.2f)",
                     heard_addr, cross, best[0])
        return ""
    tok = heard_addr.strip().split(" ", 1)[0]
    if re.fullmatch(r"\d+-\d+", tok):
        num = tok.replace("-", "")  # whisper '4-0' = '40'
    elif re.fullmatch(r"\d+[A-Za-z]?", tok):
        num = tok
    else:
        num = ""
    mtail = re.search(r",\s*(.*)$", heard_addr)
    corrected = (f"{num} " if num else "") + best[1] + (", " + mtail.group(1) if mtail else "")
    logging.info("cross-correction candidate: '%s' + [%s] -> '%s' (score %.2f)",
                 heard_addr, cross, corrected, best[0])
    return corrected


async def _cross_streets(lat: float, lon: float, address: str) -> tuple:
    """Cross streets via Overpass (free, keyless): ways sharing a node with the
    job's own street truly cross it. Returns (crosses, exact) - ('A & B', True),
    or ('A & B', False) when falling back to nearest streets, or (None, False)."""
    import math
    q = (f'[out:json][timeout:15];way(around:250,{lat},{lon})'
         f'[highway][name];out tags geom;')
    hdrs = {"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"}
    data = None
    for attempt in (1, 2):  # one retry pass: Overpass rate-limits bursts
        for endpoint in _OVERPASS_EPS:
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
            if data is not None:
                break
        if data is not None:
            break
        await asyncio.sleep(3)
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
    eps = _OVERPASS_EPS

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


BOX_CACHE_FILE = SEG_DIR / "box_cache.json"


def _load_box_cache() -> dict:
    try:
        return json.loads(BOX_CACHE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_box_cache(c: dict) -> None:
    try:
        BOX_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOX_CACHE_FILE.write_text(json.dumps(c))
    except Exception:  # noqa: BLE001
        pass


_SOCRATA_BOX = "https://data.cityofnewyork.us/resource/v57i-gtxb.json"
_BORO_PREFIX = {"B": "Brooklyn", "M": "Manhattan", "Q": "Queens",
                "X": "Bronx", "R": "Staten Island"}


async def _box_lookup_socrata(box4: str) -> list:
    """FDNY box -> [(location, borough), ...] from the NYC Open Data
    'In-Service Alarm Box Locations' dataset (v57i-gtxb). Numbering verified
    identical to fdnewyork dispatch boxes (B2393='AVENUE M & E 84 ST')."""
    codes = ",".join(f"'{p}{box4}'" for p in _BORO_PREFIX)
    url = (f"{_SOCRATA_BOX}?$select=borobox,location&$where=borobox in({codes})"
           f"&$limit=10")
    rows: list = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent": "fdny-slim/1.0"},
                             timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
        for rec in data:
            code = rec.get("borobox") or ""
            loc = (rec.get("location") or "").strip()
            boro = _BORO_PREFIX.get(code[:1], "")
            if loc and boro:
                rows.append((loc, boro))
    except Exception as e:  # noqa: BLE001
        logging.warning("socrata box lookup failed for %s: %s", box4, e)
        return []
    return rows


async def _nearest_box(lat: float, lon: float, borough: str = "") -> tuple:
    """Address -> closest FDNY box (user rule 9/28: no heard box -> look up
    the closest box to the address). Radius-ordered Socrata query; returns
    (box_digits, location, distance_m) or (None, None, None)."""
    import urllib.parse
    boro_filter = ""
    if borough and borough.lower() in ("brooklyn", "queens", "manhattan", "bronx", "staten island"):
        boro_filter = f" AND borough='{borough.title()}'"
    where = (f"within_circle(location_point,{lat},{lon},500){boro_filter}")
    order = f"distance_in_meters(location_point,'POINT({lon} {lat})')"
    url = (f"{_SOCRATA_BOX}?$select=borobox,location"
           f"&$where={urllib.parse.quote(where)}"
           f"&$order={urllib.parse.quote(order)}&$limit=1")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"User-Agent": "fdny-slim/1.0"},
                             timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status != 200:
                    return None, None, None
                data = await r.json()
        if data:
            code = data[0].get("borobox") or ""
            return code[1:], (data[0].get("location") or "").strip(), None
    except Exception as e:  # noqa: BLE001
        logging.warning("nearest box lookup failed: %s", e)
    return None, None, None


_APP_BOX_URL = "https://fdny.app.appery.io/assets/js/boxNumberSearch.js"
_APP_BOX_DATA = None
_APP_BOX_FETCHED = 0.0


def _app_box_parse(js: str) -> dict:
    """Read-only lookup of the public app's current box data; no redistribution.

    Dataset has borough-prefixed numbers, so B2862 and X2862 are distinct.
    """
    rows = {}
    for prefix, box, loc in re.findall(
            r'\[\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*"([BMQXR])(\d{4}) - ([^"]+)"\s*\]', js):
        if prefix in _BORO_PREFIX and loc.strip():
            rows.setdefault(box, []).append((loc.strip(), _BORO_PREFIX[prefix]))
    return rows


async def _box_lookup_app(box4: str) -> list:
    global _APP_BOX_DATA, _APP_BOX_FETCHED
    if _APP_BOX_DATA is None or time.time() - _APP_BOX_FETCHED > 86400:
        _APP_BOX_FETCHED = time.time()  # failure backoff; do not stall each incident
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(_APP_BOX_URL, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        js = await r.text()
                        parsed = _app_box_parse(js)
                        if len(parsed) > 8000:
                            _APP_BOX_DATA, _APP_BOX_FETCHED = parsed, time.time()
        except Exception as e:  # noqa: BLE001
            logging.warning("app box lookup unavailable: %s", e)
    return (_APP_BOX_DATA or {}).get(box4, [])


def _box_loc_agrees(left: str, right: str) -> bool:
    # Require a named/numbered road side after normalizing abbreviation and
    # ordinal variants; generic words like STREET or AVENUE are insufficient.
    def roads(loc):
        loc = loc.lower().replace("&", " at ").replace(" and ", " at ")
        loc = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", loc)
        loc = re.sub(r"\bavenue\b", "ave", loc)
        loc = re.sub(r"\bstreet\b", "st", loc)
        loc = re.sub(r"\broad\b", "rd", loc)
        return {re.sub(r"\s+", " ", p.strip()) for p in re.split(r"\s+at\s+", loc)
                if len(p.strip()) >= 5}
    return bool(roads(left) & roads(right))


async def _box_lookup(box4: str) -> list:
    """NYC city dataset first; app fills gaps; fdnewyork preserves boxes
    absent in both. Conflicting city/app locations never silently replace one
    another. The caller's address/cross checks remain the posting gate.
    """
    import urllib.parse
    import urllib.request
    cache = _load_box_cache()
    city = await _box_lookup_socrata(box4)
    # App data is a supplementary source, not a new sole authority.
    app = await _box_lookup_app(box4)
    if city:
        for loc, borough in city:
            peers = [l for l, b in app if b == borough]
            if peers and not any(_box_loc_agrees(loc, peer) for peer in peers):
                logging.warning("box %s city/app disagreement in %s: city=%s app=%s",
                                box4, borough, loc, peers)
                ops_log(f"box {box4} source disagreement in {borough}: city {loc}; app {peers}")
        covered = {borough for _, borough in city}
        supplemental = [(loc, borough) for loc, borough in app if borough not in covered]
        # A positive legacy record neither city nor app carries still matters
        # (Brooklyn 0808). Do not introduce a 12-second lookup on every city hit:
        # only a populated prior cache can add an absent-borough row here.
        legacy = [tuple(r) for r in cache.get(box4, [])]
        extra = [(loc, borough) for loc, borough in legacy
                 if borough not in covered and borough not in {b for _, b in supplemental}]
        return city + supplemental + extra
    if box4 in cache and cache[box4]:
        # Legacy fdnewyork lookup can have records neither source carries,
        # including Brooklyn 0808. Retain it before supplementing from app.
        legacy = [tuple(r) for r in cache[box4]]
    else:
        legacy = []
        try:
            data = urllib.parse.urlencode({"action": "Save Form Data", "id": box4}).encode()
            req = urllib.request.Request(
                "https://www.fdnewyork.com/getbox.asp", data=data,
                headers={"User-Agent": "fdny-slim/1.0 (dispatch monitor; low volume)"})
            def _fetch():
                with urllib.request.urlopen(req, timeout=12) as r:
                    return r.read().decode("utf-8", "replace")
            html_txt = await asyncio.to_thread(_fetch)
            for m in re.finditer(
                    r"<td class=\w+>(\d{4})</td><td class=\w+>([^<]+)</td><td class=\w+>\s*([^<]+?)\s*</td>",
                    html_txt):
                if m.group(1) == box4:
                    legacy.append((m.group(2).strip(), m.group(3).strip()))
        except Exception as e:  # noqa: BLE001
            logging.warning("box lookup failed for %s: %s", box4, e)
        if legacy:
            cache[box4] = legacy
            _save_box_cache(cache)
    if legacy and app:
        for loc, borough in legacy:
            peers = [l for l, b in app if b == borough]
            if peers and not any(_box_loc_agrees(loc, peer) for peer in peers):
                logging.warning("box %s legacy/app disagreement in %s: %s / %s",
                                box4, borough, loc, peers)
                ops_log(f"box {box4} source disagreement in {borough}: legacy {loc}; app {peers}")
    rows = list(legacy)
    # Fill only absent borough rows. A disagreement in one borough does not
    # manufacture a second box location there.
    covered = {borough for _, borough in rows}
    rows.extend((loc, borough) for loc, borough in app if borough not in covered)
    return rows


def _box_address_correction(heard_addr: str, rows: list) -> str:
    """Box-supported address correction for the whisper ordinal digit-drop:
    heard '1238 East 4th Street' (or bare 'East 4th Street'), box row side
    'E 84 ST' -> 'East 84th Street, Brooklyn, NY' when the shapes line up:
    same direction prefix, same street type, and the heard ordinal's digits
    are a strict suffix of the row ordinal's digits ('4' in '84'). Returns ''
    when no row side supports a correction - never guesses."""
    _DIR = {"e": "East", "w": "West", "n": "North", "s": "South",
            "east": "East", "west": "West", "north": "North", "south": "South"}
    m = re.match(r"^\s*(\d+\s+)?(?:(east|west|north|south|e|w|n|s)\s+)?"
                 r"(\d+)(?:st|nd|rd|th)?\s+(street|st|avenue|ave|road|rd|boulevard|blvd)",
                 heard_addr, re.I)
    if not m:
        return ""
    house = (m.group(1) or "").strip()
    heard_dir = (m.group(2) or "").lower()
    heard_num = m.group(3)
    heard_type = m.group(4).lower()
    heard_type = {"st": "street", "ave": "avenue", "rd": "road", "blvd": "boulevard"}.get(
        heard_type, heard_type)
    tail = ""
    mt = re.search(r",\s*(.*)$", heard_addr)
    if mt:
        tail = ", " + mt.group(1)
    for loc, _borough in rows:
        for side in re.split(r"\s+at\s+|&", loc):
            sm = re.match(r"^\s*(?:(east|west|north|south|e|w|n|s)\s+)?"
                          r"(\d+)(?:st|nd|rd|th)?\s*(street|st|avenue|ave|road|rd|boulevard|blvd)?",
                          side, re.I)
            if not sm:
                continue
            row_dir = (sm.group(1) or "").lower()
            row_num = sm.group(2)
            row_type = (sm.group(3) or heard_type).lower()
            row_type = {"st": "street", "ave": "avenue", "rd": "road",
                        "blvd": "boulevard"}.get(row_type, row_type)
            _FULL = {"e": "east", "w": "west", "n": "north", "s": "south"}
            if (_FULL.get(heard_dir, heard_dir) != _FULL.get(row_dir, row_dir)
                    or heard_type != row_type):
                continue
            if len(row_num) > len(heard_num) and row_num.endswith(heard_num):
                direction = _DIR.get(row_dir, "")
                n = int(row_num)
                suf = ("th" if 10 <= n % 100 <= 20
                       else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))
                type_disp = {"street": "Street", "avenue": "Avenue", "road": "Road",
                             "boulevard": "Boulevard"}.get(row_type, row_type.title())
                street = f"{direction + ' ' if direction else ''}{row_num}{suf} {type_disp}"
                corrected = f"{house + ' ' if house else ''}{street}{tail}"
                logging.info("box address correction: '%s' -> '%s' (row '%s')",
                             heard_addr, corrected, loc)
                return corrected
    return ""


def _box_row_matches_address_and_cross(location: str, address: str, crosses: str) -> bool:
    """Box row 'SURF AVE at W 25 ST' corroborates the spoken W 25th
    address + Surf cross. Ordinal '25th' and source '25' are same street;
    'W' and 'West' are the same direction. Never compare mere city tokens.
    """
    def canon(street: str) -> str:
        t = street.lower().strip()
        t = re.sub(r"\bwest\b", "w", t)
        t = re.sub(r"\beast\b", "e", t)
        t = re.sub(r"\bnorth\b", "n", t)
        t = re.sub(r"\bsouth\b", "s", t)
        t = re.sub(r"\bavenue\b", "ave", t)
        t = re.sub(r"\bstreet\b", "st", t)
        t = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", t)
        return re.sub(r"\s+", " ", t).strip()
    row_sides = [canon(x) for x in re.split(r"\s+at\s+|\s*&\s*", location, flags=re.I)]
    own = canon(re.sub(r"^\d+\s+", "", address.split(",", 1)[0]))
    cross_sides = [canon(x) for x in re.split(r"\s*&\s*", crosses) if x.strip()]
    return bool(own and cross_sides and own in row_sides and any(x in row_sides for x in cross_sides))


def _heard_box(excerpt: str) -> str | None:
    # user ruling 9/28 13:36: 'class 3 2584' digits are an ALARM readout, not a
    # box ('it can come over as a class 3... but the box is wrong') - only a
    # spoken 'box NNNN' counts as a heard box
    m = re.search(r"\bbox\s+(\d{1,4})\b", excerpt or "", re.I)
    return m.group(1).zfill(4) if m else None


RECENT_FILE = Path(os.environ.get("RECENT_FILE", "./segments/recent_posts.json"))
_INCIDENT_DEDUP_SEC = 600
_ADDR_GENERIC = {"street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd",
                 "place", "pl", "drive", "dr", "lane", "ln", "parkway", "pkwy", "court",
                 "ct", "east", "west", "north", "south", "ny", "brooklyn", "new", "york",
                 "queens", "manhattan", "bronx", "and", "the", "between", "county", "co", "sullivan", "nassau", "bergen", "kings", "richmond", "thompson", "monticello", "parksville", "cedarhurst", "fallsburg", "loch", "sheldrake"}


def _tok_hit(tok: str, haystack: str) -> bool:
    """Token match on word boundaries: single-letter/short street tokens
    ('m' from 'Avenue M') must not substring-match inside other words
    ('Manhattan Ave' is not 'Avenue M')."""
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])",
                          haystack))


def _rare_tokens(addr: str) -> set:
    return {t for t in re.split(r"[\s,.&'-]+", addr.lower())
            if len(t) >= 4 and t not in _ADDR_GENERIC and not t.isdigit()}


def _street_core(addr: str) -> str:
    """Normalized primary street: '535 4th Ave, Brooklyn' -> '4th ave';
    '4TH AVE at 13 ST' -> '4th ave'."""
    s = re.split(r"\s+at\s+|,|&", addr.lower())[0]
    s = re.sub(r"^\s*\d+(?:[A-Za-z])?\s+", "", s).strip()
    s = re.sub(r"\b(avenue|ave)\b", "ave", s)
    s = re.sub(r"\b(street|st)\b", "st", s)
    s = re.sub(r"\b(road|rd)\b", "rd", s)
    s = re.sub(r"\b(boulevard|blvd)\b", "blvd", s)
    return re.sub(r"\s+", " ", s)


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


async def _held_recording(clip_name: str | None) -> str:
    """Off-site audio for new held jobs; a failure never affects posting gates."""
    if not clip_name:
        return ""
    try:
        ogg = await asyncio.to_thread(_ensure_ogg, clip_name)
        if ogg:
            path = ARCHIVE_DIR / ogg
            if path.stat().st_size > 100:
                url = await _uguu_upload(path)
                if url:
                    # Uguu's success response alone is insufficient: the
                    # hosting edge has occasionally served a zero-byte file.
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers={"Range": "bytes=0-1023"},
                                               timeout=aiohttp.ClientTimeout(total=8)) as rsp:
                            head = await rsp.read()
                            if rsp.status in (200, 206) and head.startswith(b"OggS"):
                                return url
                    logging.warning("held recording archive returned invalid audio: %s", url)
    except Exception as e:
        logging.warning("held recording upload unavailable: %s", e)
    return ""


_REVIEW_SKIP = {"feed muted", "dup incident", "bare box", "Rockland dispatch",
                "outside Sullivan Co"}


def _held_review_text(profile: str, hit: dict) -> str:
    """Explain only the actual parsed data and uncertainty, never invent a read."""
    source = {"fdny": "FDNY", "sullivan": "Sullivan",
              "hatzolah": "Hatzalah", "hatzalah": "Hatzalah"}.get(
                  profile.removeprefix("zello-"), profile)
    address = (hit.get("address") or "").strip()
    if profile.removeprefix("zello-") == "sullivan":
        # A held job has no confirmed locality. Strip both the generic county
        # suffix and any ASR-guessed town; keep only the road actually heard.
        address = address.split(",", 1)[0].strip()
    nature = (hit.get("nature") or "").strip()
    reason = (hit.get("hold_reason") or "").strip()
    heard = (f"The system parsed {nature} at {address}." if nature and address else
             f"The system parsed the location as {address}, but no complaint." if address else
             f"The system parsed the complaint as {nature}, but no location." if nature else
             "The system could not parse a complaint or location.")
    if reason == "no nature":
        uncertainty = "It could not identify a clear complaint from this recording, so it held the alert."
        question = "What complaint does the dispatcher actually say, and is the parsed address right?"
    elif reason == "ambiguous default borough":
        uncertainty = "The recording did not establish the borough clearly enough to use the parsed address."
        question = "Which borough and exact address does the dispatcher say?"
    elif reason == "FDNY numbered cross street needs an independent audio check":
        uncertainty = "A numbered crossing street could have been transcribed with the wrong digits."
        question = "What are the crossing street's exact number and name in the audio?"
    elif reason in ("no verified location", "unconfirmed, no box",
                    "map did not confirm the exact FDNY house and street"):
        uncertainty = "The exact house and street could not be confirmed against the map."
        question = "What house number and street does the dispatcher say?"
    elif reason.startswith("spoken cross unverified:"):
        cross = reason.partition(":")[2].strip()
        uncertainty = f"The heard crossing street {cross} could not be verified." if cross else "The heard crossing street could not be verified."
        question = "Which crossing street is actually said, and is this one location?"
    elif reason.startswith("FDNY dispatch gave a numbered building"):
        uncertainty = "The numbered building heard in the audio was missing from the parsed address."
        question = "Which number belongs to the building, rather than a crossing street or radio ID?"
    else:
        from status import plain_reason
        uncertainty = plain_reason(reason, address)
        if not uncertainty or uncertainty == reason:
            uncertainty = "The location or complaint could not be checked well enough for a main-group alert."
        question = "What does the dispatcher actually say for the complaint and exact location?"
    return f"*Held {source} call - please check the recording*\n{heard} {uncertainty} {question}"


async def _post_held_review(profile: str, hit: dict, clip_name: str | None) -> None:
    """After owner format approval, send the review and the actual audio to ops."""
    if os.environ.get("HELD_REVIEW_ENABLED", "0") != "1":
        return
    reason = (hit.get("hold_reason") or "").strip()
    if not reason or reason in _REVIEW_SKIP:
        return
    if not clip_name or not alert_waha._ops_chat():
        logging.warning("held review has no clip or ops destination: %s", reason)
        return
    ogg = await asyncio.to_thread(_ensure_ogg, clip_name)
    if not ogg or not (ARCHIVE_DIR / ogg).exists() or (ARCHIVE_DIR / ogg).stat().st_size <= 100:
        logging.warning("held review has no usable audio: %s", clip_name)
        return
    # Send text before voice, but only to the known ops destination. The
    # service's /audio route supplies the bytes to WAHA right away; unlike an
    # Uguu link, its address is not the delivered artifact.
    chat = alert_waha._ops_chat()
    text = _held_review_text(profile, hit)
    if await alert_waha.send_text(text, chat_id=chat):
        base = os.environ.get("RENDER_EXTERNAL_URL", "https://fdny-slim.onrender.com").rstrip("/")
        if not await alert_waha.send_voice(f"{base}/audio/{ogg}", chat_id=chat):
            logging.warning("held review audio send failed: %s", clip_name)
    else:
        logging.warning("held review text send failed: %s", clip_name)


async def _hatzalah_brooklyn_grid_corridor(hit: dict) -> tuple | None:
    """One spoken Boro Park avenue between consecutive numbered streets.

    The stream supplies Brooklyn context, but map geometry still has to prove
    both roads cross that avenue in Kings County. No house or cross is inferred.
    """
    if hit.get("source", "").removeprefix("zello-") not in ("hatzolah", "hatzalah"):
        return None
    text = hit.get("excerpt") or ""
    if re.search(r"\b(?:queens|bronx|manhattan|staten island|nassau|rockland|"
                 r"sullivan|new jersey|nj|five towns|long island)\b", text, re.I):
        return None
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th) (?:Ave|Avenue) between "
                     r"(\d{1,3})(?:st|nd|rd|th) & (\d{1,3})(?:st|nd|rd|th) "
                     r"(?:St|Street), Brooklyn, NY", hit.get("address") or "", re.I)
    if not m:
        return None
    avenue, first, second = map(int, m.groups())
    if not (1 <= avenue <= 25 and 35 <= first <= 65 and second == first + 1):
        return None
    from detect import _ordinal_street_num
    road = f"{_ordinal_street_num(avenue)} Avenue, Brooklyn, NY"
    try:
        points = await asyncio.gather(*(
            asyncio.wait_for(_intersection_point(road, f"{_ordinal_street_num(st)} Street"), timeout=18)
            for st in (first, second)))
    except Exception:
        return None
    if any(lat is None or lon is None for lat, lon in points):
        return None
    import math
    gap = math.hypot((points[0][0] - points[1][0]) * 111000,
                     (points[0][1] - points[1][1]) * 85000)
    if not 20 <= gap <= 750:
        return None
    # Reverse checks attach both independently found junctions to Kings County,
    # instead of trusting the parsed Brooklyn suffix or a matching road elsewhere.
    try:
        async with aiohttp.ClientSession() as ses:
            async def kings(point):
                async with ses.get("https://nominatim.openstreetmap.org/reverse",
                                   params={"lat": point[0], "lon": point[1],
                                           "format": "json", "addressdetails": 1},
                                   headers={"User-Agent": "fdny-slim/1.0 (dispatch monitor)"},
                                   timeout=aiohttp.ClientTimeout(total=6)) as rsp:
                    data = await rsp.json() if rsp.status == 200 else {}
                area = data.get("address") or {}
                return ("Kings" in (area.get("county") or "") or
                        area.get("city_district") == "Kings County") and area.get("state") == "New York"
            if not all(await asyncio.gather(*(kings(pt) for pt in points))):
                return None
    except Exception:
        return None
    return ((points[0][0] + points[1][0]) / 2,
            (points[0][1] + points[1][1]) / 2)


async def verify_and_send(profile: str, hit: dict, stats, clip_name: str | None = None,
                            fresh_ts: float | None = None,
                            audio_ts: float | None = None, spoken_time: str = "",
                            send_lock: asyncio.Lock | None = None,
                            correction_guard: CorrectionGuard | None = None,
                            source_call: dict | None = None) -> str:
    """User's posting rules (9/28): verified addresses only; Sullivan feed posts
    only Sullivan-County-verified addresses; unverifiable posts marked not confirmed.
    Returns 'sent' | 'queued' | 'suppressed'."""
    now = time.time()
    verify_started = time.monotonic()
    if profile in control.muted_feeds():
        logging.info("[%s] suppressed (feed muted): %s @ %s", profile, hit["nature"], hit["address"])
        stats.event(profile, f"suppressed (feed muted): {hit['nature']} @ {hit['address']}")
        ops_log(f"suppressed (feed muted): {hit['nature']} @ {hit['address']}")
        hit["hold_reason"] = "feed muted"
        return "suppressed"
    if fresh_ts:
        fresh_limit = FRESH_FDNY_SEC if profile == "fdny" else FRESH_LIVE_SEC
        age = time.time() - fresh_ts
        if age > fresh_limit:
            logging.info("[%s] suppressed (stale, %.0fm old, limit %dm): %s @ %s",
                         profile, age / 60, fresh_limit / 60, hit["nature"], hit["address"])
            stats.event(profile, f"suppressed (stale, {age / 60:.0f}m old): {hit['nature']} @ {hit['address']}")
            ops_log(f"suppressed (stale, {age / 60:.0f}m old): {hit['nature']} @ {hit['address']}")
            hit["hold_reason"] = f"stale audio ({age / 60:.0f} min)"
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
                hit["hold_reason"] = "dup incident"
                return "suppressed"
    if re.match(r"^FDNY Box \d+", hit["address"]) and not hit.get("box_only"):
        logging.info("[%s] suppressed (bare box, no street address): %s", profile, hit["address"])
        stats.event(profile, f"suppressed (bare box): {hit['address']}")
        ops_log(f"suppressed (bare box): {hit['address']}")
        hit["hold_reason"] = "bare box"
        return "suppressed"
    if not (hit.get("nature") or "").strip():
        logging.info("[%s] suppressed (no discernible nature): %s", profile, hit["address"])
        stats.event(profile, f"Held: Units were talking, but no clear complaint was said. Location heard: {hit['address']}.")
        ops_log(f"Held: Units were talking, but no clear complaint was said. Location heard: {hit['address']}.")
        hit["hold_reason"] = "no nature"
        return "suppressed"
    if profile.lower().startswith(("hatzalah", "zello-hatzalah")) and \
            (hit.get("nature") or "").strip().lower() in control.excluded_natures():
        logging.info("[%s] suppressed (Hatzalah %s excluded): %s", profile, hit.get("nature"), hit["address"])
        stats.event(profile, f"suppressed ({hit.get('nature')} excluded): {hit['address']}")
        ops_log(f"suppressed ({hit.get('nature')} excluded): {hit['address']}")
        hit["hold_reason"] = f"{hit.get('nature')} excluded by controls"
        return "suppressed"
    box_task = None
    if profile == "fdny":
        heard = hit.get("box_heard") or _heard_box(hit.get("excerpt") or "")
        if heard:
            box_task = asyncio.create_task(_box_lookup(heard))
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
    if profile.lower().startswith(("hatzalah", "zello-hatzalah")) and re.search(
            r"\b(?:rockland|monsey|spring valley|new square|suffern|"
            r"haverstraw|garnerville|airmont|chestnut ridge)\b",
            hit.get("excerpt") or "", re.I):
        stats.event(profile, f"suppressed (Rockland dispatch): {hit['address']}")
        hit["hold_reason"] = "Rockland dispatch"
        return "suppressed"
    if profile.lower().removeprefix("zello-") in ("hatzolah", "hatzalah") and hit.get("area_defaulted"):
        import locality_gate
        # A bare NYC pair can name an exact point even if the borough was
        # omitted. Prove both full road names at the same map node, and
        # independently reverse-check the point's borough before using it.
        pair_safe = False
        bare_first = hit["address"].split(",", 1)[0]
        candidate = hit.get("direct_cross_candidate") or ""
        if candidate and not re.match(r"^\d+\s", bare_first) and bare_first.lower().endswith(
                ("street", "avenue", "road", "boulevard", "drive", "place", "lane")):
            try:
                point = await asyncio.wait_for(
                    _intersection_point(hit["address"], candidate), timeout=9)
            except Exception:
                point = (None, None)
            if point[0] is not None:
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as ses:
                        async with ses.get("https://nominatim.openstreetmap.org/reverse",
                                           params={"lat": point[0], "lon": point[1],
                                                   "format": "json", "addressdetails": 1},
                                           headers={"User-Agent": "fdny-slim/1.0 (dispatch monitor)"},
                                           timeout=aiohttp.ClientTimeout(total=6)) as rsp:
                            body = await rsp.json() if rsp.status == 200 else {}
                    area = body.get("address") or {}
                    pair_safe = area.get("city_district") == "Kings County" and area.get("state") == "New York"
                except Exception:
                    pair_safe = False
        grid_point = None
        if not pair_safe:
            grid_point = await _hatzalah_brooklyn_grid_corridor(hit)
        if grid_point is not None:
            hit["verified_brooklyn_grid_point"] = grid_point
            pair_safe = True
        if not pair_safe and not await locality_gate.default_area_safe(hit, hit.get("excerpt") or ""):
            stats.event(profile, f"suppressed (ambiguous default borough): {hit['address']}")
            ops_log(f"suppressed (ambiguous default borough): {hit['address']}")
            hit["hold_reason"] = "ambiguous default borough"
            return "suppressed"
    if profile == "fdny" and re.search(r"\b\d+(?:st|nd|rd|th)\s+Walk,", hit["address"], re.I):
        # A reused overlapping clip may contain a separate numbered street
        # job and a box for THAT job, then repeat a Walk address. Never tie
        # its box to the Walk. A solitary Walk/box disagreement retains the
        # existing warning behavior.
        excerpt = hit.get("excerpt") or ""
        walk_house = re.match(r"^(\d+)\s+", hit["address"])
        others = re.findall(r"\b(\d{1,5})\s+(?:[A-Za-z][A-Za-z'-]*\s+){0,2}"
                            r"(?:Street|St|Avenue|Ave|Road|Rd)\b", excerpt, re.I)
        if walk_house and any(num != walk_house.group(1) for num in others) and hit.get("box_heard"):
            stats.event(profile, f"suppressed (mixed Walk/other address): {hit['address']}")
            ops_log(f"suppressed (mixed Walk/other address): {hit['address']}")
            hit["hold_reason"] = "mixed Walk/other address"
            return "suppressed"
    if profile == "fdny" and hit.get("terminal_street_box_correlated"):
        # A user's specific reading of this garbled dispatch is still gated
        # by independent map and NYC box corroboration before any post.
        box_num = hit.get("box_heard") or ""
        rows = await _box_lookup(box_num) if box_num else []
        exact_row = any(boro == "Brooklyn" and "53 ST" in loc.upper()
                        and "9 AVE" in loc.upper() for loc, boro in rows)
        if not exact_row:
            stats.event(profile, "suppressed (terminal street box mismatch)")
            hit["hold_reason"] = "terminal street box mismatch"
            return "suppressed"
    if profile == "fdny" and hit.get("box_only"):
        # A terminal-ID dispatch with no trustworthy spoken street may use
        # the verified Brooklyn box location as its address anchor. Never
        # invent a house number or let a box from another borough through.
        heard_box = hit.get("box_heard") or ""
        box_rows = await _box_lookup(heard_box) if heard_box else []
        brooklyn_rows = [place for place, boro in box_rows if boro == "Brooklyn"]
        if len(brooklyn_rows) != 1:
            stats.event(profile, f"suppressed (box-only location unverified): {heard_box}")
            hit["hold_reason"] = "box-only location unverified"
            return "suppressed"
        box_place = brooklyn_rows[0]
        sides = [p.strip() for p in re.split(r"\s+at\s+|&", box_place, flags=re.I)]
        if len(sides) != 2 or not all(sides):
            stats.event(profile, f"suppressed (box-only location incomplete): {heard_box}")
            hit["hold_reason"] = "box-only location incomplete"
            return "suppressed"
        # The spoken 8th/9th corridor must corroborate at least one side of
        # the box location. Generic area words don't count as a match.
        said = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", hit.get("cross") or "", flags=re.I)
        listed = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", box_place, flags=re.I)
        if not said or not any(re.search(r"\b" + re.escape(x) + r"\b", listed, re.I)
                               for x in re.findall(r"\b\d{1,2}\b", said)):
            stats.event(profile, f"suppressed (box-only crosses uncorroborated): {heard_box}")
            hit["hold_reason"] = "box-only crosses uncorroborated"
            return "suppressed"
        def box_side_name(raw):
            p = raw.strip().lower()
            p = re.sub(r"\b(\d{1,3})\b", lambda m:
                       str(int(m.group(1))) + ("th" if 11 <= int(m.group(1)) % 100 <= 13
                           else "st" if int(m.group(1)) % 10 == 1
                           else "nd" if int(m.group(1)) % 10 == 2
                           else "rd" if int(m.group(1)) % 10 == 3 else "th"), p)
            p = re.sub(r"\bave\b", "Avenue", p, flags=re.I)
            p = re.sub(r"\bst\b", "Street", p, flags=re.I)
            return p.title().replace("Th ", "th ").replace("St ", "st ").replace("Nd ", "nd ").replace("Rd ", "rd ")
        candidate = f"{box_side_name(sides[0])} & {box_side_name(sides[1])}, Brooklyn, NY"
        lat, lon = await _intersection_point(candidate, box_side_name(sides[1]))
        if lat is None:
            stats.event(profile, f"suppressed (box-only intersection unverified): {heard_box}")
            hit["hold_reason"] = "box-only intersection unverified"
            return "suppressed"
        hit["address"] = candidate
        hit["cross"] = ""
        stats.event(profile, f"box-only verified address from Brooklyn Box {heard_box}: {candidate}")
        verified_label, locality = candidate, "Brooklyn"
    if GEOCODE_VERIFY and not hit.get("box_only"):
        location_check_started = time.monotonic()
        # Intersections require BOTH spoken roads at one point. The ordinary
        # geocoder can otherwise certify the first street only.
        spoken_location = hit["address"].split(",")[0]
        if " & " in spoken_location and not re.match(r"^\d+\s", spoken_location):
            side_a, side_b = (p.strip() for p in spoken_location.split("&", 1))
            lat, lon = await _intersection_point(hit["address"], side_b)
            verified = lat is not None
            # Spatially constrained road-name intersection. If map service
            # is unavailable, verified stays false and alert is suppressed.
            verified_label = hit["address"] if verified else ""
            locality = hit["address"].split(",")[1].strip() if verified and "," in hit["address"] else ""
            # Owner rule: a false spoken corner may still post the primary
            # road, but only if that road independently verifies in the
            # explicitly named area. Never print the false second road or a
            # map-computed substitute. A defaulted locality gets no fallback.
            if not verified and profile.lower().removeprefix("zello-") in ("hatzolah", "hatzalah") \
                    and not hit.get("area_defaulted") and re.search(
                        r"\b(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|"
                        r"Drive|Dr|Place|Pl|Lane|Ln|Parkway|Pkwy|Court|Ct|Terrace|Ter|"
                        r"Broadway)\b$", side_a, re.I):
                primary = f"{side_a}, " + hit["address"].split(",", 1)[1].strip()
                v0, s0, label0, la0, lo0, loc0 = await geocode_verify(primary, profile)
                area0 = hit["address"].split(",")[1].strip()
                if v0 and label0 and re.search(r"\b" + re.escape(area0) + r"\b", label0, re.I):
                    hit["address"] = primary
                    hit["cross"] = ""
                    hit["direct_cross_candidate"] = ""
                    hit["unresolved_spoken_corner_fallback"] = True
                    verified, in_sullivan, verified_label, lat, lon, locality = v0, s0, label0, la0, lo0, loc0
                    stats.event(profile, f"spoken corner unresolved; verified primary road only: {primary}")
        else:
            verified, in_sullivan, verified_label, lat, lon, locality = await geocode_verify(hit["address"], profile)
        # The standard address geocoder cannot parse a bare "between" block.
        # Only the two-junction Kings County check above can certify it.
        if hit.get("verified_brooklyn_grid_point") is not None and not verified:
            lat, lon = hit["verified_brooklyn_grid_point"]
            verified = True
            verified_label = hit["address"]
            locality = "Brooklyn"
        if (verified and locality and profile.lower().startswith(("hatzalah", "zello-hatzalah"))
                and locality.lower() not in ("brooklyn", "queens", "manhattan", "bronx", "new york", "staten island")):
            state_suffix = "NJ" if hit["address"].upper().endswith(", NJ") else "NY"
            fixed = re.sub(r",\s*[^,]+,\s*(?:NY|NJ)$", f", {locality}, {state_suffix}", hit["address"])
            if fixed != hit["address"] and not hit.get("unresolved_spoken_corner_fallback"):
                logging.info("[%s] area corrected by geocode: %s -> %s", profile, hit["address"], fixed)
                stats.event(profile, f"area corrected: {hit['address']} -> {fixed}")
                hit["address"] = fixed
        if profile.lower().startswith(("hatzalah", "zello-hatzalah")):
            # The dispatch explicitly names an excluded chapter. Never let a
            # generic street geocode in Brooklyn override that place name.
            if re.search(r"\b(?:rockland|monsey|spring valley|new square|suffern|"
                         r"haverstraw|garnerville|airmont|chestnut ridge)\b",
                         hit.get("excerpt") or "", re.I):
                stats.event(profile, f"suppressed (Rockland dispatch): {hit['address']}")
                hit["hold_reason"] = "Rockland dispatch"
                return "suppressed"
        if profile == "sullivan" and verified and not in_sullivan:
            logging.info("[%s] suppressed (verified outside Sullivan Co): %s", profile, hit["address"])
            stats.event(profile, f"suppressed (outside Sullivan Co): {hit['nature']} @ {hit['address']}")
            ops_log(f"suppressed (outside Sullivan Co): {hit['nature']} @ {hit['address']}")
            hit["hold_reason"] = "outside Sullivan Co"
            return "suppressed"
        if not verified:
            stats.event(profile, f"unconfirmed address: {hit['address']}")
    if profile == "fdny" and verified and GEOCODE_VERIFY:
        from fdny_borough_gate import exact_numbered_fdny_match
        if not exact_numbered_fdny_match(hit["address"], verified_label):
            reason = "map did not confirm the exact FDNY house and street"
            stats.event(profile, f"Held: {reason}: {hit['address']} (map: {verified_label})")
            ops_log(f"Held: {reason}: {hit['address']} (map: {verified_label})")
            hit["hold_reason"] = reason
            return "suppressed"
    # A directly spoken X and Y pair: keep the verified first street if the
    # map cannot prove the second at a real intersection. The map-verification
    # result controls the printed second side; no fuzzy substitution.
    direct_candidate = (hit.get("direct_cross_candidate") or "").strip()
    direct_pair_verified = False
    if direct_candidate and verified:
        try:
            pair_point = await asyncio.wait_for(
                _intersection_point(hit["address"], direct_candidate), timeout=9)
        except Exception:
            pair_point = (None, None)
        if pair_point[0] is None and profile.lower().removeprefix("zello-") in ("hatzolah", "hatzalah"):
            # One transient map failure may drop a spoken intersection. Never
            # infer it merely from geocoding the first road.
            await asyncio.sleep(0.5)
            try:
                pair_point = await asyncio.wait_for(
                    _intersection_point(hit["address"], direct_candidate), timeout=9)
            except Exception:
                pair_point = (None, None)
        if pair_point[0] is not None:
            hit["address"] = hit["address"].replace(
                hit["address"].split(",", 1)[0],
                f"{hit['address'].split(',', 1)[0]} & {direct_candidate}", 1)
            lat, lon = pair_point
            direct_pair_verified = True
            stats.event(profile, f"spoken intersection map-verified: {hit['address']}")
        else:
            stats.event(profile, f"spoken second street unverified: {direct_candidate}")
    spoken_three = (hit.get("spoken_three_road_crosses") or "").strip()
    if spoken_three:
        # Both crossing roads were said after the primary road. Verify each
        # against that primary, not against one another. If either map check
        # fails, hold instead of substituting a nearby unspoken cross.
        sides = [p.strip() for p in spoken_three.split("&")]
        if not verified or len(sides) != 2:
            hit["hold_reason"] = "spoken crossing roads not verified"
            stats.event(profile, f"suppressed (spoken crosses unverified): {hit['address']}")
            return "suppressed"
        checked = []
        for side in sides:
            try:
                point = await asyncio.wait_for(_intersection_point(hit["address"], side), timeout=9)
            except Exception:
                point = (None, None)
            if point[0] is None:
                hit["hold_reason"] = f"spoken cross unverified: {side}"
                stats.event(profile, f"suppressed (spoken cross unverified): {side}")
                return "suppressed"
            checked.append(point)
        # A single junction cannot be called "between" two distinct roads.
        # The map points must be distinct and within a short corridor.
        import math
        gap_m = math.hypot((checked[0][0] - checked[1][0]) * 111000,
                           (checked[0][1] - checked[1][1]) * 85000)
        if not 20 <= gap_m <= 750:
            hit["hold_reason"] = "spoken crossings not a bounded block"
            stats.event(profile, f"suppressed (spoken crossings geometry): {gap_m:.0f}m")
            return "suppressed"
        stats.event(profile, f"two spoken crosses map-verified: {spoken_three}")
    cross = (hit.get("cross") or "").strip()
    # A single directly spoken FDNY cross is never invented from a box row.
    # Only keep it beside the selected box after a real road intersection
    # independently verifies; failure leaves the box alone.
    spoken_cross = (hit.get("single_spoken_cross") or "").strip() if profile == "fdny" else ""
    spoken_cross_verified = False
    if spoken_cross and verified and lat is not None and lon is not None:
        base_road = re.sub(r"^\s*\d+[A-Za-z-]*\s+", "", hit["address"].split(",")[0])
        try:
            import spoken_cross as crossmap
            spoken_cross_verified = await asyncio.wait_for(
                crossmap.verify(base_road, spoken_cross, lat, lon), timeout=10)
        except Exception:
            spoken_cross_verified = False
        if spoken_cross_verified:
            stats.event(profile, f"spoken cross map-verified: {spoken_cross} at {base_road}")
    if profile == "fdny" and hit.get("class3_house_address") and cross and "&" in cross:
        # For a Class 3 + exact house address, ASR may join one nearby cross
        # with a distant road from another assignment. The house and box are
        # independently verified; omit this unverified cross pair entirely.
        # This leaves established cross behavior for other FDNY calls alone.
        cross = ""
    if " & " in hit["address"].split(",")[0] and (
            cross.lower() == hit["address"].split(",")[0].lower() or
            (direct_pair_verified and cross.lower() == direct_candidate.lower())):
        cross = ""  # the spoken intersection already IS the location line
    if cross and "&" not in cross and lat is not None and lon is not None \
            and verified_label:
        # single spoken cross ('off Woodbine Street') - complete the pair
        # from the map, spoken side first
        comp, _exact = await _cross_streets(lat, lon, hit["address"])
        if comp and _exact:
            spoken = cross.strip().lower()
            other = [p.strip() for p in comp.split("&")
                     if p.strip() and p.strip().lower() != spoken]
            if other:
                cross = f"{cross} & {other[0]}"
                stats.event(profile, f"cross completed from map: {cross}")
    if not cross and not direct_pair_verified and not hit.get("unresolved_spoken_corner_fallback") \
            and not hit.get("direct_cross_candidate") and not spoken_three \
            and lat is not None and lon is not None and verified_label \
            and profile.lower().removeprefix("zello-") != "sullivan":
        street_core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", hit["address"])
        street_core = re.sub(r"[,.;].*$", "", street_core).strip().lower()
        if street_core and street_core in verified_label.lower():
            cross, exact = await _cross_streets(lat, lon, hit["address"])
            cross = cross or ""
            if cross and not exact:
                stats.event(profile, "approximate map crosses omitted")
                cross = ""
            if cross:
                stats.event(profile, f"cross streets (computed): {cross}")
    # A numbered FDNY address can be sound while the vendor's spoken-cross
    # transcription is not. Verify each cross independently against actual
    # street geometry near the exact house; never replace an unverified spoken
    # block with a nearest map pair (that can describe a different block).
    if (profile == "fdny" and verified and re.match(r"^\d+[A-Za-z-]*\s+", hit["address"])
            and cross and "&" in cross and lat is not None and lon is not None):
        import spoken_cross as crossmap
        base_road = re.sub(r"^\s*\d+[A-Za-z-]*\s+", "", hit["address"].split(",")[0])
        sides = [part.strip() for part in cross.split("&", 1)]
        # Dispatch commonly omits the repeated type: "Foster to Newkirk
        # Avenue" means Foster Avenue and Newkirk Avenue. Only inherit an
        # explicit type when the first side is one bare name and both sides
        # independently intersect this verified street near the house.
        if (len(sides) == 2 and re.fullmatch(r"[A-Za-z][A-Za-z.'-]+", sides[0])
                and (typed := re.search(r"\b(Avenue|Street|Road|Place|Ave|St|Rd|Pl)\b$",
                                       sides[1], re.I))):
            sides[0] += " " + typed.group(1)
        try:
            verdicts = await asyncio.gather(*(asyncio.wait_for(
                crossmap.verify(base_road, side, lat, lon), timeout=10)
                for side in sides))
        except Exception:
            verdicts = [False, False]
        if all(verdicts) and " & ".join(sides) != cross:
            cross = " & ".join(sides)
            stats.event(profile, f"spoken abbreviated cross pair map-verified: {cross}")
        if not all(verdicts):
            stats.event(profile, f"unverified spoken FDNY crosses omitted: {cross}")
            ops_log(f"unverified spoken FDNY crosses omitted: {cross} @ {hit['address']}")
            cross = ""
    if cross and lat is not None and lon is not None and verified_label \
            and profile.lower().removeprefix("zello-") != "sullivan":
        core = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", hit["address"].split(",")[0]).strip()
        # Optional naming pass must not hold a verified, spoken incident hostage
        # to a slow Overpass endpoint. On timeout keep the spoken pair untouched.
        try:
            pool = await asyncio.wait_for(_map_street_names(lat, lon, core), timeout=5)
        except Exception as e:  # noqa: BLE001 - optional naming only
            logging.info("[%s] cross-name lookup skipped (%s); retaining spoken streets",
                         profile, type(e).__name__)
            pool = set()
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
    if (not verified and cross and GEOCODE_VERIFY
            and not re.match(r"^\s*\d", hit["address"])):
        # bare street ('53rd Street' + crosses '15th & 16th Avenue') - the
        # spoken intersection itself is the place; verify it on the map
        pt = await _intersection_point(hit["address"], cross)
        if pt[0] is None and profile.lower().startswith(("hatzalah", "zello-hatzalah", "fdny")):
            # One fresh map retry for a directly spoken intersection after a
            # transient Overpass miss. Never turn an unresolved map result
            # into a verified address. FDNY also needs this bounded retry;
            # Willoughby/Wilson car fire missed when the first lookup failed.
            await asyncio.sleep(0.5)
            pt = await _intersection_point(hit["address"], cross)
        if pt[0] is not None:
            lat, lon = pt
            verified = True
            verified_label = re.sub(r",", f" at {cross.split('&', 1)[0].strip()},",
                                    hit["address"], count=1)
            mloc = re.search(r",\s*([A-Za-z ]+),\s*NY", hit["address"])
            locality = mloc.group(1).strip() if mloc else locality
            stats.event(profile, f"verified via intersection (map): {verified_label}")
    if not verified and profile == "fdny" and box_task is not None and GEOCODE_VERIFY:
        # A heard box can correct a single ASR street spelling, but only if
        # the box's own borough and spoken cross independently corroborate it.
        rows = await box_task
        heard_street = re.sub(r"^\s*\d+\s+", "", hit["address"].split(",", 1)[0])
        for loc, borough in rows:
            if borough != "Brooklyn" or not _rare_tokens(loc) & _rare_tokens(cross):
                continue
            sides = re.split(r"\s+at\s+|\s*&\s+|/", loc, flags=re.I)
            for side in sides:
                side = side.strip()
                if not side or not re.search(r"\b(?:st|street|ave|avenue|rd|road)\b", side, re.I):
                    continue
                import difflib
                if difflib.SequenceMatcher(None, _street_core(heard_street),
                                            _street_core(side)).ratio() < 0.76:
                    continue
                type_long = re.sub(r"\bAVE\b", "Avenue", side, flags=re.I)
                type_long = re.sub(r"\bST\b", "Street", type_long, flags=re.I)
                type_long = re.sub(r"\bRD\b", "Road", type_long, flags=re.I)
                house = re.match(r"^\s*(\d+)\s+", hit["address"])
                if not house:
                    continue
                candidate = f"{house.group(1)} {type_long.title()}, {locality}, NY"
                v2, ins2, lbl2, la2, lo2, loc2 = await geocode_verify(candidate, profile)
                if v2 and loc2.lower() == locality.lower():
                    stats.event(profile, f"address corrected via box/map: {hit['address']} -> {candidate}")
                    ops_log(f"address corrected via box/map: {hit['address']} -> {candidate}")
                    hit["address"] = candidate
                    verified, in_sullivan, verified_label, lat, lon, locality = v2, ins2, lbl2, la2, lo2, loc2
                    break
            if verified:
                break
    if not verified and cross and GEOCODE_VERIFY:
        corrected = await _correct_street_via_crosses(hit["address"], cross)
        if corrected and corrected.lower() != hit["address"].lower():
            v2, ins2, lbl2, la2, lo2, loc2 = await geocode_verify(corrected, profile)
            if v2:
                stats.event(profile, f"address corrected via crosses: "
                                     f"{hit['address']} -> {corrected}")
                ops_log(f"address corrected via crosses: {hit['address']} -> {corrected}")
                hit["address"] = corrected
                verified, in_sullivan = True, ins2
                verified_label, lat, lon, locality = lbl2, la2, lo2, loc2
    if profile.lower().removeprefix("zello-") == "sullivan" and GEOCODE_VERIFY:
        location_check_finished = time.monotonic()
        logging.info("[%s] stages location_check=%.2fs before_location=%.2fs",
                     profile, location_check_finished-location_check_started,
                     location_check_started-verify_started)
    if not cross:
        ops_log(f"No cross street was said clearly enough to verify for {hit['nature']} at {hit['address']}.")
    colony = None
    if profile.lower().startswith(("sullivan", "hatzalah", "zello-sullivan", "zello-hatzalah")):
        try:
            import sullivan_colonies as scol
            if verified_label:
                r0 = scol.match_colony_for_verified_address(verified_label)
                colony = r0.colony_name if r0.found else None
            # No transcript/name fallback: only a verified street address may
            # identify a colony. Similar channel names are never job location.
        except Exception as e:  # noqa: BLE001
            logging.warning("colony match failed: %s", e)
    box_disp = ""
    box_loc = ""
    garbage_box = False
    box_mismatch = False
    if box_task is not None:
        try:
            rows = await box_task
        except Exception:  # noqa: BLE001
            rows = []
        heard = hit.get("box_heard") or _heard_box(hit.get("excerpt") or "")
        if rows and heard:
            # Reuse the earlier exact-house nearest-box corroboration for
            # selection, not just the false-box hold gate.
            house_box_agrees = False
            if verified and re.match(r"^\d+\s+", hit["address"]) and lat is not None and lon is not None:
                nearest, _near_loc, _dist = await _nearest_box(lat, lon, locality)
                own_road = re.sub(r"^south\b", "s", re.sub(r"^north\b", "n",
                           re.sub(r"^east\b", "e", re.sub(r"^west\b", "w",
                           _street_core(hit["address"])))))
                house_box_agrees = nearest == heard and any(
                    own_road == re.sub(r"^south\b", "s", re.sub(r"^north\b", "n",
                               re.sub(r"^east\b", "e", re.sub(r"^west\b", "w", _street_core(part)))))
                    for place, bor in rows if bor.lower() == locality.lower()
                    for part in re.split(r"\s+at\s+|&", place, flags=re.I))
            toks = _rare_tokens(f"{hit['address']} {cross} {verified_label}")
            inc_street = _street_core(verified_label or hit["address"])
            for loc, borough in rows:
                sides = {_street_core(p) for p in re.split(r"\s+at\s+|&", loc)}
                if (hit.get("terminal_street_box_correlated") and heard == "2685"
                        and borough == "Brooklyn" and "9 AVE" in loc.upper()
                        and "53 ST" in loc.upper()) or \
                        (house_box_agrees and borough.lower() == locality.lower() and
                         any(own_road == re.sub(r"^south\b", "s", re.sub(r"^north\b", "n",
                             re.sub(r"^east\b", "e", re.sub(r"^west\b", "w", _street_core(part)))))
                             for part in re.split(r"\s+at\s+|&", loc, flags=re.I))) or \
                        _box_row_matches_address_and_cross(loc, hit["address"], cross) or \
                        _rare_tokens(loc) & toks or \
                        (inc_street and inc_street in sides):
                    box_disp = heard
                    break
            if not box_disp and verified:
                # user verdict 9/28: never drop the box - it anchors. First try a
                # box-supported address correction (whisper ordinal digit-drop:
                # heard 'east 4th st', box row 'AVE M at E 84 ST' -> 'East 84th
                # Street'); else post the box + its location with a mismatch flag
                corrected_addr = _box_address_correction(hit["address"], rows)
                if corrected_addr:
                    stats.event(profile, f"address corrected via box: "
                                         f"{hit['address']} -> {corrected_addr} (Box {heard})")
                    ops_log(f"address corrected via box: {hit['address']} -> {corrected_addr} "
                            f"(Box {heard})")
                    hit["address"] = corrected_addr
                    box_disp = heard
                elif locality and not any(b.lower() == locality.lower() for _, b in rows):
                    # A box recorded only in a different borough is unsafe
                    # for the independently verified address. Drop the box.
                    garbage_box = True
                    stats.event(profile, f"box killed (borough mismatch): heard {heard} ("
                                + "; ".join(f"{l} {b}" for l, b in rows)
                                + f") vs {hit['address']} ({locality})")
                    ops_log(f"box killed (borough mismatch): heard {heard} vs "
                            f"{hit['address']} ({locality})")
                else:
                    pick = next((l for l, b in rows
                                 if locality and b.lower() == locality.lower()), rows[0][0])
                    garbage_box = True
                    stats.event(profile, f"box discarded (verified address, mismatch): Box {heard} - {pick} "
                                         f"vs {hit['address']}")
                    ops_log(f"box discarded (verified address, mismatch): Box {heard} - {pick} vs {hit['address']}")
            elif not box_disp:
                logging.info("[%s] box mismatch: heard Box %s, lookup %s", profile, heard, rows)
                stats.event(profile, f"box mismatch (not posted): heard {heard}, lookup "
                            + "; ".join(f"{l} ({b})" for l, b in rows))
                ops_log(f"box mismatch (not posted): heard Box {heard} @ {hit['address']}, "
                        f"lookup: " + "; ".join(f"{l} ({b})" for l, b in rows))
            from fdny_borough_gate import box_street_conflict
            if (verified and not box_disp and
                    box_street_conflict(hit["address"], locality, rows) and
                    not (re.match(r"^\d{1,5}(?:-\d{1,3})?\s+", hit["address"]) and
                         exact_numbered_fdny_match(hit["address"], verified_label))):
                reason = "spoken FDNY box conflicts with the verified street"
                stats.event(profile, f"Held: {reason}: Box {heard} @ {hit['address']}")
                ops_log(f"Held: {reason}: Box {heard} @ {hit['address']}")
                hit["hold_reason"] = reason
                return "suppressed"
        elif heard:
            garbage_box = True
            logging.info("[%s] box %s not in lookup DB - not posted", profile, heard)
            stats.event(profile, f"box {heard} not in lookup DB (not posted)")
    # A five-digit box+house run can equally be a four-digit box plus a
    # one-digit house, or a two-digit box plus a three-digit house. Resolve
    # ONLY when the actual box lookup independently matches the heard cross
    # or verified location. 83255 North Henry at Norman is Box 0083 + 255,
    # not Box 0832 + 55 and not the unrelated 8355.
    raw_run = hit.get("raw_box_run") or ""
    if profile == "fdny" and len(raw_run) == 5 and hit.get("box_glue_ambiguous"):
        street_tail = re.sub(r"^\d+\s+", "", hit["address"].split(",", 1)[0])
        heard_cross = hit.get("cross") or ""
        choices = []
        for n in (2, 3, 4):
            num = raw_run[:n].zfill(4)
            house = raw_run[n:]
            if not house or house.startswith("0"):
                continue
            candidate = f"{house} {street_tail}, Brooklyn, NY"
            yes, _, label, la, lo, loc = await geocode_verify(candidate, "fdny")
            if not yes or la is None or lo is None:
                continue
            rr = await _box_lookup(num)
            candidate_street = _rare_tokens(street_tail)
            cross_tokens = _rare_tokens(heard_cross)
            matching = [(place, bor) for place, bor in rr if bor == "Brooklyn"
                        and (candidate_street & _rare_tokens(place))
                        and (cross_tokens & _rare_tokens(place))]
            if matching:
                choices.append((num, candidate, label, la, lo, loc))
        if len(choices) != 1:
            stats.event(profile, f"suppressed (ambiguous five-digit box/house): {raw_run}")
            ops_log(f"suppressed (ambiguous five-digit box/house): {raw_run}")
            hit["hold_reason"] = "ambiguous five-digit box/house"
            return "suppressed"
        box_disp, hit["address"], verified_label, lat, lon, locality = choices[0]
        box_mismatch = False
        box_loc = ""
        verified = True
        stats.event(profile, f"five-digit box/house independently resolved: Box {box_disp} @ {hit['address']}")
    # A glued box/house run has multiple plausible splits. Require a verified
    # address before any post; never treat a box as proof of the house.
    if profile == "fdny" and hit.get("box_glue_ambiguous") and not verified:
        stats.event(profile, f"suppressed (ambiguous box/house split): {hit['address']}")
        ops_log(f"suppressed (ambiguous box/house split): {hit['address']}")
        hit["hold_reason"] = "ambiguous box/house split"
        return "suppressed"
    if profile.lower().removeprefix("zello-") == "sullivan" and verified and in_sullivan:
        # The county is a verification boundary, not the outgoing area name.
        # A spoken town may win over a smaller mapped village ONLY when that
        # same town is independently present in the map's verified label.
        mapped = re.sub(r"^(?:village|town|hamlet|city) of\s+", "", locality.strip(), flags=re.I)
        spoken = re.search(r"\btown of\s+([A-Za-z][A-Za-z'-]*)\b", hit.get("excerpt") or "", re.I)
        if spoken and re.search(r"\bTown of\s+" + re.escape(spoken.group(1)) +
                                r"\b", verified_label, re.I):
            mapped = spoken.group(1)
        if mapped and mapped.lower() not in ("sullivan co", "sullivan county", "new york"):
            hit["verified_area"] = mapped
        else:
            hit["hold_reason"] = "verified Sullivan location has no town/area"
            stats.event(profile, f"Held: {hit['hold_reason']}: {hit['address']}")
            return "suppressed"
    # A verified address is mandatory. A box alone cannot rehabilitate an
    # unverified ASR road spelling. A mismatched box is omitted, not swapped
    # for another guessed box; an absent box is never guessed.
    if not verified:
        reason = "unconfirmed, no box" if profile == "fdny" else "no verified location"
        logging.info("[%s] suppressed (%s): %s", profile, reason, hit["address"])
        stats.event(profile, f"Held: Heard {hit['address']}, but could not verify that location for {hit['nature']}.")
        ops_log(f"Held: Heard {hit['address']}, but could not verify that location for {hit['nature']}.")
        hit["hold_reason"] = reason
        return "suppressed"
    if profile == "fdny" and GEOCODE_VERIFY:
        from fdny_borough_gate import exact_numbered_fdny_match
        if not exact_numbered_fdny_match(hit["address"], verified_label):
            reason = "map did not confirm the exact FDNY house and street"
            stats.event(profile, f"Held: {reason}: {hit['address']} (map: {verified_label})")
            ops_log(f"Held: {reason}: {hit['address']} (map: {verified_label})")
            hit["hold_reason"] = reason
            return "suppressed"
    # A nearby map box is not a box spoken for this dispatch. Do not add one,
    # and never hold a verified address solely because no box was obtainable.
    box_closest = False
    if profile == "fdny" and verified and garbage_box and not box_disp:
        stats.event(profile, f"verified address posting without untrusted box: {hit['address']}")
    # North Shore Towers is a documented complex reached from the Grand
    # Central Parkway service road. Keep the broad highway geocode as the
    # verification gate, but display the spoken landmark and approach rather
    # than replacing the location with an arbitrary tower's house number.
    if hit.get("north_shore_towers") and verified and \
            re.match(r"^Grand Central Parkway, Queens, NY$", hit["address"], re.I):
        access = ("Grand Central Parkway Service Road" if
                  hit.get("service_road_spoken") else "Grand Central Parkway")
        hit["address"] = f"North Shore Towers, {access}, Queens, NY"
    text_out = format_alert(hit, crosses=cross, confirmed=verified, footer=colony,
                            box=box_disp if profile == "fdny" else "",
                            box_loc=box_loc if profile == "fdny" else "",
                            box_mismatch=box_mismatch if profile == "fdny" else False,
                            box_closest=box_closest if profile == "fdny" else False,
                            box_cross=spoken_cross if spoken_cross_verified and profile == "fdny" else "",
                            audio_ts=(audio_ts if audio_ts is not None else fresh_ts)
                            if clip_name else None, spoken_time=hit.get("spoken_time") or "")
    verified_at = time.monotonic()
    if profile.lower().removeprefix("zello-") == "sullivan":
        logging.info("[%s] stages verification_total=%.2fs after_location=%.2fs",
                     profile, verified_at-verify_started,
                     verified_at-location_check_finished if 'location_check_finished' in locals()
                     else 0.0)
    ogg = None
    if ogg_task is not None:
        try:
            ogg = await ogg_task
        except Exception:  # noqa: BLE001
            ogg = None
    ogg_at = time.monotonic()
    if send_lock is not None:
        await send_lock.acquire()
    try:
        if profile == "fdny" and correction_guard is not None and source_call is not None:
            correction_guard.ingest([])  # expire old correction evidence
            guard_reason = correction_guard.reason(hit, source_call)
            if guard_reason:
                stats.event(profile, f"held ({guard_reason}): {hit['nature']} @ {hit['address']}")
                ops_log(f"held ({guard_reason}): {hit['nature']} @ {hit['address']}")
                hit['hold_reason'] = guard_reason
                return "suppressed"
        ok = await alert_waha.send_text(text_out)
        if ok and profile == "fdny" and correction_guard is not None:
            correction_guard.mark_sent(hit)
        text_at = time.monotonic()
        logging.info("[%s] stages verification=%.2fs voice_convert=%.2fs text_send=%.2fs",
                     profile, verified_at-verify_started, ogg_at-verified_at,
                     text_at-ogg_at)
        if not ok:
            ops_log(f"ALERT POST FAILED: {hit['nature']} @ {hit['address']}")
            return "queued"
        if clip_name:
            if ogg:
                base = os.environ.get("RENDER_EXTERNAL_URL", "https://fdny-slim.onrender.com").rstrip("/")
                vok = await alert_waha.send_voice(f"{base}/audio/{ogg}")
                if vok:
                    hit["voice_sent"] = True
                else:
                    ops_log(f"voice-note send failed: {hit['nature']} @ {hit['address']}")
            else:
                ops_log(f"voice-note convert failed: {hit['nature']} @ {hit['address']}")
    finally:
        if send_lock is not None:
            send_lock.release()
    if hit.get("voice_sent") and ogg:
        hit["voice_url"] = await _uguu_upload(ARCHIVE_DIR / ogg)
        if not hit["voice_url"]:
            ops_log(f"archive upload failed (post ok): {hit['nature']} @ {hit['address']}")
    if profile == "fdny":
        logging.info("[fdny] stages after_text=%.2fs verify_to_end=%.2fs",
                     time.monotonic()-text_at, time.monotonic()-verify_started)
    if nat_norm and toks:
        recent = _load_recent()
        recent.append({"t": now, "nature": nat_norm, "tokens": sorted(toks)})
        _save_recent(recent)
    return "sent"


def format_alert(hit: dict, crosses: str = "", confirmed: bool = True,
                 footer: str | None = None, box: str = "", box_loc: str = "",
                 box_mismatch: bool = False, box_closest: bool = False,
                 box_cross: str = "",
                 audio_ts: float | None = None, spoken_time: str = "") -> str:
    """User-picked layout (9/28, option 1): bold caps nature header with fire
    emoji; bold pinned address; plain 'between X & Y' crosses line; time;
    italic source footer at the very bottom. No transcript quote, ever.
    Audio follows separately as a voice-note bubble."""
    now = datetime.now(NY).strftime("%-I:%M %p")
    nature = (hit.get("nature") or "").strip().upper()
    is_sullivan = (hit.get("source") or "").removeprefix("zello-") == "sullivan"
    street = hit["address"]
    if is_sullivan:
        street = re.sub(r",\s*[^,]+,\s*NY$", "", street, flags=re.I)
    addr_line = f"\N{ROUND PUSHPIN} *{street}*"
    if is_sullivan and footer:
        addr_line += f" ({footer})"
    if not confirmed:
        addr_line += " (not confirmed)"
    medical = re.search(
        r"\b(?:cyclist|bicyclist|breath(?:ing)?|cardiac|arrest|cpr|unresponsive|responsive|chok|"
        r"overdose|stroke|cva|seizure|convuls|fall|fell|bleeding|hemorrhage|"
        r"chest pain|drown|syncope|faint|passed out|diabet|sugar|allergic|"
        r"anaphyla|bee sting|abdominal|stomach|altered|disoriented|"
        r"unconscious|aided|trauma|not acting right|general illness|generally ill|gi distress|"
        r"not feeling well|feeling unwell|feels unwell|feels ill|feeling ill|"
        r"doesn.t feel well|does not feel well|"
        r"sick person|medical emergency|ped(?:estrian)?|mva|mvc|accident|"
        r"collision|rollover|entrap)\w*\b", nature, re.I)
    icon = "\N{AMBULANCE}" if medical else "\N{FIRE}"
    lines = [f"*{icon} {nature}*", "", addr_line]
    if is_sullivan and hit.get("verified_area"):
        lines.append(f"*{hit['verified_area'].upper()}*")
    if hit.get("apartment"):
        lines.append(hit["apartment"])
    if crosses:
        lines.append(f"C/s {crosses}" if "&" in crosses else f"off {crosses}")
    if box:
        line = f"Box {box}"
        if box_closest:
            line += " (closest)"
        if box_loc:
            line += f" - {box_loc}"
        if box_cross:
            line += f" · at {box_cross}"
        lines.append(line)
        if box_mismatch:
            lines.append("\N{WARNING SIGN} spoken address not at box location")
    try:
        stamp = float(audio_ts) if audio_ts is not None else 0
        # Timestamps outside the live job window cannot be trusted as this
        # dispatch's capture time; never print an invented CAD time.
        time_line = ("CAD - TIME " + datetime.fromtimestamp(stamp, NY).strftime("%H:%M")
                     if stamp > 0 and abs(time.time() - stamp) < 2 * 3600
                     else f"\N{CLOCK FACE ONE OCLOCK} {now}")
    except (ValueError, TypeError, OverflowError, OSError):
        time_line = f"\N{CLOCK FACE ONE OCLOCK} {now}"
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", spoken_time):
        time_line = f"CAD - TIME {spoken_time}"
    lines += ["", time_line]
    label = footer or SOURCE_LABEL.get(hit["source"], hit["source"])
    if hit.get("source") == "fdny":
        dispatch_area = re.search(r",\s*(Brooklyn|Queens|Manhattan|Bronx|Staten Island),\s*NY$",
                                  hit.get("address") or "", re.I)
        if dispatch_area:
            borough = dispatch_area.group(1).title()
            label = ("FDNY Brooklyn feed - " + borough + " borough announcement"
                     if borough != "Brooklyn" else "FDNY Brooklyn Dispatch")
    if (hit.get("source") or "").removeprefix("zello-") == "sullivan":
        # The same pager carries fire and EMS jobs. Empress/EMS/ALS/BLS
        # dispatches are EMS; otherwise use the spoken nature, without
        # guessing from an address or an ordinary unit number.
        heard = (hit.get("excerpt") or "").lower()
        ems_dispatch = bool(re.search(r"\b(?:dispatch\s+to\s+empress|for\s+empress|ems\s+(?:call|response|dispatch)|als\s+response|bls\s+response)\b", heard))
        label = "EMS" if medical or ems_dispatch else "Sullivan FD"
        if label == "EMS":
            try:
                import sullivan_tone
                toned = sullivan_tone.toned_label(hit.get("excerpt") or "")
                if toned:
                    label += f" · {toned}"
            except Exception as e:  # noqa: BLE001
                logging.warning("Sullivan tone parser unavailable: %s", e)
    lines.append(f"_{label}_")
    # Presentation only: keep the spoken transcript and structured hit unchanged.
    text = "\n".join(lines)
    text = re.sub(r"\bpatient\b", "PTT", text, flags=re.I)
    return re.sub(r"\bapartment\b", "APT", text, flags=re.I)


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


def _ptt_group_match(rec: dict, started: float, addr: str, gap: float, nature: str = "") -> bool:
    if started < rec["start"] or started - rec["stop"] > gap:
        return False
    if addr and rec["address"]:
        if _street_core(addr) != _street_core(rec["address"]): return False
        old_house = re.match(r"^\s*(\d+)\s+", rec["address"])
        new_house = re.match(r"^\s*(\d+)\s+", addr)
        if old_house and new_house and old_house.group(1) != new_house.group(1): return False
    if nature and rec.get("nature") and nature.lower() != rec["nature"].lower():
        return False
    return bool((addr and rec["address"]) or (rec["opener"] and not rec["address"])
                or (rec["opener"] and not addr))


def _ptt_ready(profile: str) -> list[Path]:
    """Only fully converted, metadata-backed transmissions; never read .part."""
    return sorted((p for p in SEG_DIR.glob(f"{profile}-ptt-*.wav")
                   if p.with_suffix(".json").exists() and p.stat().st_size > 44),
                  key=lambda p: p.stat().st_mtime)


async def verify_zello_with_second_listen(profile: str, hit: dict, stats,
                                          clip_name: str, *, fresh_ts: float) -> tuple[str, dict]:
    """Primary ASR first; one optional second listen before finalizing a hold.

    A different job/address never becomes an automatic post. Every revised
    candidate goes through the entire normal verification and freshness gate.
    """
    outcome = await verify_and_send(profile, hit, stats, clip_name, fresh_ts=fresh_ts,
                                    audio_ts=fresh_ts)
    if outcome != "suppressed" or not transcribe.GROQ_ENABLED:
        return outcome, hit
    reason = hit.get("hold_reason") or ""
    if reason not in ("no nature", "no verified location", "ambiguous default borough",
                      "spoken crossing roads not verified") and not reason.startswith(
                          ("spoken cross unverified:",)):
        return outcome, hit
    # If the first ASR heard a complaint, the second ear may clarify its
    # location, never overturn that complaint into another incident. An
    # original 'no nature' may recover only when the road and house agree.
    src = ARCHIVE_DIR / clip_name
    if not src.is_file():
        return outcome, hit
    second = await asyncio.to_thread(transcribe.second_listen, src, profile)
    if not second:
        return outcome, hit
    candidates = [detect.analyze(span, profile) for span in
                  detect.split_dispatch_jobs(second, profile)]
    candidates = [c for c in candidates if c and c.get("nature") and c.get("address")]
    if len(candidates) != 1:
        return outcome, hit
    candidate = candidates[0]
    # Two ASR readings can disagree about a street or another incident.
    # Only rescue this same road with an equal or newly recovered house.
    old_road = _street_core(hit.get("address") or "")
    new_road = _street_core(candidate["address"])
    old_house = re.match(r"^\s*(\d{1,5}(?:-\d{1,3})?)\s+", hit.get("address") or "")
    new_house = re.match(r"^\s*(\d{1,5}(?:-\d{1,3})?)\s+", candidate["address"])
    if (not old_road or old_road != new_road or
            (old_house and (not new_house or old_house.group(1) != new_house.group(1))) or
            (hit.get("nature") and candidate["nature"].lower() != hit["nature"].lower())):
        stats.event(profile, "second listen disagreed on incident location or complaint; held for review")
        return outcome, hit
    # A second ASR is diagnostic, not permission to silently replace a
    # different claimed town; the map must still verify its exact job area.
    revised = await verify_and_send(profile, candidate, stats, clip_name,
                                    fresh_ts=fresh_ts, audio_ts=fresh_ts)
    if revised == "sent":
        stats.event(profile, "held job recovered by second listen and map verification")
        return revised, candidate
    return outcome, hit


async def ptt_consumer(profile: str, stats: Stats, seen: dict) -> None:
    """Trial incident grouping over Zello stream IDs. Legacy segment consumer
    continues independently and is the fallback on missing events or decode.
    Group only same location or a clear opener followed by a bounded repeat;
    never splice a separate address/nature into one job.
    """
    processed: set[str] = set()
    pending: list[dict] = []
    gap = max(0.5, min(zello_ingest.GROUP_TRIAL_SEC, 12.0))
    opener = re.compile(r"\b(?:dispatch\s+to|units?\s+in|any\s+units?\s+in|"
                        r"(?:sullivan|hatzalah)\s+dispatch)\b", re.I)
    while True:
        for wav in _ptt_ready(profile):
            if wav.name in processed: continue
            processed.add(wav.name)
            if len(processed) > 500:
                processed = {n for n in processed if (SEG_DIR / n).exists()}
            try:
                meta = json.loads(wav.with_suffix(".json").read_text())
                started, stopped = float(meta["start"]), float(meta["stop"])
                if not 0 < started <= stopped or time.time() - stopped > FRESH_LIVE_SEC:
                    zello_ingest.stream_owner(profile, wav.stem, started, stopped, "failed")
                    wav.unlink(missing_ok=True);wav.with_suffix(".json").unlink(missing_ok=True)
                    continue
                asr_started = time.monotonic()
                text = await asyncio.to_thread(transcribe.transcribe, wav, profile)
                logging.info("[%s] stages ptt_stop_to_read=%.2fs asr=%.2fs",
                             profile, max(0.0, time.time()-stopped),
                             time.monotonic()-asr_started)
                if not text:
                    zello_ingest.stream_owner(profile, wav.stem, started, stopped, "failed")
                    wav.unlink(missing_ok=True);wav.with_suffix(".json").unlink(missing_ok=True)
                    continue
                zello_ingest.stream_owner(profile, wav.stem, started, stopped, "owned")
                stats.mark_segment(profile);stats.mark_transcript(profile, text)
                await _kw_check(profile, text)
                hit = detect.analyze(text, profile)
                addr = (hit or {}).get("address", "")
                nature = (hit or {}).get("nature", "")
                matched = None
                for rec in pending:
                    if _ptt_group_match(rec, started, addr, gap, nature):
                        matched = rec;break
                if matched:
                    matched["wav"].append(wav);matched["stop"] = stopped
                    matched["text"] += " " + text
                    matched["address"] = addr or matched["address"]
                    matched["nature"] = nature or matched["nature"]
                else:
                    pending.append({"start":started,"stop":stopped,"wav":[wav],
                                    "text":text,"address":addr,"nature":nature,
                                    "opener":bool(opener.search(text))})
            except Exception as e:
                logging.warning("[%s] PTT consumer error: %s", profile, e)
                try:
                    bad_meta = json.loads(wav.with_suffix(".json").read_text())
                    zello_ingest.stream_owner(profile, wav.stem, float(bad_meta["start"]),
                                              float(bad_meta["stop"]), "failed")
                except Exception:
                    pass
        for rec in list(pending):
            if time.time() - rec["stop"] < gap + zello_ingest.TAIL_SEC: continue
            pending.remove(rec)
            target=rec["wav"][0]
            try:
                text=rec["text"]
                hits = [detect.analyze(span, profile) for span in detect.split_dispatch_jobs(text, profile)]
                target=rec["wav"][0]
                if len(rec["wav"]) > 1:
                    grouped=SEG_DIR / f"ptt-group-{profile}-{int(rec['start']*1000)}.wav"
                    import wave
                    with wave.open(str(grouped), 'wb') as wo:
                        wo.setnchannels(1);wo.setsampwidth(2);wo.setframerate(16000)
                        for part in rec["wav"]:
                            with wave.open(str(part),'rb') as wi:
                                wo.writeframes(wi.readframes(wi.getnframes()))
                    target=grouped
                clip_name = f"{profile}-ptt-{int(rec['start']*1000)}.wav"
                await asyncio.to_thread(_archive_clip,target,clip_name)
                stats.mark_clip(profile,clip_name,text)
                for hit in hits:
                    if not hit:continue
                    key=f"{profile}|{hit['nature']}|{hit['address']}"
                    now=time.time()
                    if now-seen.get(key,0)<DEDUP_SEC:continue
                    seen[key]=now;_save_seen(seen)
                    outcome,hit=await verify_zello_with_second_listen(
                        profile,hit,stats,clip_name,fresh_ts=rec["start"])
                    ok=outcome=="sent"
                    if outcome=="suppressed":
                        hit["voice_url"]=await _held_recording(clip_name)
                        await _post_held_review(profile, hit, clip_name)
                    stats.mark_alert(profile,hit["nature"],hit["address"],ok,
                                     voice_url=hit.get("voice_url",""),failed=(outcome=="queued"),
                                     outcome=outcome,reason=hit.get("hold_reason",""))
                    _append_alert_log({"t":now,"feed":profile,"nature":hit["nature"],
                                       "address":hit["address"],"sent":ok,"excerpt":hit["excerpt"]})
            except Exception as e:
                logging.warning("[%s] PTT grouped dispatch error: %s",profile,e)
            finally:
                # Completed incident is kept in ARCHIVE_DIR and uploaded by
                # send/hold; raw PTT pieces are transient and must not fill
                # Render's small free-tier filesystem.
                for part in rec["wav"]:
                    part.unlink(missing_ok=True)
                    part.with_suffix(".json").unlink(missing_ok=True)
                if target != rec["wav"][0]:
                    target.unlink(missing_ok=True)
        await asyncio.sleep(1)


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
            # The old ring is strictly fallback. A completed PTT file close
            # to this ring segment means the same audio is already handled by
            # the stream-ID consumer. On a stalled/missing PTT decode, allow
            # the old ring after a bounded 30s wait. Never race a pending PTT
            # group's verify/send just because transcription is slow.
            if profile in zello_ingest.CHANNELS:
                age = time.time() - mtime
                ownership = zello_ingest.stream_owner_state(profile, mtime)
                if ownership == "owned":
                    processed[wav.name] = mtime
                    prev = None  # never pair fallback with audio owned by PTT
                    continue
                if ownership == "pending" or age < 30:
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
            text = await asyncio.to_thread(transcribe.transcribe, target, profile)
            if not text:
                continue
            stats.mark_transcript(profile, text)
            logging.info("[%s] heard: %s", profile, text[:160])
            await _kw_check(profile, text)
            clip_name = f"{profile}-{int(time.time())}.wav"
            await asyncio.to_thread(_archive_clip, target, clip_name)
            stats.mark_clip(profile, clip_name, text)
            try:
                job_spans = detect.split_dispatch_jobs(text, profile)
                hits = [detect.analyze(span, profile) for span in job_spans]
            except Exception as e:  # noqa: BLE001 - one bad chunk must never kill the feed
                logging.warning("[%s] detect failed: %s", profile, e)
                stats.event(profile, f"detect error: {e}")
                prev = wav
                continue
            for hit in hits:
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
                outcome, hit = await verify_zello_with_second_listen(
                    profile, hit, stats, clip_name, fresh_ts=wav.stat().st_mtime)
                ok = outcome == "sent"
                if outcome == "suppressed":
                    hit["voice_url"] = await _held_recording(clip_name)
                    await _post_held_review(profile, hit, clip_name)
                stats.mark_alert(profile, hit["nature"], hit["address"], ok,
                                 voice_url=hit.get("voice_url", ""),
                                 failed=(outcome == "queued"), outcome=outcome,
                                 reason=hit.get("hold_reason", ""))
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


async def _fdny_independent_hearing(wav: Path) -> str:
    """Disabled on the free service: small.en exceeded its memory limit.

    Do not substitute the primary tiny.en model as independent evidence.
    Disputed FDNY details are held in _fdny_handle_call for review.
    """
    return ""


async def _fdny_recover_held_street(hit: dict, wav: Path, stats: Stats,
                                    call: dict, clip_name: str,
                                    send_lock: asyncio.Lock | None = None,
                                    correction_guard: CorrectionGuard | None = None) -> str:
    """Bounded Groq second listen for a still-fresh, held exact-house FDNY call.

    Never synthesizes a location from the map. Both readings must agree on
    the house, box and complaint. The candidate gets the normal sender gates.
    """
    if not transcribe.GROQ_ENABLED or not transcribe.GROQ_KEY or not wav.is_file():
        return "suppressed"
    try:
        age = time.time() - float(call.get("ts") or 0)
    except (TypeError, ValueError):
        return "suppressed"
    if not 0 <= age <= FRESH_FDNY_SEC:
        return "suppressed"
    from fdny_correction_guard import address_parts
    old_parts = address_parts(hit.get("address"))
    if not old_parts or not hit.get("nature") or not hit.get("box_heard"):
        return "suppressed"
    second = await asyncio.to_thread(transcribe.second_listen, wav, "fdny")
    if not second:
        stats.event("fdny", "held street second listen unavailable; retained hold")
        return "suppressed"
    spans = detect.split_dispatch_jobs(second, "fdny")
    if len(spans) != 1:
        return "suppressed"
    candidate = detect.analyze(spans[0], "fdny")
    new_parts = address_parts((candidate or {}).get("address"))
    if not new_parts or old_parts[0] != new_parts[0] or old_parts[2] != new_parts[2]:
        stats.event("fdny", "held street second listen disagreed on house/borough; retained hold")
        return "suppressed"
    if (candidate.get("box_heard") != hit.get("box_heard") or
            candidate.get("nature", "").lower() != hit["nature"].lower()):
        stats.event("fdny", "held street second listen disagreed on box/complaint; retained hold")
        return "suppressed"
    # An independent address is not enough: the house/street must resolve to
    # the actual mapped house, and both cross roads must share street geometry
    # near it. For a different vendor street, require a matching spoken cross.
    verified, _, label, lat, lon, locality = await geocode_verify(candidate["address"], "fdny")
    from fdny_borough_gate import exact_numbered_fdny_match
    if not (verified and lat is not None and lon is not None and
            exact_numbered_fdny_match(candidate["address"], label)):
        return "suppressed"
    crosses = [c.strip() for c in (candidate.get("cross") or "").split("&") if c.strip()]
    if old_parts[1] != new_parts[1]:
        old_crosses = [c.strip() for c in (hit.get("cross") or "").split("&") if c.strip()]
        if not crosses or not any(_street_core(c) == _street_core(oc)
                                  for c in crosses for oc in old_crosses):
            return "suppressed"
    if crosses:
        import spoken_cross as crossmap
        base = re.sub(r"^\s*\d+[A-Za-z-]*\s+", "", candidate["address"].split(",")[0])
        checks = await asyncio.gather(*(asyncio.wait_for(
            crossmap.verify(base, c, lat, lon), timeout=10) for c in crosses),
            return_exceptions=True)
        if old_parts[1] != new_parts[1]:
            # A common verified spoken cross anchors the changed road; the
            # other ASR cross may be a wrong block, so omit the pair if any
            # side fails rather than rejecting the exact-house rescue.
            shared = { _street_core(oc) for oc in old_crosses }
            if not any(check is True and _street_core(side) in shared
                       for side, check in zip(crosses, checks)):
                return "suppressed"
        if not all(v is True for v in checks):
            candidate["cross"] = ""
    # No delayed rescue when the second look has consumed the freshness budget.
    if time.time() - float(call["ts"]) > FRESH_FDNY_SEC:
        return "suppressed"
    # This path repairs a held incident; a prior failed vendor address must
    # not donate its dedup key. The final sender still checks live freshness,
    # map, box and correction guard, with sends intercepted in tests.
    candidate["hold_reason"] = ""
    return await verify_and_send("fdny", candidate, stats, clip_name,
                                 fresh_ts=float(call["ts"]),
                                 audio_ts=float(call.get("audio_start_ts") or call["ts"]),
                                 send_lock=send_lock, correction_guard=correction_guard,
                                 source_call=call)


async def _fdny_repair_brooklyn_street(hit: dict, wav: Path, stats: Stats,
                                       second: str | None = None) -> None:
    """Narrow local correction of a failed Brooklyn street spelling.

    Only a single named road within 180m of an exact verified house, a
    nearby spoken cross, and both transcript readings can support it. This
    cannot turn a numeric street, a missing house or an unverified road into
    a guessed address. The normal sender still verifies the final candidate.
    """
    import difflib
    addr = hit.get("address") or ""
    m = re.fullmatch(r"(\d{1,5})\s+([A-Za-z][A-Za-z' -]+?)\s+"
                     r"(Street|Avenue|Road|Place|Drive|Court), Brooklyn, NY", addr, re.I)
    if not m or re.search(r"\d", m.group(2)):
        return
    # A numbered address from a second job in one clip cannot borrow this
    # house's cross and phonetic road evidence.
    vendor_houses = set(re.findall(
        r"\b(\d{1,5})\s+[A-Za-z][A-Za-z' -]+?\s+"
        r"(?:Street|Avenue|Road|Place|Drive|Court)\b", hit.get("excerpt") or "", re.I))
    if vendor_houses != {m.group(1)}:
        return
    try:
        verified = await geocode_verify(addr, "fdny")
    except Exception:
        return
    if verified[0]:
        return
    vendor_street = (m.group(2) + " " + m.group(3)).lower()
    excerpt = hit.get("excerpt") or ""
    # The second recognizer is independent of the FDNY Calls ASR. A silent,
    # partial or contradictory reading is not evidence for a map repair.
    if second is None:
        try:
            second = await _fdny_independent_hearing(wav)
        except Exception:
            return
    if not second or not re.search(r"\b(?:street|avenue|road|place|drive|court)\b", second, re.I):
        return
    # If the independent reader clearly contradicts the house number,
    # fail closed. It may lose a leading digit (396 -> 96), but the
    # surviving trailing digits must agree. A mixed separate job stays out.
    other_houses = re.findall(r"\b(\d{1,5})\s+[A-Za-z]{4,15}\s+" +
                              re.escape(m.group(3)) + r"\b", second, re.I)
    if other_houses and any(not m.group(1).endswith(n) for n in other_houses):
        return
    # A numbered house must be present in the vendor transcript and not be
    # contradicted by the second hearing (which can drop a leading digit).
    if not re.search(r"\b" + re.escape(m.group(1)) + r"\s+" +
                     re.escape(m.group(2)), excerpt, re.I):
        return
    # Only a short, distinctive vendor street spelling can be corrected;
    # no swapping a known named street for an unrelated nearby one.
    if len(m.group(2)) < 5:
        return
    # The city street-name index supplies candidates. Do not fish through
    # generic geosearch's top fuzzy house hits; those omit the true road.
    official = ("https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/"
                "services/DCM_Street_Center_Line/FeatureServer/0/query")
    stem = m.group(2).split()[0].upper()
    params = {"where": f"Borough = 'Brooklyn' AND UPPER(Street_NM) LIKE '{stem[:4]}%'",
              "outFields": "Street_NM,Borough", "returnGeometry": "false", "f": "json"}
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(official, params=params,
                                timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    return
                features = (await resp.json()).get("features") or []
    except Exception:
        return
    names = {str((f.get("attributes") or {}).get("Street_NM") or "") for f in features}
    candidates = []
    for road in names:
        if road.lower() == vendor_street or not road.lower().endswith(m.group(3).lower()):
            continue
        if difflib.SequenceMatcher(None, road.lower(), vendor_street).ratio() < 0.85:
            continue
        candidate = f"{m.group(1)} {road.title()}, Brooklyn, NY"
        try:
            v, _, label, lat, lon, borough = await geocode_verify(candidate, "fdny")
        except Exception:
            continue
        if not (v and lat is not None and lon is not None and borough.lower() == "brooklyn"
                and label.lower().startswith(f"{m.group(1)} {road.lower()}")):
            continue
        candidates.append((candidate, lat, lon, road))
    if len(candidates) != 1:
        return
    candidate, lat, lon, road = candidates[0]
    # Official city street data confirms the nearby road and a second spoken
    # cross within the same small radius. A shared borough alone is not proof.
    official = ("https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/"
                "services/DCM_Street_Center_Line/FeatureServer/0/query")
    params = {"where": "Borough = 'Brooklyn'", "geometry": f"{lon},{lat}",
              "geometryType": "esriGeometryPoint", "inSR": "4326",
              "spatialRel": "esriSpatialRelIntersects", "distance": 180,
              "units": "esriSRUnit_Meter", "outFields": "Street_NM,Borough",
              "returnGeometry": "false", "f": "json"}
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(official, params=params,
                                timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    return
                nearby = (await resp.json()).get("features") or []
    except Exception:
        return
    roads = {str((f.get("attributes") or {}).get("Street_NM") or "").lower()
             for f in nearby}
    if road.lower() not in roads or vendor_street in roads:
        return
    # Require another named road near the candidate that occurs as a full
    # street phrase in BOTH independent readings, not merely a generic type.
    cross = [r for r in roads if r != road.lower() and len(r.split()[0]) >= 5
             and any(difflib.SequenceMatcher(None, w.lower(), r.split()[0]).ratio() >= 0.82
                     for w in re.findall(r"\b([A-Za-z]{5,15})\s+" +
                                         re.escape(r.split()[-1]) + r"\b", excerpt, re.I))
             and re.search(r"\b" + re.escape(r) + r"\b", second, re.I)]
    if len(cross) != 1:
        return
    # Independent reading must also contain a similar street name; the
    # official spelling is a correction, not a new unspoken street.
    heard_roads = re.findall(r"\b([A-Za-z]{4,15})\s+" + re.escape(m.group(3)) + r"\b",
                             second, re.I)
    if not any(word[0].lower() == road[0].lower() and
               difflib.SequenceMatcher(None, word.lower(), road.split()[0].lower()).ratio() >= 0.52
               for word in heard_roads):
        return
    hit["address"] = candidate
    stats.event("fdny", f"street spelling repaired with exact house and cross: {addr} -> {candidate}")


async def _fdny_recheck_qualifiers(hit: dict, wav: Path, stats: Stats,
                                   second: str | None = None) -> None:
    """Independently re-hear post-bound apartment/floor/occupancy detail.

    A repeated hallucination in the vendor ASR is still one source. If the
    independent audio reading is absent or inconclusive, remove only the
    unsupported detail, never manufacture an alternative qualifier.
    """
    nat = hit.get("nature") or ""
    if not re.search(r"\b(?:apartment|apt\.?|floors?|basement|cellar|dwelling)\b", nat, re.I):
        return
    if second is None:
        try:
            second = await _fdny_independent_hearing(wav)
        except Exception as e:  # noqa: BLE001
            logging.warning("[fdny] qualifier recheck failed (%s)", e)
            second = ""
    apt = re.search(r",\s*Apartment\s+([A-Za-z0-9]+)", nat, re.I)
    if apt:
        detail = apt.group(1)
        number = re.match(r"\d+", detail)
        number_seen = bool(number and re.search(
            r"\b(?:apartment|apt\.?)\s+" + re.escape(number.group()) + r"\b", second, re.I))
        exact_seen = bool(re.search(r"\b(?:apartment|apt\.?)\s+" +
                                    re.escape(detail) + r"\b", second, re.I))
        if not exact_seen:
            replacement = ", Apartment " + number.group() if number_seen else ""
            nat = nat[:apt.start()] + replacement + nat[apt.end():]
            stats.event("fdny", "unconfirmed apartment qualifier omitted")
    if re.search(r"\bsmoke\s+in\s+the\s+(?:basement|cellar)\s+of\s+a\s+"
                 r"(?:private|multiple)\s+dwelling\b", nat, re.I):
        if not re.search(r"\bsmoke\s+in\s+the\s+(?:basement|cellar)\s+of\s+a\s+"
                         r"(?:private|multiple)\s+dwelling\b", second, re.I):
            nat = "Smoke" if re.search(r"\bsmoke\b", second, re.I) else ""
            stats.event("fdny", "unconfirmed smoke-location detail omitted")
    for qualifier in ("basement", "cellar", "floor"):
        if re.search(r"\b" + qualifier + r"s?\b", nat, re.I) and not re.search(
                r"\b" + qualifier + r"s?\b", second, re.I):
            nat = re.sub(r",?\s*\b[^,]*\b" + qualifier + r"s?\b[^,]*",
                         "", nat, flags=re.I).strip(", ")
            stats.event("fdny", "unconfirmed location qualifier omitted")
    hit["nature"] = nat


def _fdny_call_record(call: dict, transcript: str, clip_name: str | None,
                      hit: dict | None, decision: str, reason: str = "") -> None:
    """Best-effort audit record. Local Render Free storage is ephemeral.

    Does not extend recording retention: audio path refers to the bounded
    rotating archive and may cease to exist. A durable remote sink is pending.
    """
    try:
        SEG_DIR.mkdir(parents=True, exist_ok=True)
        row = {"id": str(call.get("id") or call.get("filename") or ""),
               "ts": call.get("ts"), "audio_start_ts": call.get("audio_start_ts"),
               "feed": "fdny", "transcript": transcript,
               "audio_path": str(ARCHIVE_DIR / clip_name) if clip_name else "",
               "audio_url": str(call.get("audio_url") or ""),
               "nature": (hit or {}).get("nature", ""),
               "address": (hit or {}).get("address", ""),
               "decision": decision, "reason": reason,
               "recorded_at": time.time()}
        with (SEG_DIR / "fdny_call_records.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # audit failure must not manufacture a post
        logging.error("[fdny] local audit record failed id=%s: %s", call.get("id"), exc)


def _fdny_clip_sanity(wav: Path | None, transcript: str) -> str:
    """Fail closed on an absent, silent, or physically impossible Calls clip.

    This is not semantic concordance: a clear different dispatch can still
    pass. It prevents a long vendor transcript from riding a tiny/silent file.
    """
    if wav is None or not wav.is_file():
        return "FDNY audio missing"
    try:
        import wave
        with wave.open(str(wav), "rb") as w:
            duration = w.getnframes() / w.getframerate()
            rate = w.getframerate()
            frames = w.readframes(min(w.getnframes(), rate * 15))
            width = w.getsampwidth()
        if width != 2:
            return "FDNY audio unsupported sample width"
        import array
        import math
        samples = array.array("h")
        samples.frombytes(frames[:len(frames) - len(frames) % 2])
        rms = int(math.sqrt(sum(v*v for v in samples) / len(samples))) if samples else 0
    except Exception:
        return "FDNY audio unreadable"
    words = len(re.findall(r"\b[\w'-]+\b", transcript))
    if duration < 2.0 or (words >= 12 and duration < words / 5.0):
        return f"FDNY transcript/clip duration mismatch ({words} words, {duration:.1f}s)"
    if rms < 80:
        return f"FDNY audio silent (rms {rms})"
    return ""


async def _fdny_handle_call(call: dict, stats: Stats, seen: dict, tmp: Path,
                            send_lock: asyncio.Lock | None = None,
                            correction_guard: CorrectionGuard | None = None) -> None:
    stats.mark_segment("fdny")
    cid = str(call.get("id") or call.get("filename") or int(time.time()))
    text = (call.get("transcription") or "").strip()
    stage_start = time.monotonic()
    url = call.get("audio_url") or ""
    fetch_task = None
    if url:
        tmp.mkdir(parents=True, exist_ok=True)
        fetch_task = asyncio.create_task(asyncio.to_thread(
            _fdny_fetch_clip, url, tmp / f"{cid}.m4a", tmp / f"{cid}.wav"))
    # Calls provides a transcription. Parse it while the audio downloads;
    # the WAV archive still completes before verification and any outbound post.
    hit = None
    if text:
        stats.mark_transcript("fdny", text)
        logging.info("[fdny] heard: %s", text[:160])
        await _kw_check("fdny", text)
        try:
            hit = detect.analyze(text, "fdny")
        except Exception as e:  # noqa: BLE001
            logging.warning("[fdny] detect failed: %s", e)
            stats.event("fdny", f"detect error: {e}")
    parsed_at = time.monotonic()
    wav = await fetch_task if fetch_task else None
    fetched_at = time.monotonic()
    if text:
        clip_problem = _fdny_clip_sanity(wav, text)
        if clip_problem:
            stats.event("fdny", "held: " + clip_problem)
            ops_log("held: " + clip_problem)
            if hit:
                stats.mark_alert("fdny", hit.get("nature", ""), hit.get("address", ""), False,
                                 failed=False, outcome="suppressed", reason=clip_problem)
            _fdny_call_record(call, text, None, hit, "suppressed", clip_problem)
            for suffix in (".m4a", ".wav"):
                (tmp / f"{cid}{suffix}").unlink(missing_ok=True)
            return
    if not text and wav is not None:
        text = await asyncio.to_thread(transcribe.transcribe, wav)
        if text:
            stats.mark_transcript("fdny", text)
            logging.info("[fdny] heard: %s", text[:160])
            await _kw_check("fdny", text)
            try:
                hit = detect.analyze(text, "fdny")
            except Exception as e:  # noqa: BLE001
                logging.warning("[fdny] detect failed: %s", e)
                stats.event("fdny", f"detect error: {e}")
    clip_name = None
    if wav is not None and text:
        clip_name = f"fdny-{int(time.time())}-{re.sub(r'[^A-Za-z0-9_-]', '_', cid)[:40]}.wav"
        await asyncio.to_thread(_archive_clip, wav, clip_name)
        stats.mark_clip("fdny", clip_name, text)
    archived_at = time.monotonic()
    for suffix in (".m4a", ".wav"):
        try:
            (tmp / f"{cid}{suffix}").unlink()
        except Exception:  # noqa: BLE001
            pass
    logging.info("[fdny] stages id=%s parsed=%.2fs fetched=%.2fs archived=%.2fs",
                 cid, parsed_at-stage_start, fetched_at-stage_start,
                 archived_at-stage_start)
    if not text:
        _fdny_call_record(call, "", clip_name, None, "skipped", "no transcription")
        stats.event("fdny", "call with no transcription - detect skipped")
        return
    if not hit:
        _fdny_call_record(call, text, clip_name, None, "skipped", "no parsed incident")
        return
    key = f"fdny|{hit['nature']}|{hit['address']}"
    now = time.time()
    if now - seen.get(key, 0) < DEDUP_SEC:
        logging.info("[fdny] deduped: %s @ %s", hit["nature"], hit["address"])
        stats.event("fdny", f"deduped: {hit['nature']} @ {hit['address']}")
        _fdny_call_record(call, text, clip_name, hit, "suppressed", "duplicate incident")
        return
    seen[key] = now
    _save_seen(seen)
    # Keep explicit address-conflict and numbered-cross guards. A spoken
    # apartment or floor alone does not hold the job; it is posted when heard,
    # and omitted when absent. Other unsupported dwelling/basement qualifiers
    # retain their independent-review gate.
    nature = hit.get("nature") or ""
    address = hit.get("address") or ""
    from fdny_borough_gate import spoken_borough_conflict, unnumbered_with_spoken_building
    conflict = spoken_borough_conflict(text, address)
    numbered_heard = unnumbered_with_spoken_building(text, address)
    hold_reason = (f"FDNY address says Brooklyn but dispatch says {conflict}"
                   if conflict else (f"FDNY dispatch gave a numbered building ({numbered_heard}) "
                                     "but the parsed address lost its number"
                                     if numbered_heard else ""))
    # A single Calls clip can contain two separate jobs. A global nature
    # classifier otherwise attaches the later job's complaint to the first
    # job's numbered address. Distinct spoken boxes are a conservative
    # boundary: hold rather than publish an unproven nature/address pairing.
    spoken_boxes = {m.group(1).zfill(4) for m in re.finditer(
        r"\bbox\s*[,;:]?\s*(\d{3,5})\b", text, re.I)}
    if not hold_reason and len(spoken_boxes) > 1:
        hold_reason = "FDNY clip contains multiple distinct box jobs; complaint/address pairing unverified"
    # A single vendor ASR reading can drop a digit in a numbered cross (East
    # 22nd -> East 2nd). Without a second audio recognizer on the free tier,
    # hold that location detail instead of publishing a false block.
    if not hold_reason and re.search(
            r"\b(?:East|West|North|South|E|W|N|S)\s+\d{1,3}(?:st|nd|rd|th)?\s+"
            r"(?:Street|St|Avenue|Ave|Road|Rd)\b", hit.get("cross") or "", re.I):
        hold_reason = "FDNY numbered cross street needs an independent audio check"
    # Vendor ASR can turn a second numbered house at a corner into a
    # plausible numbered cross (1615 8th Ave / 1632 Windsor Place was read
    # as 16th Street to Windsor Place). A map hit on the primary address
    # cannot authenticate that block. Hold the whole call for audio review.
    if not hold_reason and re.match(r"^\d+[A-Za-z-]*\s+\d+(?:st|nd|rd|th)?\s+"
            r"(?:Avenue|Street|Road|Place)\b", address, re.I) and re.match(
            r"^\d+(?:st|nd|rd|th)?\s+(?:Street|Avenue|Road|Place)\s*&\s*"
            r"[A-Za-z][A-Za-z ]+\s+(?:Place|Street|Avenue|Road)\b",
            hit.get("cross") or "", re.I):
        hold_reason = "FDNY numbered corner cross needs independent audio check"
    # A specific complaint in the vendor's own reading cannot be silently
    # replaced with a transmission-type fallback. Keep the audio for review.
    # This is active independently of the experimental second-ASR path.
    import fdny_audio_gate
    if not hold_reason and fdny_audio_gate.unclassified_fire_complaint(text, nature):
        hold_reason = "FDNY specific fire complaint unclassified; audio review required"
    # Bounded trial: only re-hear otherwise sendable weak fallback incidents.
    # Disabled until the independent service has a demonstrated success rate.
    # An unavailable pass cannot certify a post; the existing vendor/sender
    # gates remain in force when this trial is off.
    if (not hold_reason and os.environ.get("FDNY_WEAK_AUDIO_GATE", "0") == "1"
            and re.match(r"^(?:phone alarm|fire alarm|automatic alarm|alarm activation)\b", nature, re.I)):
        independent = ""
        if clip_name:
            try:
                independent = await asyncio.wait_for(asyncio.to_thread(
                    transcribe.second_listen, ARCHIVE_DIR / clip_name, "fdny"), timeout=25)
            except Exception as exc:
                logging.warning("[fdny] independent check failed (%s)", type(exc).__name__)
        reason = fdny_audio_gate.compare_weak_fdny(hit, independent)
        if reason:
            hold_reason = reason
    if not hold_reason and re.search(r"\b(?:basement|cellar|dwelling)\b", nature, re.I):
        hold_reason = "FDNY dwelling detail needs independent audio check"
    elif not hold_reason and re.fullmatch(r"\d{1,5}\s+[A-Za-z][A-Za-z' -]+?\s+"
                      r"(?:Street|Avenue|Road|Place|Drive|Court), (?:Brooklyn|Queens|Manhattan|Bronx|Staten Island), NY", address, re.I):
        try:
            verified_street = bool((await geocode_verify(address, "fdny"))[0])
        except Exception:
            verified_street = False
        if not verified_street:
            hold_reason = "FDNY street spelling needs independent audio check"
    if hold_reason:
        hit["hold_reason"] = hold_reason
        # Rescue only the narrow map-failed named-house case, while live.
        # Other holds (mixed jobs, borough, numbered cross, etc.) stay held.
        if hold_reason == "FDNY street spelling needs independent audio check" and wav is not None:
            try:
                rescue = await _fdny_recover_held_street(
                    hit, wav, stats, call, clip_name or "", send_lock,
                    correction_guard)
            except Exception as exc:  # never turn a recovery error into a send
                logging.warning("[fdny] held street second listen failed: %s", exc)
                rescue = "suppressed"
            if rescue == "sent":
                stats.event("fdny", f"held street rescued by second listen: {address}")
                stats.mark_alert("fdny", nature, hit["address"], True,
                                 outcome="sent", voice_url=hit.get("voice_url", ""))
                _append_alert_log({"t": now, "feed": "fdny", "nature": nature,
                                   "address": hit["address"], "sent": True,
                                   "excerpt": hit["excerpt"]})
                _fdny_call_record(call, text, clip_name, hit, "sent", "second listen")
                return
        stats.event("fdny", f"held ({hold_reason}): {nature} @ {address}")
        ops_log(f"held ({hold_reason}): {nature} @ {address}")
        hit["voice_url"] = await _held_recording(clip_name)
        await _post_held_review("fdny", hit, clip_name)
        stats.mark_alert("fdny", nature, address, False, failed=False, outcome="suppressed",
                         voice_url=hit.get("voice_url", ""), reason=hold_reason)
        _append_alert_log({"t": now, "feed": "fdny", "nature": nature,
                           "address": address, "sent": False, "excerpt": hit["excerpt"]})
        _fdny_call_record(call, text, clip_name, hit, "suppressed", hold_reason)
        return
    try:
        call_ts = float(call.get("ts") or 0) or None
        audio_start = float(call.get("audio_start_ts") or 0) or None
    except Exception:  # noqa: BLE001
        call_ts = audio_start = None
    verify_start = time.monotonic()
    outcome = await verify_and_send("fdny", hit, stats, clip_name,
                                    fresh_ts=call_ts, audio_ts=audio_start,
                                    send_lock=send_lock, correction_guard=correction_guard,
                                    source_call=call)
    logging.info("[fdny] stages id=%s verify_send=%.2fs total=%.2fs outcome=%s",
                 cid, time.monotonic()-verify_start, time.monotonic()-stage_start, outcome)

    ok = outcome == "sent"
    if outcome == "suppressed":
        hit["voice_url"] = await _held_recording(clip_name)
        await _post_held_review("fdny", hit, clip_name)
    stats.mark_alert("fdny", hit["nature"], hit["address"], ok,
                     failed=(outcome == "queued"), outcome=outcome,
                     voice_url=hit.get("voice_url", ""), reason=hit.get("hold_reason", ""))
    _append_alert_log({"t": now, "feed": "fdny", "nature": hit["nature"],
                       "address": hit["address"], "sent": ok,
                       "excerpt": hit["excerpt"]})
    _fdny_call_record(call, text, clip_name, hit, outcome, hit.get("hold_reason", ""))
    logging.info("[fdny] ALERT %s @ %s - sent=%s", hit["nature"], hit["address"], ok)


async def fdny_consumer(stats: Stats, seen: dict) -> None:
    """Process distinct Calls with a small concurrency bound. Only the
    outbound text+voice pair uses a lock, so no other call may interleave it.
    The queue is drained continuously while slow map/CDN work runs elsewhere.
    """
    ids: dict = _load_json(FDNY_IDS, {})
    offset = 0
    tmp = SEG_DIR / "fdny_tmp"
    limit = asyncio.Semaphore(3)
    send_lock = asyncio.Lock()
    correction_guard = CorrectionGuard()
    active: set = set()

    async def worker(call: dict, cid: str, queued_at: float) -> None:
        async with limit:
            logging.info("[fdny] queue id=%s wait=%.2fs source_stop_age=%.2fs",
                         cid, time.monotonic()-queued_at,
                         time.time()-float(call.get("ts") or time.time()))
            try:
                # The shared dedup state stays in the event loop. Each alert
                # gets its own temp files by cid, with a send lock only at the
                # final WhatsApp text/voice pair inside verify_and_send.
                await _fdny_handle_call(call, stats, seen, tmp, send_lock=send_lock,
                                        correction_guard=correction_guard)
            except Exception as e:  # noqa: BLE001
                logging.warning("[fdny] worker id=%s failed: %s", cid, e)

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
                    valid_calls = []
                    for line in chunk.splitlines():
                        try:
                            call = json.loads(line)
                        except Exception:  # noqa: BLE001
                            continue
                        if isinstance(call, dict):
                            valid_calls.append(call)
                    # Index explicit address corrections for the whole poller
                    # burst before any of its Calls workers may send.
                    for box, old_addr, new_addr in correction_guard.ingest(valid_calls):
                        reason = (f"FDNY correction after sent Box {box}: "
                                  f"{old_addr} -> {new_addr}; review, no automatic repost")
                        stats.event("fdny", reason)
                        logging.warning("%s", reason)
                        # This is an exception, not a routine ops digest: an
                        # already-posted address may be wrong for responders.
                        _OPS_TASKS.append(asyncio.create_task(
                            alert_waha.send_ops("⚠️ " + reason)))
                    for call in valid_calls:
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
                        task = asyncio.create_task(worker(call, cid, time.monotonic()))
                        active.add(task)
                        task.add_done_callback(active.discard)
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
    stats.groq_enabled = transcribe.GROQ_ENABLED
    stats.groq_key_present = bool(transcribe.GROQ_KEY)
    logging.info("Groq second listener: enabled=%s key_present=%s",
                 stats.groq_enabled, stats.groq_key_present)
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
        *(ptt_consumer(p, stats, seen) for p in zello_ingest.CHANNELS),
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
