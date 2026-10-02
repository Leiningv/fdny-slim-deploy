"""Verify a directly spoken FDNY cross against OSM street geometry, bounded."""
import asyncio
import math
import re
import xml.etree.ElementTree as ET
import aiohttp


def _road(s):
    s=s.lower().strip()
    s=re.sub(r'\b(\d+)(?:st|nd|rd|th)\b',r'\1',s)
    for pat,repl in [(r'\bavenue\b','ave'),(r'\bstreet\b','st'),(r'\broad\b','rd'),(r'\bboulevard\b','blvd')]:
        s=re.sub(pat,repl,s)
    return s


def normalize_pair(sides):
    """Expand an explicitly spoken shared road type, never a map guess."""
    if len(sides) != 2:
        return sides
    sides = list(sides)
    types = {"avenues": "Avenue", "streets": "Street", "roads": "Road",
             "places": "Place", "boulevards": "Boulevard", "drives": "Drive",
             "lanes": "Lane", "courts": "Court", "parkways": "Parkway"}
    for i, side in enumerate(sides):
        m = re.search(r"\b(" + "|".join(types) + r")$", side, re.I)
        if m:
            sides[i] = side[:m.start()] + types[m.group(1).lower()]
    explicit = re.search(r"\b(Avenue|Street|Road|Place|Boulevard|Drive|Lane|Court|Parkway|Ave|St|Rd|Pl)$",
                         sides[1], re.I)
    if explicit and re.fullmatch(r"(?:[A-Za-z][A-Za-z.'-]+|\d+(?:st|nd|rd|th))", sides[0], re.I):
        sides[0] += " " + explicit.group(1)
    return sides


_TYPES = {"ave", "st", "rd", "blvd", "pl", "dr", "ct", "ln", "pkwy", "hwy", "ter", "way", "sq", "expy"}
_MAP_CACHE: dict = {}


def _lev1(a: str, b: str) -> bool:
    """True when a and b differ by at most one insert, delete or substitution."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def same_road(heard: str, mapped: str) -> bool:
    """Exact normalized match, or a one-letter spelling slip in the name
    ("Green Avenue" heard, "Greene Avenue" mapped). Same road type required,
    numbered streets must match exactly, and short names must match exactly."""
    a, b = _road(heard), _road(mapped)
    if not a or not b:
        return False
    if a == b:
        return True
    a = a.replace("'", "").replace(".", "")
    b = b.replace("'", "").replace(".", "")
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    if len(ta) < 2 or len(tb) < 2 or ta[-1] != tb[-1] or ta[-1] not in _TYPES:
        return False
    na, nb = " ".join(ta[:-1]), " ".join(tb[:-1])
    if re.search(r"\d", na + nb):
        return False
    if len(na) < 5 or len(nb) < 5:
        return False
    return _lev1(na, nb)


async def _fetch_map(bbox: str):
    """OSM map XML for bbox, cached briefly so two crosses cost one download."""
    import time
    hit = _MAP_CACHE.get(bbox)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    async with aiohttp.ClientSession(headers={"User-Agent": "fdny-slim/1.0 (dispatch cross check)"}) as s:
        async with s.get('https://www.openstreetmap.org/api/0.6/map', params={'bbox': bbox},
                         timeout=aiohttp.ClientTimeout(total=9)) as r:
            if r.status != 200:
                return None
            blob = await r.read()
            if len(blob) > 3_000_000:
                return None
    if len(_MAP_CACHE) > 20:
        _MAP_CACHE.clear()
    _MAP_CACHE[bbox] = (time.time(), blob)
    return blob


async def verify(street: str, cross: str, lat: float, lon: float) -> bool:
    """True iff distinct named road ways share a node within 250m of address.
    Names match exactly or with a one-letter spelling slip (same_road).
    A source/map failure is NOT a pass: it returns False. Display only.
    """
    if not street or not cross or lat is None or lon is None:
        return False
    delta_lat = 0.0027
    delta_lon = 0.0036
    # Round the box so the two crosses of one call share a single download.
    bbox = f'{round(lon-delta_lon, 4)},{round(lat-delta_lat, 4)},{round(lon+delta_lon, 4)},{round(lat+delta_lat, 4)}'
    try:
        blob = await _fetch_map(bbox)
        if not blob:
            return False
        root = ET.fromstring(blob)
    except Exception:
        return False
    coords = {n.attrib['id']: (float(n.attrib['lat']), float(n.attrib['lon'])) for n in root.findall('node')}
    if _road(street) == _road(cross):
        return False
    a_nodes, b_nodes = set(), set()
    for way in root.findall('way'):
        tags = {x.attrib['k']: x.attrib['v'] for x in way.findall('tag')}
        name = tags.get('name', '')
        if not name or not tags.get('highway'):
            continue
        refs = [x.attrib['ref'] for x in way.findall('nd')]
        if same_road(street, name):
            a_nodes.update(refs)
        if same_road(cross, name) and not same_road(street, name):
            b_nodes.update(refs)
    for node in a_nodes & b_nodes:
        if node not in coords:
            continue
        a, b = coords[node]
        dlat = (a - lat) * 110540
        dlon = (b - lon) * 111320 * math.cos(math.radians(lat))
        if math.hypot(dlat, dlon) <= 250:
            return True
    return False
