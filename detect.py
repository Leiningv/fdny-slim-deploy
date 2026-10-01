"""Detection for fdny-slim: emergency patterns, nature classification, address extraction.

Simplified port of the useful logic from fdny_monitor_full.py (read-only reference).
Two source profiles: "hatzolah" (Brooklyn) and "sullivan" (Sullivan County).
"""
from __future__ import annotations

import logging
import re

# ---------------------------------------------------------------------------
# Emergency patterns (ported from the original EMERGENCY_PATTERNS)
# ---------------------------------------------------------------------------
EMERGENCY_PATTERNS = [
    r"\b(?:box|alarm)\s+\d+",
    r"\b(?:10-75|10-76|10-77|10-78|10-18|10-33|10-32|all hands|second alarm|people trapped)\b",
    r"\b(?:smoke|fire|structure|gas|leak)\b",
    r"\b(?:mva|accident|collision|rollover|entrapment|crash|wreck|mvc)\b",
    r"\b(?:members?\s+respond|respond(?:ing)?\s+to)\b",
    r"\b(?:cardiac|arrest|ems|hatzalah|hatz|medical|medic)\b",
    r"\b(?:ped\s+struck|pedestrian|cyclist\s+struck|bicyclist\s+struck|not breathing|unconscious|choking|seizure|stroke|cva|convul|heart\s+attack)\b",
    r"\b(?:difficulty|difficulties)\s+breath",
    r"\brespiratory\s+distress\b",
    r"\b(?:address|avenue|street|ave|st)\s+\d+|\d+\s+(?:avenue|street|ave|st)\b",
    r"\b\d{1,5}\s+[a-z][a-z'\-\s]{1,28}\s+(?:ave|avenue|street|st|road|rd|drive|dr|blvd|boulevard|pkwy|parkway|lane|ln|place|pl)\b",
    r"\b(?:pet|pad|ped)\s+(?:struck|strike|stricken|hit|stroke)\b",
    r"\b(?:auto|vehicle)\s+ped\b",
    r"\bped\s+vs\b",
    r"\b(?:division|unit)\s+\d+|\d+\s+(?:division|unit)\b",
    r"\b(?:child|children|kid|kids|baby|babies|infant|juvenile|toddler|pediatric|pedietric|pedeiateic)\s+(?:struck|stricken|hit|run\s*over|runover)\b",
    r"\b(?:struck|hit)\s+(?:a\s+)?(?:child|children|kid|kids|baby|babies|infant|juvenile|toddler)\b",
    r"\b(?:child|pediatric|pedietric|pedeiateic)\s+(?:not\s+)?(?:breathing|unresponsive|unconscious|drowned|turning\s+blue)\b",
    r"\b(?:patient|pationt)\s+(?:not\s+)?(?:breathing|unresponsive|unconscious|turning\s+blue)\b",
    r"\b(?:possible|posible)\s+(?:fire|code)\b",
    r"\b(?:report\s+of\s+)?(?:a\s+)?fire\b",
    r"\b(?:priority|priorty|prioity|prioroty)\s+(?:dispatch|dispach|call|job|ems|e\s*m\s*s)\b",
    r"\b(?:echo\s+level|signal\s*8|hot\s+run|urgent\s+(?:dispatch|response)|stat\s+(?:run|call|job))\b",
    r"\b(?:red\s+alert|immediate\s+response|lights\s+and\s+sirens)\b",
    r"\b(?:respond(?:ing)?\s+(?:to|on)|response\s+to|assignment\s+for|nature\s+of\s+(?:the\s+)?(?:call|emergency))\b",
    r"\b(?:cross\s+of|corner\s+of|between|intersection\s+of)\b",
    r"\b(?:turnpike|parkway|terrace|boulevard|drive|lane|court|place)\b",
    r"\b(?:hatzalah|hatz|chevra)\s+(?:to|on|at)\b",
    r"\b(?:allergic|anaphylaxis|epi\s*pen|overdose|unresponsive|syncope|fall|bleeding|abdominal)\b",
    r"\b(?:full\s+trauma|trauma|traumatic)\b",
    r"\b(?:general(?:ly)?\s+ill|general\s+illness)\b",
    r"\b(?:tree|trees|limb|branch).{0,35}(?:wire|wires|power\s*line|utility\s*line).{0,35}(?:down|burn|burning|fallen|arcing|spark)\b",
    r"\b(?:wire|wires|power\s*line).{0,35}(?:tree|trees|limb|branch).{0,35}(?:down|burn|burning|fallen)\b",
    r"\btree\s+(?:and|&)\s+wires?\s+(?:down|burning)\b",
    r"\btree\s+down\s+on\s+wires?\b",
    r"\btree(?:s)?\s+(?:on|into|over|across)\s+(?:the\s+)?(?:wire|wires|power\s*line)s?\b",
]


def is_emergency(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in EMERGENCY_PATTERNS)


# ---------------------------------------------------------------------------
# Service areas
# ---------------------------------------------------------------------------
BERGEN_AREAS = {
    "fair lawn": "Fair Lawn", "teaneck": "Teaneck", "englewood": "Englewood",
    "bergenfield": "Bergenfield", "fort lee": "Fort Lee", "tenafly": "Tenafly",
    "paramus": "Paramus", "hackensack": "Hackensack", "ridgefield": "Ridgefield",
    "alpine": "Alpine", "closter": "Closter",
}

FIVE_TOWNS_AREAS = {
    "woodmere": "Woodmere",
    "woodmare": "Woodmere",  # whisper variant on scratchy audio
    "five-town": "Five Towns",
    "lawrence": "Lawrence",
    "cedarhurst": "Cedarhurst",
    "inwood": "Inwood",
    "hewlett": "Hewlett",
    "atlantic beach": "Atlantic Beach",
    "five towns": "Five Towns",
    "far rockaway": "Far Rockaway",
    "valley stream": "Valley Stream",
    "lynbrook": "Lynbrook",
}


def _rego_saunders_corner(text: str) -> bool:
    """Only the audio-grounded Rego Park / Saunders / 64 Road dispatch shape.
    The observed Queen Trigo Park ASR variant is not a general Queens alias.
    Both roads remain subject to the sender's intersection verification.
    """
    return bool(re.search(r"\b(?:in\s+)?Queens?\s*,?\s*(?:Rego|Trigo)\s+Park\s*,?\s+Saunders(?:\s+Street)?\s+(?:and|&)\s+64(?:th)?\s+Road\b", text, re.I))


def spoken_hatzalah_locality(text: str) -> str:
    """Job-local named places, not a unit origin or a town-named road.

    South Folsburg is the observed initial read, independently repeated as
    South Fallsburg. No broad phonetic town guessing.
    """
    places = {**BERGEN_AREAS, **FIVE_TOWNS_AREAS,
              **{k: v for k, v in SULLIVAN_AREAS.items()
                 if k in ("south fallsburg", "woodridge", "woodbourne", "monticello", "liberty", "loch sheldrake")},
              "south folsburg": "S Fallsburg", "bayswater": "Queens",
              "crown heights": "Brooklyn"}
    for name in sorted(places, key=len, reverse=True):
        place = re.escape(name)
        if re.search(r"\b(?:in|near|at|for|town of|village of)\s+" + place +
                     r"\b(?!\s+(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Place|Pl)\b)", text, re.I):
            # A responding unit's origin cannot relabel the incident.
            if re.search(r"\b(?:unit|engine|member|medic)\s+(?:is\s+)?(?:in|at)\s+" + place, text, re.I):
                continue
            return places[name]
    # An explicitly named town need not be on a global neighborhood list.
    # Capture only a dispatch request's area slot before its location; never
    # a unit origin, an apparatus destination, or a road-named "town".
    generic = re.search(
        r"\b(?:any\s+(?:units?|assistance)(?:\s+available)?|dispatch|(?:the\s+)?(?:job|call|location)\s+is)"
        r"\s+(?:in|at|for)\s+(?:the\s+(?:town|village|area)\s+of\s+)?"
        r"([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,3}?)"
        r"(?=\s+(?:for|from|at|near|in front of)\b|\s*,)", text, re.I)
    if generic:
        name = generic[1].strip()
        if len(name) >= 3 and not re.fullmatch(r"(?:the\s+)?[A-Za-z]|town|the area", name, re.I) and not re.search(r"\b(?:unit|bus|medic|backup|back up|Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Place|Pl|Parkway|Pkwy)\b", name, re.I):
            # Known county/borough aliases keep their established handling.
            return places.get(name.lower(), name.title())
    return ""


def get_hatzolah_area(text: str) -> str:
    """TSL-ChevraHatzalah mixes NYC divisions AND Sullivan County - trust the
    place names in the dispatch itself to set the area (user rule 9/28)."""
    t = text.lower()
    explicit = spoken_hatzalah_locality(text)
    if explicit:
        return explicit
    if _rego_saunders_corner(text):
        return "Queens"
    if re.search(r"\b(?:in|for|near|at)\s+Bayswater\b|\bBayswater\s+for\b", text, re.I):
        return "Queens"
    if re.search(r"\b(?:west\s*side|manhattan)\b",t) and not re.search(r"\bmanhattan beach\b",t):
        return "Manhattan"
    # This complete spoken Beach-number/Rockaway pair is a Queens location,
    # never Brooklyn's default. Sender still verifies both roads together.
    if re.search(r"\bRockaway Beach (?:Boulevard|Blvd)\s+(?:and|at|&)\s+Beach\s+\d{1,3}(?:st|nd|rd|th)?\b", t, re.I):
        return "Queens"
    # Explicitly excluded Rockland locations cannot inherit Brooklyn's
    # default area. The final coverage gate suppresses these.
    if re.search(r"\b(?:rockland|monsey|spring valley|new square|suffern|haverstraw|garnerville|airmont|chestnut ridge)\b", t):
        return "Rockland"
    for k, v in SULLIVAN_AREAS.items():
        if k in t:
            # "Liberty Avenue" is Brooklyn, not Sullivan's Liberty / Old Liberty Road
            if k == "liberty" and re.search(r"liberty\s+(?:ave|avenue)", t):
                continue
            return v
    for k, v in BERGEN_AREAS.items():
        if re.search(rf"\b(?:in|near|at|village of|town of)\s+{re.escape(k)}\b", t) or \
                re.search(rf"\b{re.escape(k)}\s*,?\s+(?:nj|new jersey)\b", t):
            return v
    # A job-local Westbury address must not inherit Brooklyn's default.
    # Only an explicit place phrase counts; a responding unit, street name,
    # or substring is not enough. The sender still verifies Nassau county
    # and the precise town against a live geocoder before posting.
    if re.search(r"\b(?:in|at|near|village of|town of)\s+(?:the\s+area\s+of\s+)?westbury\b", t):
        return "Westbury"
    if re.search(r"\b(?:in|at|near|village of|town of)\s+(?:the\s+area\s+of\s+)?wentbury\b", t):
        return "Westbury"  # observed ASR repeat of the same Westbury job
    # A chapter/unit named Queens may respond across the Nassau line. A
    # dispatch-local "in Great Neck" names the JOB, not the responding unit.
    if re.search(r"\bin\s+(?:great|grape)\s+neck\b", t):
        return "Great Neck"
    for k, v in FIVE_TOWNS_AREAS.items():
        if k in t:
            return v
    for neighborhood, region in (("kew gardens", "Queens"), ("forest hills", "Queens"),
                                 ("rego park", "Queens"), ("flushing", "Queens"),
                                 ("glendale", "Queens"), ("manhattan beach", "Brooklyn")):
        if re.search(rf"\b{re.escape(neighborhood)}\b", t):
            # A road named Flushing Avenue is not the Queens neighborhood;
            # let an explicit borough or verified map point decide instead.
            if neighborhood == "flushing" and re.search(r"\bflushing\s+(?:avenue|ave)\b", t):
                continue
            return region
    for name in ("Staten Island", "Riverdale", "Manhattan", "Brooklyn", "Queens", "Bronx"):
        pattern = (r"\bmanhattan\b(?!\s+beach)" if name == "Manhattan"
                   else rf"\b{re.escape(name.lower())}\b")
        if re.search(pattern, t):
            return name
    return "Brooklyn"


SULLIVAN_AREAS = {
    "windsor hills estates": "Windsor Hills Estates",
    "windsor hills": "Windsor Hills Estates",
    "windy real estate": "Windsor Hills Estates",  # whisper variant, verified 9/28
    "petaluga": "Monticello",  # Petaluga Drive is in Monticello
    "south fallsburg": "S Fallsburg",
    "woodridge": "Woodridge",
    "woodbourne": "Woodbourne",
    "monticello": "Monticello",
    "liberty": "Liberty",
    "lock sheltering": "Loch Sheldrake",  # observed Groq ASR variant
    "lock sheldrake": "Loch Sheldrake",
    "lock sheldrick": "Loch Sheldrake",  # whisper variant, verified 9/28
    "loch sheldrake": "Loch Sheldrake",
    "ganser": "Loch Sheldrake",  # Ganser Road is in Loch Sheldrake
    "blue maple": "Loch Sheldrake",  # Blue Maple Estates, Loch Sheldrake
}

# Brooklyn-relevant highways (trimmed from NYC_HIGHWAYS; whisper variants kept)
NYC_HIGHWAYS = {
    "bqe": "BQE",
    "brooklyn queens expressway": "BQE",
    "belt": "Belt Pkwy",
    "bell": "Belt Pkwy",  # Whisper often hears "bell" for "belt"
    "belt parkway": "Belt Pkwy",
    "gowanus": "Gowanus Expwy",
    "gowanus expressway": "Gowanus Expwy",
    "prospect": "Prospect Expwy",
    "prospect expressway": "Prospect Expwy",
    "jackie robinson": "Jackie Robinson Pkwy",
    "atlantic": "Atlantic Ave",
    "flatbush": "Flatbush Ave",
    "kings highway": "Kings Hwy",
    "kings hwy": "Kings Hwy",
    "ocean parkway": "Ocean Pkwy",
    "conduit": "Conduit Ave",
    "cross bay": "Cross Bay Blvd",
    "woodhaven": "Woodhaven Blvd",
}

NYC_BRIDGES = {
    "verrazzano": "Verrazzano-Narrows Bridge",
    "verrazano": "Verrazzano-Narrows Bridge",
    "brooklyn bridge": "Brooklyn Bridge",
    "manhattan bridge": "Manhattan Bridge",
    "williamsburg bridge": "Williamsburg Bridge",
    "marine parkway": "Marine Parkway Bridge",
}

# Sullivan County highways (full port; whisper variants kept)
SULLIVAN_HIGHWAYS = {
    "route 17b": "Route 17B",
    "rt 17b": "Route 17B",
    "17b": "Route 17B",
    "route 17": "Route 17",
    "rt 17": "Route 17",
    "rte 17": "Route 17",
    "quickway": "Route 17",
    "route 42": "Route 42",
    "rt 42": "Route 42",
    "route 52": "Route 52",
    "rt 52": "Route 52",
    "route 55": "Route 55",
    "rt 55": "Route 55",
    "route 97": "Route 97",
    "rt 97": "Route 97",
    "route 209": "Route 209",
    "rt 209": "Route 209",
}

_STREET_ABBREV = {
    "avenue": "Ave", "ave": "Ave", "street": "St", "st": "St",
    "road": "Rd", "rd": "Rd", "drive": "Dr", "dr": "Dr",
    "boulevard": "Blvd", "blvd": "Blvd", "place": "Pl", "pl": "Pl",
    "lane": "Ln", "ln": "Ln", "court": "Ct", "ct": "Ct",
    "terrace": "Ter", "ter": "Ter", "parkway": "Pkwy", "pkwy": "Pkwy",
    "circle": "Cir", "cir": "Cir", "highway": "Hwy", "hwy": "Hwy",
}

_ORDINAL_WORDS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th",
    "fifth": "5th", "sixth": "6th", "seventh": "7th", "eighth": "8th",
    "ninth": "9th", "tenth": "10th", "eleventh": "11th", "twelfth": "12th",
    "thirteenth": "13th", "fourteenth": "14th", "fifteenth": "15th",
    "sixteenth": "16th", "seventeenth": "17th", "eighteenth": "18th",
    "nineteenth": "19th", "twentieth": "20th",
}
_ORD_WORD_RE = "|".join(_ORDINAL_WORDS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_MISHEAR_RE = re.compile(r"\bone floor\b(?=\s+(?:between|and)\s+\d)", re.I)


def _norm(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "")).strip()
    # "one floor" is a verified mishearing of "14" in Boro Park avenue shorthand (9/28)
    return _MISHEAR_RE.sub("14", t)


def _ordinal_street_num(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{'st' if n % 10 == 1 else 'nd' if n % 10 == 2 else 'rd' if n % 10 == 3 else 'th'}"


def _addr_title(s: str) -> str:
    """title() that keeps ordinals lowercase: '53rd street' -> '53rd Street'
    (str.title gives '53Rd' - shipped in the 6:01 AM 53rd St post 9/28)."""
    t = s.title()
    t = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)
    t = re.sub(r"'S\b", "'s", t)
    t = re.sub(r"(?<!^)\b(In|An?|Of|The|And|Or|At|On|For)\b",
               lambda m: m.group(1).lower(), t)
    return t


def _format_cross_street_part(num_ord: str, street_type: str) -> str:
    num_ord = num_ord.strip()
    if not num_ord:
        return ""
    abbrev = _STREET_ABBREV.get(street_type.lower().strip(), street_type.title())
    return f"{num_ord} {abbrev}".strip() if abbrev else num_ord


def _highways_for(profile: str) -> dict:
    return SULLIVAN_HIGHWAYS if profile == "sullivan" else {**NYC_HIGHWAYS, **NYC_BRIDGES}


def _find_highway(t: str, profile: str) -> tuple[str | None, str | None]:
    """Return (keyword, display) for earliest highway found. Longer keys first."""
    best: tuple[int, str, str] | None = None
    for k, v in sorted(_highways_for(profile).items(), key=lambda x: -len(x[0])):
        if k == "lie":
            m = re.search(r"(?<![a-z0-9])lie(?![a-z0-9])", t)
            idx = m.start() if m else -1
        else:
            idx = t.find(k)
        if idx >= 0 and (best is None or idx < best[0]):
            best = (idx, k, v)
    return (best[1], best[2]) if best else (None, None)


def extract_highway_intersection(text: str, profile: str = "hatzolah") -> str | None:
    """Highway + detail: 'Route 17 at Exit 104', 'Belt Pkwy at 6th Ave', 'BQE SB'."""
    t = _norm(text).lower()
    kw, hwy = _find_highway(t, profile)
    if not hwy:
        return None
    # 'prospect avenue' is the street, not the Prospect Expressway: an alias
    # keyword directly followed by a non-highway street type is that street
    if re.search(
            rf"\b{re.escape(kw)}\s+(?:avenue|ave|street|st|road|rd|boulevard|"
            rf"blvd|drive|dr|place|pl|lane|ln|court|ct|terrace|ter)\b", t):
        return None
    # [highway] at exit N
    m = re.search(rf"{re.escape(kw)}[^.]*?(?:at\s+)?exit\s+(\d{{1,3}}[a-z]?)\b", t)
    if m:
        return f"{hwy} at Exit {m.group(1).upper()}"
    m = re.search(r"exit\s+(\d{1,3}[a-z]?)[^.]*?" + re.escape(kw), t)
    if m:
        return f"{hwy} at Exit {m.group(1).upper()}"
    # [highway] near [town]
    m = re.search(
        rf"{re.escape(kw)}[^.]{{0,80}}(?:heading\s+)?(?:towards?|near|by)\s+"
        r"(monticello|liberty|woodridge|south fallsburg|woodbourne|fallsburg)",
        t,
    )
    if m:
        return f"{hwy} near {SULLIVAN_AREAS.get(m.group(1), m.group(1).title())}"
    # [highway] at/near [other highway]
    for other_k, other_v in _highways_for(profile).items():
        if other_v == hwy or other_k in kw or kw in other_k:
            continue
        for phrase in [" at ", " near ", " approaching "]:
            if phrase in t and other_k in t:
                i1, i2 = t.find(kw), t.find(other_k)
                if i1 >= 0 and i2 >= 0 and abs(i1 - i2) < 100:
                    return f"{hwy} {phrase.strip().title()} {other_v}"
    # direction suffix
    idx = t.find(kw)
    chunk = t[max(0, idx - 30): idx + len(kw) + 80]
    for word, abbr in (("southbound", "SB"), ("northbound", "NB"),
                       ("eastbound", "EB"), ("westbound", "WB")):
        if word in chunk:
            return f"{hwy} {abbr}"
    # bare highway only if it is not a numbered surface street corridor
    if idx > 0 and re.search(r"\d{1,5}\s+$", t[:idx]):
        return None  # "7814 rockaway boulevard" is a house address, not a highway
    # 'any units in East Flatbush' is the neighborhood, not 'Flatbush Ave':
    # a bare highway keyword after 'in/to/from' or a directional word is a
    # place reference, not the road
    pre = t[max(0, idx - 16):idx].strip()
    if re.search(r"(?:^|\s)(?:in|into|to|from|east|west|north|south)\s+$",
                 " " + pre + " "):
        return None
    return hwy


def extract_cross_street(text: str) -> str | None:
    """'13th avenue and 50th street' -> '13th Ave & 50th St'; '14 and 46' -> '14th Ave & 46th St'."""
    t = _norm(text).lower()
    stypes = r"(ave|avenue|st|street|blvd|boulevard|rd|road|dr|drive|pl|place|ln|lane|ct|court|pkwy|parkway)"
    num = rf"(?:\d{{1,3}}(?:st|nd|rd|th)?|{_ORD_WORD_RE})"
    m = re.search(
        rf"(?<![\d-])(?P<n1>{num})\s+(?P<t1>{stypes})\s+(?:and|at|@|&)\s+(?P<n2>{num})\s+(?P<t2>{stypes})\b",
        t, re.I,
    )
    if m:
        n1 = _ORDINAL_WORDS.get(m.group("n1").lower(), m.group("n1"))
        n2 = _ORDINAL_WORDS.get(m.group("n2").lower(), m.group("n2"))
        p1 = _format_cross_street_part(n1, m.group("t1"))
        p2 = _format_cross_street_part(n2, m.group("t2"))
        if p1 and p2:
            return f"{p1} & {p2}"
    # Boro Park bare-number shorthand: "14 between 50 and 51" -> 14th Ave between 50th & 51st St
    m = re.search(r"(?<![\d-])(\d{1,2})\s+between\s+(\d{1,3})\s+and\s+(\d{1,3})(?!\d)", t)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= a <= 25 and 1 <= b <= 199 and c == b + 1:
            return (f"{_ordinal_street_num(a)} Ave between "
                    f"{_ordinal_street_num(b)} & {_ordinal_street_num(c)} St")
    # Bare grid shorthand only counts in the location phrase itself. A later
    # unit readout ("62 and 47 is by the car") cannot become an intersection
    # merely because another part of the recording contains a complaint.
    m = re.search(r"\b(?:for|at|on|in|to|respond[,]?)\s+(\d{1,2})\s+and\s+(\d{1,2})(?!\d)", t)
    if m:
        # Even with "for", a radio unit pair may be read in the same
        # multi-job chunk. If a named location and its house-number anchor
        # appear, never let an unrelated bare pair outrank that location.
        named_anchor = re.search(
            r"\b(?:for|at|on|to)\s+[A-Za-z][A-Za-z'-]+\s+and\s+"
            r"[A-Za-z][A-Za-z'-]+\b", t) and re.search(
            r"\b\d{1,5}\s*,?\s+[A-Za-z][A-Za-z'-]+\b", t)
        tail = t[m.end():m.end()+36]
        unit_tail = re.match(r"\s+(?:is\s+by|are\s+by|\w+\s+(?:respond|copy)|units?\b)", tail)
        if not named_anchor and not unit_tail:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= 99 and 1 <= b <= 99 and a != b:
                lo, hi = min(a, b), max(a, b)
                return f"{_ordinal_street_num(lo)} Ave & {_ordinal_street_num(hi)} St"
    return None


def extract_house_address(text: str) -> str | None:
    """'responding to 5014 15th avenue' -> '5014 15th Ave'."""
    t = _norm(text).lower()
    m = re.search(
        r"\b(\d{1,5})\s+((?:east|west|north|south)\s+\d{1,3}(?:st|nd|rd|th)|"
        r"\d{1,3}(?:st|nd|rd|th)?)\s+"
        r"(avenue|ave|street|st|road|rd|drive|dr|boulevard|blvd|place|pl|lane|ln)\b",
        t,
    )
    if m:
        street = m.group(2)
        typ = {"st": "street", "ave": "avenue", "rd": "road", "dr": "drive",
               "blvd": "boulevard", "pl": "place", "ln": "lane"}.get(
                   m.group(3).lower(), m.group(3))
        return f"{m.group(1)} {_addr_title(f'{street} {typ}')}"
    return None


_NAME_STOP = {
    "the", "a", "an", "for", "on", "to", "in", "at", "and", "or", "is", "it",
    "be", "unit", "units", "engine", "ladder", "battalion", "rescue", "squad",
    "truck", "box", "alarm", "phone", "still", "code", "signal", "from",
    "with", "of", "by", "go", "no", "we", "you", "your", "rd", "st", "nd",
    "th", "ave", "man", "that", "thats", "that's", "off", "corner", "near",
    "next", "up", "out", "just", "right", "fire", "smoke", "it's", "its",
}


def _ok_name(n: str) -> bool:
    ws = n.split()
    if len(n) < 2 or not ws or any(w in _NAME_STOP for w in ws):
        return False
    return all(w not in ("rd", "st", "nd", "th", "ave") for w in ws)


_STREET_TYPE = r"(?:street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|place|pl|lane|ln|parkway|pkwy|highway|hwy|court|ct|terrace|ter|way|circle|cir)"
_VERB_BEFORE_TO = re.compile(r"\b(?:respond|responding|go|going|come|report|back|return|head|heading|enroute|en\s*route|out|take|taking)\s+$", re.I)


def extract_audio_crosses(text: str) -> str | None:
    """Cross streets spoken in the dispatch: 'Buffalo to Ralph Avenue',
    'Lorimer Street to Broadway', 'between X and Y'. Returns 'X & Y' or None.
    Strict: each side must look like a street name (1-3 words, capitalized or
    numeric in the original transcript, no verb/filler words) - scratchy-audio
    fragments like 'step now' or 'it's going' must never pass."""
    _T = r"(?:streets?|st|avenues?|ave|boulevards?|blvd|roads?|rd|drives?|dr|places?|pl|lanes?|ln|parkways?|pkwy|highways?|hwy|courts?|ct|terraces?|ter)"
    _WORD = r"[A-Za-z0-9][A-Za-z0-9.'-]*"
    _NM = rf"{_WORD}(?:\s+{_WORD}){{0,2}}?"      # 1-3 name words
    _TYPED = rf"{_NM}\s+{_T}"                    # "Ralph Avenue"
    _TN = rf"{_T}\s+[A-Za-z0-9]{{1,2}}"          # "Avenue H", "Avenue 2"
    _ANCH = rf"(?:{_TYPED}|{_TN})"
    _BARE = rf"{_WORD}(?:\s+{_WORD})?"
    _STOP1 = {"the", "a", "an", "you", "me", "him", "her", "it", "its", "now",
              "scene", "hospital", "units", "unit", "any", "respond", "responding",
              "go", "going", "come", "report", "back", "return", "head", "heading",
              "enroute", "out", "take", "copy", "make", "step", "be", "to", "and",
              "for", "on", "in", "of", "can", "are", "there"}
    t = text

    def _ok(name: str) -> bool:
        ws = name.split()
        if not (1 <= len(ws) <= 3) or len(name) > 32:
            return False
        if any(w.lower() in _STOP1 and not
               (w.lower() == "a" and len(ws) == 2 and ws[0].lower() in ("avenue", "ave"))
               for w in ws):
            return False
        return all(w[0].isupper() or w[0].isdigit() for w in ws)

    def _pair(a: str, b: str) -> str | None:
        a, b = a.strip(), b.strip()
        if a.split()[0].lower() in {"street", "st", "avenue", "ave", "road", "rd", "place", "pl"} \
                and len(a.split()) > 1:
            return None
        if _ok(a) and _ok(b) and a.lower() != b.lower():
            return f"{a} & {b}"
        return None

    m = re.search(rf"\bbetween\s+({_ANCH})\s+and\s+({_ANCH})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # "362 Lafayette Avenue, Classon and Grand Avenue": the first cross
    # drops its street type in radio shorthand. Anchor AFTER the complete
    # numbered address; never consume the address's Avenue as a cross.
    m = re.search(r"\b\d{1,5}\s+(?:[A-Z][a-z.'-]+\s+){1,3}"
                  r"(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl)\s*[,;]?\s+"
                  r"([A-Z][a-z.'-]{2,})\s+and\s+"
                  r"([A-Z][a-z.'-]{2,}\s+(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl))\b", t)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # Fully typed pair after a complete numbered address: "1409 New York
    # Avenue, Foster Avenue and Farragut Road". Keep only spoken roads; the
    # sender checks both intersections against the verified house geometry.
    m = re.search(r"\b\d{1,5}(?:-\d{1,3})?\s+(?:[A-Z][a-z.'-]+\s+){1,3}"
                  r"(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl)\s*[,;]?\s+"
                  r"([A-Z][a-z.'-]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl))"
                  r"\s+and\s+"
                  r"([A-Z][a-z.'-]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl))\b", t)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # Spoken bare pair after a numbered, typed job address. No map spelling
    # is invented: the bare names are preserved and checked downstream.
    m = re.search(r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+"
                  r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr)"
                  r"\s*[,;]?\s+([A-Z][a-z.'-]{2,})\s+to\s+"
                  r"([A-Z][a-z.'-]{2,})\b", t)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # 'off Nostrand Avenue and Bedford Avenue' - crosses spoken after the
    # address (dropped on the 8:03 AM Herkimer job 9/28)
    m = re.search(rf"\boff\s+({_ANCH})\s+and\s+({_ANCH})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    bare_block_text = t
    if re.search(rf"\b{_ANCH}\s+between\b", t, re.I):
        bare_block_text = re.split(r"\b(?:for|reporting)\b", t[t.lower().find("between"):], maxsplit=1, flags=re.I)[0]
    m = re.search(rf"\bbetween\s+({_BARE})\s+and\s+({_BARE})\b", bare_block_text, re.I)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        if all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]{2,}", w)
               for w in (a.split() + b.split())):
            r = _pair(a, b)
            if r:
                return r
    # between with one bare side: "between North Cannon and Victory Boulevard"
    m = re.search(rf"\bbetween\s+({_BARE})\s+and\s+({_ANCH})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    m = re.search(rf"\bbetween\s+({_ANCH})\s+and\s+({_BARE})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # Location pair spoken with only the second street typed: "for Coleridge
    # and Hampton Avenue". Accept only an address-introducing preposition,
    # and reject dispatcher filler on the bare side.
    m = re.search(rf"\b(?:for|at|on|of|in)\s+({_BARE})\s+and\s+({_ANCH})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # A digit-led primary job address may end with "Street" immediately
    # before an untyped first cross. The generic anchored-to-bare pattern
    # below can accidentally consume that trailing Street as a cross name
    # ("Street Neptune & Mermaid Avenue" on 2860 West 23). Capture only
    # the two roads following the full numbered address, or keep no pair.
    if re.search(r"\b\d{1,5}\s+(?:West|East|North|South)\s+\d{1,3}"
                 r"(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave)\b", t, re.I):
        m = re.search(r"\b\d{1,5}\s+(?:West|East|North|South)\s+\d{1,3}"
                      r"(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave)\b"
                      r"\s*[,;.]?\s+([A-Z][a-z.'-]{2,})\s+to\s+"
                      r"([A-Z][a-z.'-]{2,}\s+" + _T + r")\b", t, re.I)
        if m:
            r = _pair(m.group(1), m.group(2))
            if r:
                return r
    # A highway suffix may include a direction after its road type. Do not
    # trim the road name off "Belt Parkway South" before a spoken cross.
    m = re.search(r"\b((?:Belt|Grand Central|Southern State)\s+Parkway\s+"
                  r"(?:South|North|East|West))\s+to\s+(" + _ANCH + r")\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # Typed crosses after a complete house address; ASR may render "to"
    # as comma + "the". Require both road types and the address anchor.
    m = re.search(r"\b\d{1,5}\s+(?:[A-Z][a-z.'-]+\s+){1,3}"
                  r"(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl)\s*,\s*"
                  r"([A-Z][a-z.'-]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl))"
                  r"\s*,\s*the\s+"
                  r"([A-Z][a-z.'-]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Place|Pl))\b", t)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # anchored to anchored: "Glenwood Road to Avenue H"
    m = re.search(rf"({_ANCH})\s+to\s+({_ANCH})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # anchored to bare: "Lorimer Street to Broadway"
    m = re.search(rf"({_ANCH})\s+to\s+({_BARE})\b", t, re.I)
    if m:
        pre = t[:m.start()].rstrip()[-12:]
        if not _VERB_BEFORE_TO.search(pre + " "):
            r = _pair(m.group(1), m.group(2))
            if r:
                return r
    # adjacent numbered crosses sharing one suffix, 'to' lost by whisper:
    # "East 99 East 100 Street" (9903 Flatlands 9/28)
    m = re.search(rf"\b((?:east|west|north|south)\s*\d{{1,3}}(?:st|nd|rd|th)?)\s+(?:to\s+)?((?:east|west|north|south)\s*\d{{1,3}}(?:st|nd|rd|th)?\s+{_T})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # numbered pair sharing one suffix, no to/between: "15th and 16th Avenue"
    m = re.search(rf"\b(\d{{1,3}}(?:st|nd|rd|th))\s+and\s+(\d{{1,3}}(?:st|nd|rd|th)?\s+{_T})\b", t, re.I)
    if m:
        r = _pair(m.group(1), m.group(2))
        if r:
            return r
    # bare to anchored: "Buffalo to Ralph Avenue", "3 to 4 Avenue"
    m = re.search(rf"\b({_BARE})\s+to\s+({_ANCH})\b", t, re.I)
    if m:
        pre = t[:m.start()].rstrip()[-12:]
        if not _VERB_BEFORE_TO.search(pre + " "):
            r = _pair(m.group(1), m.group(2))
            if r:
                return r
    # 'off Woodbine Street' - single spoken cross (371 Irving 9/28; user: 'I
    # wanna see cross streets of the address'). Renders 'off X'; the map side
    # completes the pair downstream. LAST - every pair shape above wins.
    m = re.search(rf"\boff(?:\s+of)?\s+({_ANCH})\b(?!\s+(?:and|&|to)\b)", t, re.I)
    if m:
        a = m.group(1).strip()
        if _ok(a):
            return a
    return None


def extract_direct_street_pair(text: str) -> tuple[str, str] | None:
    """A directly spoken X and Y intersection, both sides typed.

    The first road is the fallback location. The second is a candidate only:
    map verification decides whether it appears in the outgoing alert.
    """
    word = r"[A-Za-z0-9][A-Za-z0-9.'-]*"
    typ = r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln|Parkway|Pkwy|Court|Ct|Terrace|Ter)"
    road = rf"{word}(?:\s+{word}){{0,2}}?\s+{typ}"
    for m in re.finditer(rf"(?=\b({road})\s+(?:and|&)\s+({road})\b)", text, re.I):
        a, b = m.group(1).strip(), m.group(2).strip()
        # A location-introducing preposition or comma must lead this pair;
        # don't reclassify arbitrary chatter as a job location.
        pre = text[:m.start()]
        if not re.search(r"(?:\b(?:for|at|on|in|to|corner of|intersection of)\s+|,\s*)$", pre, re.I):
            continue
        def clean(n):
            ws = n.split()
            while ws and ws[0].lower() in _NAME_STOP:
                ws.pop(0)
            return " ".join(ws)
        a, b = _hatzalah_clean_road(clean(a)), clean(b)
        # A regex span starting at an action word is not a road name:
        # "respond to 13th avenue" must remain "13th avenue".
        a = re.sub(r"^(?:respond|responding|dispatch|units?)\s+(?:to\s+)?", "", a, flags=re.I)
        if a and b and a.lower() != b.lower() and len(a) < 40 and len(b) < 40:
            return a, b
    return None


def extract_spoken_three_road_location(text: str) -> tuple[str, str, str] | None:
    """A spoken primary road followed by two separately named crossing roads.

    E.g. "Dry Harbor Road, 84th Place and 85th Street". Require all
    three complete street types and a location-introducing phrase; unit
    numbers elsewhere in the transmission cannot become a street.
    """
    word = r"[A-Za-z0-9][A-Za-z0-9.'-]*"
    typ = r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln|Parkway|Pkwy|Court|Ct|Terrace|Ter)"
    road = rf"{word}(?:\s+{word}){{0,2}}?\s+{typ}"
    for m in re.finditer(rf"(?=\b({road})\s*,\s*({road})\s+(?:and|&)\s+({road})\b)", text, re.I):
        pre = text[:m.start()]
        if not re.search(r"(?:\b(?:for|at|on|in|to|corner of|intersection of)\s+|,\s*)$", pre, re.I):
            continue
        roads = [r.strip() for r in m.groups()]
        for i, road_name in enumerate(roads):
            words = road_name.split()
            while words and words[0].lower() in _NAME_STOP:
                words.pop(0)
            roads[i] = " ".join(words)
        if all(roads) and len({r.lower() for r in roads}) == 3:
            return tuple(roads)
    return None


def extract_named_cross(text: str) -> str | None:
    """FDNY style: 'Smith Street at Baltic' -> 'Smith St & Baltic St'.

    The second street type is often omitted on the air, so it is optional;
    a stopword guard keeps chatter out. Kept fdny-only so the running
    Hatzolah/Sullivan grammar is untouched.
    """
    t = _norm(text).lower()
    stypes = r"(street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|place|pl|lane|ln|parkway|pkwy|terrace|ter|court|ct)"
    name = r"([a-z][a-z'\-]{0,20}(?: [a-z][a-z'\-]{0,20}){0,2}?)"
    # lookahead wrapper: candidates overlap ('auto accident IT'S BELL parkway
    # and...' must still find the 'it's bell parkway' candidate after the
    # leftmost one fails validation)
    for m in re.finditer(
            rf"(?=\b({name})\s+({stypes})\s+(?:and|at|&)\s+({name})(?:\s+({stypes}))?\b)",
            t, re.I):
        # groups 1/3/5/7 are the outer captures (name/stypes carry inner ones)
        n1, t1, n2 = m.group(1).strip(), m.group(3), m.group(5).strip()
        t2 = m.group(7) or "st"
        # leading dispatcher glue is not part of the street name ('that's off
        # Manhattan Avenue and Graham Avenue' posted 'That'S Off Manhattan Ave'
        # 9/28) - strip leading filler words before validating
        w1 = n1.split()
        while w1 and w1[0] in _NAME_STOP:
            w1.pop(0)
        n1 = " ".join(w1)
        if n1 == n2 or not _ok_name(n1) or not _ok_name(n2):
            continue
        p1 = f"{_addr_title(n1)} {_STREET_ABBREV.get(t1.lower(), t1.title())}"
        p2 = f"{_addr_title(n2)} {_STREET_ABBREV.get(t2.lower(), t2.title())}"

        def _alias_fix(part: str) -> str:
            # 'it's bell parkway and pennsylvania avenue' posted 'It's Bell
            # Pkwy' (9/28 15:55) - the alias table knows the whisper variants
            ws = part.split()
            if len(ws) >= 2 and ws[-1].lower() in ("pkwy", "parkway", "hwy",
                                                   "highway", "expwy", "expressway"):
                disp = (NYC_HIGHWAYS.get(" ".join(ws[:-1]).lower())
                        or NYC_BRIDGES.get(" ".join(ws[:-1]).lower()))
                if disp:
                    return disp
            return part
        return f"{_alias_fix(p1)} & {_alias_fix(p2)}"
    return None


_FDNY_JOBISH_RE = re.compile(
    r"\b(?:fire|smoke|gas|odor|leak|mva|mvc|accident|collision|rollover|pin|pinned|"
    r"entrap|water|wires?|spark|arcing|collapse|alarm|ems|cardiac|unconscious|"
    r"breathing|overdose|choking|ped\s*struck|man\s*down|electrocut|burn|scald|"
    r"hazmat|chemical|explos|subway|elevator|stuck)\b", re.I)

_FDNY_SKIP_RE = re.compile(
    r"\b(?:nothing going on|show us 10-8|you can 10-8|go 10-8|10-8 from|"
    r"relocate|relocation|radio test|from quarters|10-84|on scene|"
    r"available|in service)\b", re.I)



def _split_box_glue(t: str) -> str:
    """Split Whisper's box+house digit run before the street name.

    Six digits are usually a three-digit box followed by a three-digit
    house number: 258648 = Box 258, 648 Grand Street (verified against
    Manhattan Ave & Grand St and the spoken Manhattan/Leonard crosses).
    A five-digit run uses a three-digit box + two-digit house (95770).
    Other lengths retain the four-digit box candidate. Only split when a
    named street type follows, not a standalone box, date or radio code.
    """
    street_after = re.compile(
        r"\s*[,;]?\s+(?:[A-Za-z][A-Za-z.'-]*\s+){0,3}"
        r"(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|place|pl|"
        r"boulevard|blvd|parkway|pkwy)\b", re.I)

    def _rep(m):
        run = m.group(1)
        if not street_after.match(t[m.end():]):
            return m.group(0)
        preferred = {5: (3, 4, 2), 6: (3, 4, 2), 7: (4, 3, 2)}
        for blen in preferred.get(len(run), (4, 3, 2)):
            house = run[blen:]
            if 1 <= len(house) <= 4 and house[0] != "0":
                return f"box {run[:blen]}, {house}"
        return m.group(0)
    return re.sub(r"\bbox\s+(\d{5,7})\b(?:\s*[,;])?", _rep, t, flags=re.I)


def detect_box(text: str) -> str | None:
    t = text.lower()
    # user ruling 9/28 13:36: only a spoken 'box NNNN' counts - 'alarm 2584'
    # is a class-3/alarm readout, not a box number
    m = re.search(r"\bbox\s+(\d{2,4})", t)
    if m:
        return m.group(1).zfill(4)
    return None


def get_sullivan_area(text: str) -> str:
    t = text.lower()
    for k, v in SULLIVAN_AREAS.items():
        if k in t:
            return v
    return "Sullivan Co"


def _with_area(addr: str, profile: str, text: str) -> str:
    addr = re.sub(r"^(?:and|or)\s+", "", addr.strip(), flags=re.I)
    if profile == "hatzolah":
        locality = get_hatzolah_area(text)
        state = "NJ" if (locality in BERGEN_AREAS.values() or
            re.search(r"\b" + re.escape(locality) + r"\s*,?\s+(?:NJ|New Jersey)\b", text, re.I)) else "NY"
        area = f"{locality}, {state}"
    elif profile == "fdny":
        from fdny_borough_gate import spoken_job_borough
        area = f"{spoken_job_borough(text) or 'Brooklyn'}, NY"
    else:
        area = f"{get_sullivan_area(text)}, NY"
    # The locality word inside a street name is not the locality: "Fair
    # Lawn Avenue" still needs ", Fair Lawn, NJ". Never infer town from it.
    return f"{addr}, {area}"


_FIRE_NUM_DISPATCH_RE = re.compile(
    r"\b(\d{3,4})\s+on\s+([A-Za-z .'-]{3,40}?(?:Road|Rd|Street|St|Avenue|Ave|Lane|Ln|"
    r"Drive|Dr|Court|Ct|Place|Pl|Boulevard|Blvd|Route|Highway|Hwy|Turnpike|Tpke))\b", re.I)

# "F-37, head over to Windsor Hills Estates" - fire dispatch to a named place
_HEAD_OVER_RE = re.compile(r"\bhead over to\s+(.{3,60})", re.I)


_LONE_STREET_RE = re.compile(
    r"\b((?:[A-Za-z0-9.'-]+\s+){1,2}(?:Ave(?:nue)?|St(?:reet)?|Rd|Road|Blvd|Boulevard|"
    r"Dr|Drive|Ln|Lane|Ct|Court|Pl(?:ace)?|Pkwy|Parkway|Ter(?:race)?|Way|"
    r"Cir(?:cle)?|Hwy|Highway|Tpke|Turnpike))\b", re.I)


def extract_dispatch_address(text: str, profile: str = "hatzolah") -> str | None:
    """Best-effort dispatch location for one transcript chunk."""
    if profile == "sullivan":
        broadway = re.search(r"\b(?:number\s+)?(\d{1,5})\s+Broadway\b", text, re.I)
        if broadway:
            return _with_area(f"{broadway[1]} Broadway", profile, text)
    if profile in ("hatzolah", "hatzalah"):
        short_house = re.search(r"\b(\d{3,5})\s+(East|West|North|South)\s+(\d{1,3})(?:st|nd|rd|th)?(?=\s*[,.;]|\s+for\b)", text, re.I)
        if short_house and (get_nature(text[short_house.start():], "hatzolah") or re.search(r"\bprivate house\b", text[short_house.end():], re.I)):
            n = int(short_house.group(3))
            suffix = "th" if 11 <= n % 100 <= 13 else {1:"st",2:"nd",3:"rd"}.get(n % 10,"th")
            return _with_area(f"{short_house.group(1)} {short_house.group(2).title()} {n}{suffix} Street", profile, text)
    if profile == "fdny":
        # Queens hyphenated house numbers are indivisible, never the suffix
        # alone (159-22 is a building number, not a radio run plus 22).
        queens_house = re.search(
            r"\b(\d{2,3}-\d{1,3})\s+([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2})\s+"
            r"(Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Place|Pl)\b",
            _norm(text), re.I)
        if queens_house:
            return _with_area(f"{queens_house.group(1)} {_addr_title(queens_house.group(2) + ' ' + queens_house.group(3))}", profile, text)
        # A numbered NYCHA Walk is a full street address, including an
        # internal number ("127 Kingsborough 1 Walk"). Match it before an
        # unrelated street or a radio unit's apparent house-number fragment.
        walks = list(re.finditer(
            r"\b(\d{1,5})\s+([A-Za-z][A-Za-z'-]{2,}(?:\s+[A-Za-z][A-Za-z'-]{2,}){0,2})"
            r"[,\s]+(\d{1,2}|one|two|three|four|five)(?:st|nd|rd|th)?\s+Walk\b", _norm(text), re.I))
        if walks:
            # First complete walk address is the incident anchor; later
            # repeats in an overlapping recording do not make a new job.
            m = walks[0]
            n = int({"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}.get(m.group(3).lower(), m.group(3)))
            suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            walk_name = _addr_title(m.group(2))
            # The address appears as Kingsboro/Kingsborough on this FDNY
            # recording; the NYCHA street's canonical name is Kingsborough.
            if walk_name.lower() == "kingsboro":
                walk_name = "Kingsborough"
            return _with_area(f"{m.group(1)} {walk_name} {n}{suffix} Walk", profile, text)
        # FDNY sometimes gives a numbered MetroTech building as the address,
        # followed by Myrtle/Bridge as cross roads. MetroTech is a mapped
        # street/building name, not a generic "tech" descriptor. Preserve the
        # spoken number and let the sender verify the exact rooftop location.
        metro = re.search(r"\b(?:address\s+)?(\d{1,3})\s+(Metro\s*Tech)(?:\s+Center)?\b", _norm(text), re.I)
        if metro:
            return _with_area(f"{metro.group(1)} MetroTech Center", profile, text)
        # FDNY ASR can insert "Number" before an ordinal road: "261 Number
        # 9 Street" is a house on 9th Street, not an unnumbered "Number 9"
        # road. Require a separate house and explicit road type; the sender
        # must still verify the exact mapped house before any alert.
        number_street = re.search(
            r"\b(\d{1,5})\s+Number\s+(\d{1,3})(?:st|nd|rd|th)?\s+"
            r"(Street|St|Avenue|Ave)\b", _norm(text), re.I)
        if number_street:
            n = int(number_street.group(2))
            if 1 <= n <= 150:
                suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                road = "Street" if number_street.group(3).lower() in ("st", "street") else "Avenue"
                return _with_area(f"{number_street.group(1)} {n}{suffix} {road}", profile, text)
        # ASR may omit the ordinal suffix inside a numbered South street:
        # "330 South 3 Street". A distinct house number before the road is
        # stronger than a later bare "Box 231, 330 South 3" readout. Keep
        # the road's digit as heard; exact house verification is sender-owned.
        south_house = re.search(
            r"\b(\d{1,5})\s+(South)\s+(\d{1,2})\s+(Street|St)\b",
            _norm(text), re.I)
        if south_house:
            return _with_area(f"{south_house.group(1)} South {south_house.group(3)} Street",
                              profile, text)
        # Spoken AFA Class 3 followed by its four-digit assignment/box and a
        # separate full house address: "Class 32372, 714 East 83 Street".
        # Keep the house independent of the alarm number. The sender verifies
        # the physical address and compares any candidate box against NYC data.
        class_house = re.search(
            r"\b(?:AFA\s+)?class\s*3\s*\d{4}\s*[,;]?\s*"
            r"(\d{1,5})\s+((?:East|West|North|South)\s+\d{1,3}"
            r"(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave))\b", text, re.I)
        if class_house:
            return _with_area(f"{class_house.group(1)} {_addr_title(class_house.group(2))}",
                              profile, text)
        # A repeated, complete house address outranks an earlier bare road.
        # In the PS 115 readout "East 92 Street ... Class 3 2287, 1500 East 92
        # Street", the 2287 is the class/box ID; 1500 is the house.
        repeated_house = re.search(
            r"\b(?:class\s*3\s*[,;]?\s*\d{2,4}\s*[,;]?\s*|"
            r"box\s+\d{2,4}\s*[,;]?\s*)"
            r"(\d{1,5})\s+((?:East|West|North|South)\s+\d{1,3}"
            r"(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave))\b", text, re.I)
        if repeated_house:
            return _with_area(f"{repeated_house.group(1)} "
                              f"{_addr_title(repeated_house.group(2))}", profile, text)
        # The Brooklyn letter avenue is "Avenue U", not an unnumbered
        # "1111 Avenue" or an intersection inferred from later cross roads.
        # Require a distinct house before the typed letter avenue; never
        # promote the class/terminal digits to a building number.
        letter_avenue = re.search(
            r"\b(\d{1,5})\s+(Avenue|Ave)\s+([A-Z])\b", text)
        if letter_avenue and not re.search(
                r"\b(?:box|terminal|class)\s*$", text[max(0, letter_avenue.start()-12):letter_avenue.start()], re.I):
            return _with_area(f"{letter_avenue.group(1)} Avenue {letter_avenue.group(3)}",
                              profile, text)
        # Class 3 box and terminal readout before a separate Broadway house.
        # Broadway has no road suffix, so the generic typed-street parser
        # otherwise promotes the later Linden Street cross to the address.
        # Require the full dispatch shape; a naked terminal number is not a
        # house, and the sender still verifies the exact house independently.
        class_broadway = re.search(
            r"\b(?:AFA\s+)?class\s*3\s+(?:box\s+)?\d{2,4}\s*[,;]?\s*"
            r"terminal\s+\d{1,3}\s*[,;]?\s*"
            r"(\d{1,5})\s+((?:East|West)\s+)?Broadway\b", text, re.I)
        if class_broadway:
            road = (class_broadway.group(2) or "") + "Broadway"
            return _with_area(f"{class_broadway.group(1)} {_addr_title(road)}", profile, text)
        # A spoken alarm/box ID followed by a separate numbered East/West
        # street still has a house address. Do not turn the alarm ID into
        # the house or let a later apartment numeral replace the house.
        alarm_house = re.search(
            r"\b(?:alarm|box)\s+\d{3,5}\s*[,;]?\s*"
            r"(\d{1,5})\s+((?:East|West|North|South)\s+\d{1,3}"
            r"(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave))\b", text, re.I)
        if alarm_house:
            return _with_area(f"{alarm_house.group(1)} {_addr_title(alarm_house.group(2))}",
                              profile, text)
        # A box readout is not a house number. When dispatch gives only a
        # bare numbered street with spoken crosses, preserve that street.
        # This pattern is scoped to the box+street readout; a separate spoken
        # "2926 W 25th" still wins below as an actual house address.
        bare_box_street = re.search(
            r"\bbox\s+\d{2,4}\s+((?:east|west|north|south)\s+\d{1,3}"
            r"(?:st|nd|rd|th)?\s+(?:street|st|avenue|ave))\b", text, re.I)
        if bare_box_street:
            follow = text[bare_box_street.end():]
            if re.match(r"\s*(?:,|\.|between|at|off|from|to|for|and|$)", follow, re.I):
                return _with_area(_addr_title(bare_box_street.group(1)), profile, text)
        # A numbered subway emergency exit is a facility identifier, not a
        # house. "exit number 264 on Tillery Street" may be followed by a
        # street/cross without any dispatch address. Skip that ID only;
        # a different complete house in this transcript can still win.
        address_text = _norm(text)
        if re.search(r"\b(?:subway\s+)?emergency\s+exits?\b", address_text, re.I):
            address_text = re.sub(
                r"\b(?:subway\s+)?emergency\s+exits?\s+(?:number\s+)?\d{1,5}\b",
                "emergency exit", address_text, flags=re.I)
            address_text = re.sub(
                r"\b(?:and\s+)?(?:exit\s+)?number\s+\d{1,5}\s+on\b",
                "on", address_text, flags=re.I)
        # A bare road can follow a spoken box without a separate house:
        # "Box 3734, Clarendon Road between East 31 and East 32". The box
        # is not an address number. This is a display-only bare-road candidate;
        # sender still verifies it or holds it.
        bare_box_named = re.search(
            r"\bbox\s+\d{2,4}\s*[,;]?\s+(?:on\s+)?"
            r"([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}\s+"
            r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Place|Pl))\b"
            r"(?=\s*(?:[,;. ]|between\b|to\b|at\b|for\b|$))", _norm(text), re.I)
        if bare_box_named and not re.search(r"\b\d{1,5}\s+" +
                re.escape(bare_box_named.group(1)) + r"\b", text[bare_box_named.end():], re.I):
            return _with_area(_addr_title(bare_box_named.group(1)), profile, text)
        # house number on a named street ('710 Grand Street') is the dispatch
        # address; it beats the 'that's off X and Y' named-cross glue (710
        # Grand St posted as 'That'S Off Manhattan Ave & Graham Ave' 9/28)
        # ordinal-numbered streets carry a digit word inside the name: '1718
        # East 15th Street' missed here and the 'off of Kings Highway' anchor
        # posted instead (box 3321 gas-main job 9/28). Allow one ordinal
        # token after the alpha name, or an ordinal-only street ('515 81st
        # Street' after the split-digit merge).
        hn = re.search(
            r"\b(\d{1,5})\s+(?:([a-z][a-z'\-]*(?:\s+[a-z][a-z'\-]*){0,2})\s+)?"
            r"(?:(\d{1,3}(?:st|nd|rd|th))\s+)?"
            r"(street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|place|pl|"
            r"lane|ln|parkway|pkwy)\b", address_text.lower())
        if hn:
            w2 = (hn.group(2) or "").split()
            while w2 and w2[0] in _NAME_STOP:
                w2.pop(0)
            # Primary typed road ends at its first spoken type. A following
            # cross (Grand Street Manhattan Avenue) cannot join the name.
            for k,w in enumerate(w2):
                if w in ("street","st","avenue","ave","road","rd","drive","dr","place","pl","boulevard","blvd"):
                    return _with_area(f"{hn.group(1)} {_addr_title(' '.join(w2[:k+1]))}", profile, text)
            nm = " ".join(w2)
            ordw = hn.group(3) or ""
            if (nm and nm not in _NAME_STOP) or ordw:
                typ = {"st": "street", "ave": "avenue", "rd": "road", "dr": "drive",
                       "blvd": "boulevard", "pl": "place", "ln": "lane",
                       "pkwy": "parkway"}.get(hn.group(4), hn.group(4))
                street = " ".join(x for x in (nm, ordw, typ) if x)
                return _with_area(f"{hn.group(1)} {_addr_title(street)}",
                                  profile, text)
        num0 = _FIRE_NUM_DISPATCH_RE.search(address_text)
        if num0:
            return _with_area(f"{num0.group(1)} {_addr_title(num0.group(2).strip())}", profile, text)
        named = extract_named_cross(address_text)
        if named:
            return _with_area(named, profile, text)
    else:
        # Sullivan dispatch can pair a typed road with suffixless Broadway.
        # Require the explicit spoken separator, never supply a road suffix.
        if profile == "sullivan":
            broadway_pair = re.search(
                r"\b([a-z][a-z'-]*(?:\s+[a-z][a-z'-]*){0,2})\s+"
                r"(street|st|avenue|ave|road|rd|drive|dr|place|pl)\s+"
                r"(?:and|at|&)\s+((?:(?:east|west)\s+)?broadway)\b", text, re.I)
            if broadway_pair:
                first = broadway_pair.group(1).split()
                while len(first) > 1 and first[0].lower() in _NAME_STOP:
                    first.pop(0)
                typ = {"st": "Street", "ave": "Avenue", "rd": "Road", "dr": "Drive", "pl": "Place"}.get(broadway_pair.group(2).lower(), broadway_pair.group(2).title())
                return _with_area(f"{_addr_title(' '.join(first))} {typ} & {_addr_title(broadway_pair.group(3))}", profile, text)
        # Broadway has no Street/Road suffix. Keep its spoken house only in
        # a Sullivan medical dispatch; the sender still verifies exact house,
        # road and county before any outgoing alert.
        if profile == "sullivan":
            bw = re.search(r"\b(\d{1,5})\s+((?:East|West)\s+)?Broadway\b", text, re.I)
            if bw and re.search(r"\b(?:BLS|ALS|EMS)\s+response\b", text, re.I):
                return _with_area(f"{bw.group(1)} {_addr_title((bw.group(2) or '') + 'Broadway')}", profile, text)
        # house number on a named street for the EMS/Sullivan grammar ('67 Old
        # Ryan Road' posted bare 9/28; '2 Marcel 4 Road' lost the 2 - one
        # trailing all-digit word is allowed inside the name: Marcel 4 Road =
        # the map's Marcel Four Road)
        hn = re.search(
            r"\b(\d{1,5})\s+(?:([a-z][a-z'\-]*(?:\s+[a-z][a-z'\-]*){0,2}"
            r"(?:\s+\d{1,2})?)\s+)?(?:(\d{1,3}(?:st|nd|rd|th))\s+)?"
            r"(street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|place|pl|"
            r"lane|ln|parkway|pkwy|way)\b", _norm(text).lower())
        if hn:
            w2 = (hn.group(2) or "").split()
            while w2 and w2[0] in _NAME_STOP:
                w2.pop(0)
            nm = " ".join(w2)
            ordw = hn.group(3) or ""
            if (nm and nm not in _NAME_STOP) or ordw:
                typ = {"st": "street", "ave": "avenue", "rd": "road", "dr": "drive",
                       "blvd": "boulevard", "pl": "place", "ln": "lane",
                       "pkwy": "parkway"}.get(hn.group(4), hn.group(4))
                street = " ".join(x for x in (nm, ordw, typ) if x)
                if profile == "sullivan" and re.match(r"\s+extension\b", _norm(text).lower()[hn.end():]):
                    street += " extension"
                return _with_area(f"{hn.group(1)} {_addr_title(street)}",
                                  profile, text)
    if profile == "fdny" and re.search(r"\b(?:subway\s+)?emergency\s+exits?\b", text, re.I):
        # The named pair above is the only candidate left from this follow-up.
        # Never let generic fallbacks reintroduce a numbered exit as a house.
        return None
    hwy = extract_highway_intersection(text, profile)
    if hwy:
        return _with_area(hwy, profile, text)
    cross = extract_cross_street(text)
    if cross:
        return _with_area(cross, profile, text)
    house = extract_house_address(text)
    if house:
        return _with_area(house, profile, text)
    num = _FIRE_NUM_DISPATCH_RE.search(text)
    if num:
        return _with_area(f"{num.group(1)} {_addr_title(num.group(2).strip())}", profile, text)
    lone = _LONE_STREET_RE.search(text)
    if lone:
        ws = lone.group(1).strip().split()
        while len(ws) > 1 and ws[0].lower() in _NAME_STOP:
            ws.pop(0)
        street = _addr_title(" ".join(ws))
        if len(ws) > 1 and len(street) > 6:
            return _with_area(street, profile, text)
    if profile == "sullivan":
        for k, v in SULLIVAN_AREAS.items():
            if k in text.lower():
                return f"{v}, NY"
    return None


# ---------------------------------------------------------------------------
# Nature classification (simplified cascade from get_nature in the original)
# ---------------------------------------------------------------------------
def _negative_fire_context(t: str) -> bool:
    return bool(re.search(
        r"\b(no|not|without|negative|isn't|is\s+not)\s+(a\s+)?fire\b"
        r"|\bno\s+signs?\s+of\s+fire\b"
        r"|\bfire\s+(is\s+)?(out|extinguished|knocked?)\b", t))


def get_nature(text: str, profile: str = "") -> str:
    """Nature = the dispatcher's own words (user ruling 9/28 13:32: 'Fire in a
    private dwelling should be fire in a private dwelling') - verbatim as
    spoken, no rewording/normalizing/label swaps; only whisper garbage is
    cleaned. Returns the matched phrase ('' when nothing is discernible).
    Cascade order is unchanged: content natures beat transmission types."""
    t = text.lower()
    if profile == "fdny":
        gas = re.search(r"\bodou?r\s+of\s+gas\s+in\s+(?:the\s+)?basement\b",t,re.I)
        if gas and not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$",t[max(0,gas.start()-40):gas.start()]):
            return "Odor of Gas in the Basement"
    if profile == "fdny":
        # Observed Madison ASR "order of gas" stands for odor only inside
        # a complete job-local complaint. No global order/odor replacement.
        boxes = {m[1].zfill(4) for m in re.finditer(r"\bbox\s+(\d{2,4})\b", t)}
        if len(boxes) == 1:
            m = re.search(r"\border of gas\s+in\s+(?:the\s+)?(?:basement|cellar|area)\b", t)
            if m and not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", t[max(0,m.start()-35):m.start()]):
                return "Odor of Gas" + (", Basement" if "basement" in m[0] else ", Cellar" if "cellar" in m[0] else ", In the Area")
    # Recorded medical readouts: retain spoken wording and uncertainty. These
    # additions do not infer a diagnosis from an apparatus or routing request.
    patterns = []
    if profile == "hatzolah":
        patterns = [r"\bpatient down from a height\b", r"\brenal colic\b",
                    r"\b(?:probably\s+(?:just\s+)?(?:a\s+)?|possible\s+(?:a\s+)?)?lift assist\b"]
    elif profile == "sullivan":
        patterns = [r"\bcardiac problem\b"]
    for pattern in patterns:
        for m in re.finditer(pattern, t):
            before = t[max(0, m.start()-40):m.start()]
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", before):
                return _addr_title(m.group())
    if profile == "fdny":
        for m in re.finditer(r"\bfire in (?:a |the )?compactor\b|\bcompactor fire\b", t):
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", t[max(0,m.start()-40):m.start()]):
                return _addr_title(m.group())
    # Retain the exact observed complaint, never a diagnosis or facility name.
    exact = (r"\bpediatric emergency\b" if profile == "hatzolah" else
             r"\b(?:oven|stove) fire\b" if profile == "fdny" else "")
    if exact:
        m = re.search(exact, t)
        if m:
            before = t[max(0, m.start()-40):m.start()]
            if re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", before):
                return ""
            if re.search(r"\b(?:for|reporting)\s+(?:an?\s+)?$", before):
                return _addr_title(m.group())
    # A leading "working fire" ASR fragment can be transmission chatter while
    # the actual dispatched complaint later says automatic alarm. This FDNY
    # case must not be promoted to fire from the earlier fragment. A later
    # explicit fire complaint remains governed by the normal cascade.
    if profile == "fdny":
        manual = re.search(r"\bmanual\s+(?:fire\s+)?alarm\b", t)
        if manual and not re.search(
                r"\b(?:structure|building|house|kitchen|car|vehicle|actual)\s+fire\b"
                r"|\bfire\s+in\s+a\s+private\s+dwelling\b", t[manual.end():]):
            return _addr_title(manual.group(0))
        alarm = re.search(r"\bautomatic\s+(?:fire\s+)?alarm(?:\s+in\s+(?:an?\s+)?(?:office\s+building|private\s+dwelling))?\b", t)
        if alarm and not re.search(r"\b(?:structure|building|house|kitchen|car|vehicle|actual)\s+fire\b|\bfire\s+in\s+a\s+private\s+dwelling\b", t[alarm.end():]):
            return _addr_title(alarm.group(0))
    if profile == "sullivan":
        # Keep explicit high-rate symptoms and adjacent generally-ill readout.
        # No diagnosis is inferred from a pulse rate alone.
        for m in re.finditer(r"\b(?:generally ill\s*[,;]?\s*(?:and\s+)?high (?:heart|pulse) rate|high (?:heart|pulse) rate\s*[,;]?\s*(?:and\s+)?generally ill|high (?:heart|pulse) rate)\b", t):
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$",
                             t[max(0,m.start()-40):m.start()]):
                return _addr_title(m.group())
    if profile == "sullivan":
        # Spoken symptoms only; do not infer shock, hypotension or a diagnosis.
        for m in re.finditer(r"\b(?:low blood pressure\s*[,;]?\s*(?:and\s+)?dehydrated|dehydrated\s*[,;]?\s*(?:and\s+)?low blood pressure|low blood pressure|dehydrated)\b", t):
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$",
                             t[max(0,m.start()-40):m.start()]):
                return _addr_title(m.group())
    if profile == "hatzolah":
        # Audio-grounded MVA misreading only inside a live bus dispatch.
        # MBA as a degree, course, unit label or bare acronym stays unchanged.
        m = re.search(r"\bfor\s+(?:an?|the)\s+mba\b", t)
        if m and re.search(r"\bunits?\b.{0,45}\bload(?:ed)?\s+(?:up\s+)?(?:a\s+)?(?:queens\s+)?bus\s+at\b", t[:m.start()]) and not re.search(r"\b(?:no|not|negative|training|test|drill|degree|course|school)\b", t[:m.end()]):
            return "Mva"
    # Preserve only adjacent, explicit compound complaints from one readout.
    compounds = []
    if profile == "sullivan":
        compounds.append(r"\b(?:difficulty breathing\s*[,;]?\s*(?:and\s+)?altered mental status|altered mental status\s*[,;]?\s*(?:and\s+)?difficulty breathing)\b")
    if profile == "fdny":
        compounds.append(r"\bflash fire with (?:a )?gas leak\b")
    for pattern in compounds:
        for m in re.finditer(pattern, t):
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", t[max(0,m.start()-35):m.start()]):
                return _addr_title(m.group(0))
    # Preserve a spoken age with its medical complaint, never invent one.
    aged = re.search(r"\b(?:the\s+)?(\d{1,3}[- ]year[- ]old)\s+(?:patient\s+)?(not\s+feeling\s+well|feeling\s+unwell|feels\s+unwell)\b", t)
    if aged:
        return _addr_title(aged.group(1) + " " + aged.group(2))
    # Keep the dispatcher's entire medical complaint when a cardiac patient
    # is described as not feeling well; the isolated "cardiac" word is not a
    # diagnosis and the complaint must not lose its spoken qualifier.
    m_card = re.search(r"\bcardiac\s+patient\s+(?:is\s+)?(?:not\s+feeling\s+well|"
                       r"feeling\s+unwell|feels\s+unwell)\b", t)
    if m_card:
        return _addr_title(m_card.group(0))
    # 'firefighter(s)' on scene is not a fire nature (53rd St Hatzolah EMS job
    # posted as 'Fire' 9/28 off a whisper 'Firefight 253' fragment)
    t = re.sub(r"firefight(?:er|ers|ing)?", " ", t)

    def vt(pattern: str) -> str:
        # user ruling 9/28 ('put something that was said'): a nature word
        # immediately followed by a bare number is unit chatter, not a spoken
        # nature - 'Rubbish 265' was a mangled unit readout and posted RUBBISH
        # on a fainting call. Skip digit-followed occurrences.
        for m in re.finditer(pattern, t):
            number = re.match(r"\s+([0-9]{2,5})\b", t[m.end():])
            if number:
                # A terminal HHMM after a job-local complaint is a clock,
                # not an apparatus number. Other digit-followed words stay out.
                tail = t[m.end()+number.end():].strip(" .,!;:")
                clock = (profile == "fdny" and not tail and
                         re.fullmatch(r"(?:[01][0-9]|2[0-3])[0-5][0-9]", number.group(1)) and
                         re.search(r"\b(?:for|reporting)\s+(?:an?\s+)?$", t[max(0,m.start()-25):m.start()]))
                if not clock:
                    continue
            return _addr_title(m.group(0))
        return ""

    v = vt(r"\b(?:all hands|10-75|10 75|working fire|second alarm|third alarm)\b")
    if v: return v
    # Train/subway strike is a life-safety nature, not generic "ped struck".
    # Preserve the exact dispatcher wording and keep it ahead of apparatus
    # and transmission-code fallbacks.
    v = vt(r"\b(?:person|pedestrian|ped)\s+struck\s+by\s+(?:a\s+)?train\b")
    if v: return v
    v = vt(r"\b(?:ped|pedestrian)\s+(?:struck|stricken|hit)\b")
    if v: return v
    v = vt(r"\b(?:cyclist|bicyclist)\s+(?:struck|hit)\b")
    if v: return v
    v = vt(r"\b(?:auto|vehicle|car)\s+extrication\b")
    if v: return v
    # Sullivan formal dispatch puts the house immediately after the complaint.
    # That number is not apparatus chatter when a typed house-road follows.
    if profile == "sullivan":
        mva = re.search(r"\b(?:a\s+)?(?:priority|prior)\s+response\s+"
                        r"(motor vehicle accident)\s*[,;.]?\s+\d{1,5}\s+"
                        r"(?:[a-z][a-z'-]*\s+){1,5}"
                        r"(?:street|st|road|rd|avenue|ave|drive|dr)\b", t)
        if mva:
            return _addr_title(mva.group(1))
        alert = re.search(r"\b(?:medical alert activation|activated medical alert)\b", t)
        if alert and not re.search(r"\b(?:test|testing|training|cancelled|canceled)\b"
                                  r"|\b(?:no|not|negative)\s+(?:a\s+)?medical alert", t):
            return "Medical Alert Activation"
    if profile == "sullivan":
        pump = re.search(r"\bcellar pump[ -]?out\b", t)
        if pump and not re.search(r"\b(?:no|not|test|training|drill)\s+(?:\w+\s+){0,2}$", t[max(0,pump.start()-30):pump.start()]):
            return "Cellar Pump-Out"
        injury = re.search(r"\bknee injury\b", t)
        if injury and not re.search(r"\b(?:no|not|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", t[max(0,injury.start()-35):injury.start()]):
            return _addr_title(injury.group())
    v = vt(r"\b(?:mva|mvc|motor vehicle accident|rollover|entrapment|car accident|auto accident|vehicle accident)\b")
    if v: return v
    if profile == "hatzolah":
        # Preserve the explicit police dispatch request, with no injury claim.
        for m in re.finditer(r"\bpd\s+requesting\s+(?:they\s+have\s+a\s+)?jumper\s+down\b", t):
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$",
                             t[max(0,m.start()-40):m.start()]):
                return "Pd Requesting Jumper Down"
        # Explicit dispatch complaint, not a diagnosis inferred from routing.
        # A bare EDP unit label or mental-health training is not a complaint.
        for m in re.finditer(r"\b(?:edp|psych)\s+situation\b", t):
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$",
                             t[max(0,m.start()-40):m.start()]):
                return _addr_title(m.group())
    if profile == "hatzolah":
        v = vt(r"\bnasal obstruction\b")
        if v and re.search(r"\b(?:child|patient|male|female)\b", t):
            return v
    if profile == "hatzolah":
        # Radio complaint wording only. Preserve the actual ASR phrase, not a
        # diagnosis or an inferred street number from the surrounding readout.
        for m in re.finditer(r"\b(?:severe difficulty breather|severe deep breather|severe breather|very big breather)\b", t):
            if re.search(r"\b(?:for|we have|patient|male|female|child)\b", t[max(0,m.start()-45):m.start()]) and not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", t[max(0,m.start()-40):m.start()]):
                return _addr_title(m.group())
    v = vt(r"difficulty breathing|trouble breathing|shortness of breath|can't breathe|cant breathe|cannot breathe|not breathing|respiratory distress|turning blue")
    if v: return v
    if profile == "hatzolah":
        for pattern in [r"\b(?:for|with)\s+(?:a\s+)?(burn|scald)(?:\s+to\s+(?:a\s+)?\d{1,3}[- ]year[- ]old)?\b",
                        r"\b(possible\s+fracture|fracture)\b", r"\bfor\s+(?:a\s+|the\s+)?(cardiac)\b(?!\s+(?:arrest|patient))",
                        r"\bfor\s+(?:a\s+)?(lifeline\s+call)\b"]:
            m = re.search(pattern,t,re.I)
            if m and not re.search(r"\b(?:no|not|negative|training|test)\b.{0,20}$",t[max(0,m.start()-30):m.start()]):
                return _addr_title(m[1])
    v = vt(r"\b(?:cardiac arrest|heart attack|full arrest|cpr in progress)\b")
    if v: return v
    v = vt(r"\b(?:unresponsive|not responsive)\b")
    if v: return v
    # Sullivan EMS dispatch: "man down, unknown life status" is a spoken
    # complaint, not a diagnosis. Preserve exactly the supplied uncertainty.
    if profile == "sullivan":
        v = vt(r"\bman down(?:,?\s+unknown life status)?\b")
        if v: return v
    if ("hatzal" in profile.lower() or "hatzol" in profile.lower()) and \
            re.search(r"\b(?:patient|child|kid|baby|person|infant)\b.{0,30}\bnot acting right\b", t):
        v = vt(r"\bnot acting right\b")
        if v: return v
    v = vt(r"\bchok(?:ing|e)\b")
    if v: return v
    v = vt(r"\b(?:overdose|o\.d\.|narcotic)\b")
    if v: return v
    v = vt(r"\b(?:accident|collision|crash)\b")
    if v: return v
    v = vt(r"\b(?:stroke|cva)\b")
    if v: return v
    v = vt(r"\b(?:seizure|convuls\w*)\b")
    if v: return v
    if re.search(r"\b(?:fall|fell)\b", t):
        return "Fall"  # tense cleanup only; Hatzalah 'Fall' exclusion depends on it
    v = vt(r"\b(?:bleeding|hemorrhage)\b")
    if v: return v
    v = vt(r"\b(?:general illness|general ill|generally ill|gi distress)\b")
    if v: return v
    # Spoken medical complaint in the dispatch, not the response unit:
    # "elderly patient not feeling well" is a nature even without a prior
    # category keyword. Capture the complaint words themselves; no illness
    # diagnosis or guessed GI label is added.
    v = vt(r"\b(?:not feeling well|feeling unwell|feels unwell|feels ill|"
           r"feeling ill|doesn'?t feel well|does not feel well)\b")
    if v and re.search(r"\b(?:patient|male|female|elderly|sick person|"
                       r"year[- ]old|child|adult)\b", t):
        return v
    if profile == "sullivan" and re.search(r"\b(?:female|male|patient|person)\b.{0,25}\bmental health\b", t) and not re.search(r"\b(?:no|not|negative)\s+mental health\b", t):
        return "Mental Health"  # spoken complaint only, no diagnosis added
    if profile == "sullivan":
        for m in re.finditer(r"\bankle injury\b", t):
            if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$",
                             t[max(0,m.start()-40):m.start()]):
                return _addr_title(m.group())
    v = vt(r"\bchest pain\b")
    if v: return v
    v = vt(r"\bdrown\w*\b")
    if v: return v
    v = vt(r"\b(?:near syncope|syncope|faint(?:ed|ing)?|passed out)\b")
    if v: return v
    v = vt(r"\bdiabet\w*\b|\b(?:low|high)\s+(?:blood\s+)?sugar\b")
    if v: return v
    v = vt(r"\ballergic\b|\banaphyla\w*\b|\bbee sting\b")
    if v: return v
    v = vt(r"\babdominal\b|\bstomach pain\b")
    if v: return v
    v = vt(r"\baltered mental\b|\b(?:pationt|patient)?\s*ams\b|\bdisoriented\b")
    if v: return v
    v = vt(r"\bfire\s+in\s+a\s+private\s+dwelling\b|\bprivate\s+dwelling\s+fire\b")
    if v: return v
    v = vt(r"\bpossible structure fire\b")
    if v: return v
    v = vt(r"\b(?:structure|building|house)\s+fire\b")
    if v: return v
    v = vt(r"\bfire\s+in\s+the\s+kitchen\s+of\s+(?:a\s+)?restaurant\b")
    if v: return v
    v = vt(r"\bkitchen fire\b|\bstove fire\b")
    if v: return v
    v = vt(r"\b(?:car|vehicle|auto)\s+fire\b")
    if v: return v
    # Hatzalah uses "full trauma" as a distinct obstetric code. Preserve
    # the whole spoken phrase rather than collapsing it to "Trauma".
    if profile == "hatzolah":
        v = vt(r"\bfull\s+trauma\b")
        if v: return v
    v = vt(r"\btrauma\b")
    if v: return v
    v = vt(r"\bunconscious\b")
    if v: return v
    v = vt(r"(?<![\d-])\bcode\b(?!\s*\d)")
    if v: return v
    v = vt(r"\b(?:unstable|unsafe)\s+facade\b")
    if v: return v
    v = vt(r"\b(?:water condition|water leak|burst pipe)\b")
    if v: return v
    v = vt(r"\bsprinkler\w*\b")
    if v: return v
    v = vt(r"\bmanhole\b")
    if v: return v
    if profile == "fdny":
        v = vt(r"\belectrical fire\b")
        if v: return v
    if profile == "fdny":
        m = re.search(r"\b(?:for|reporting)\s+(?:a\s+)?(wires?\s+burning)(?:\s+(?:on|in)\s+(?:a\s+)?private\s+(?:dwelling|house))?\b",t,re.I)
        if m and not re.search(r"\b(?:no|not|negative)\b.{0,20}$",t[max(0,m.start()-25):m.start()]):
            return _addr_title(m[1])
    v = vt(r"\b(?:electrical|wires down|transformer)\b")
    if v: return v
    if (profile == "fdny" and not _negative_fire_context(t)
            and len(set(re.findall(r"\bbox\s*(\d{2,4})\b", t, re.I))) <= 1):
        # The complaint outranks the equipment involved. Keep only a local
        # smoke/elevator phrase, never smoke from a different request.
        elevator_smoke = re.search(
            r"\bodou?r\s+of\s+smoke(?:\s+(?:from|in|at)\s+(?:the\s+)?|\s*[,;]\s*(?:the\s+)?)elevator\b", t)
        if elevator_smoke and not re.search(r"\b(?:no|not|without|negative)\s+$",
                         t[max(0,elevator_smoke.start()-18):elevator_smoke.start()]):
            return "Odor of Smoke from the Elevator"
    v = vt(r"\bstuck occupied elevator\b|\belevator\b")
    if v: return v
    if profile == "fdny":
        for pattern in [r"\bgas detector activation\b", r"\bgas alarm\b", r"\bboat in distress\b"]:
            for m in re.finditer(pattern, t):
                if not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+(?:\w+\s+){0,2}$", t[max(0,m.start()-30):m.start()]):
                    return _addr_title(m.group(0))
    v = vt(r"\b(?:co alarm|carbon monoxide)\b")
    if v: return v
    if profile == "fdny":
        # Keep a location/occupancy detail when dispatch speaks it as part
        # of the complaint. Do not manufacture a floor or building type.
        m_smoke = re.search(r"\bsmoke\s+in\s+the\s+(?:basement|cellar)\s+of\s+a\s+"
                            r"(?:private dwelling|multiple dwelling)\b", t)
        if m_smoke:
            return _addr_title(m_smoke.group(0))
    if profile == "fdny" and not _negative_fire_context(t):
        rear = re.search(r"\bfire\s+in\s+the\s+rear\b(?:\s*[,;]?\s*(?:of\s+a\s+)?(?:private|multiple)\s+dwelling\b)?", t)
        if rear:
            return _addr_title(rear.group(0))
    # A concrete FDNY complaint is more informative than its transmission
    # type. Capture a bounded spoken phrase after "reporting"/"for" rather
    # than a bare fire/smoke word elsewhere in a multi-job transcript.
    # No arbitrary noun phrase becomes an alert; recognized complaint heads
    # and bounded location details are required. Known structured natures
    # above (including actual fire and apartment) still have precedence.
    if profile == "fdny":
        complaint = re.search(
            r"\b(?:reporting|for)\s+(?:an?\s+)?"
            r"(?P<nature>(?:stove|kitchen|bedroom|electrical|rubbish|garbage|"
            r"brush|vehicle|car|structure|building|house)\s+fire|"
            r"(?:odou?r\s+(?:of\s+)?(?:gas|smoke)|gas\s+odou?r)|"
            r"(?:fire|smoke)\s+(?:in|on|at)\s+(?:the\s+|an?\s+)?"
            r"(?:[a-z]+(?:\s+[a-z]+){0,2}\s+)?"
            r"(?:floor|basement|cellar|post office|lobby|hallway|stairwell|"
            r"dwelling|building|apartment)|"
            r"smoke\s+in\s+the\s+area)\b", t)
        if complaint and not _negative_fire_context(t):
            return _addr_title(complaint.group("nature"))
    # Exact dispatch complaint, not apparatus/unit chatter or a negated report.
    if profile == "fdny" and re.search(r"\b(?:for|reporting)\s+(?:(?:a\s+)?report\s+of\s+)?(?:an?\s+)?explosion\b", t, re.I) and not re.search(r"\b(?:no|not|without|negative|test|training|drill)\b.{0,20}\bexplosion\b", t, re.I):
        return "Explosion"
    # A phone-alarm transmission can name a real smoke complaint with a
    # numeric floor readout. Keep the complaint ahead of alarm fallback;
    # require the full spoken phrase, never infer a floor from a loose digit.
    if profile == "fdny" and not _negative_fire_context(t):
        floor = re.search(r"\bsmoke\s+(?:in|on|at)\s+(?:the\s+|an?\s+)?"
                          r"(?:(?:number|no\.?)\s+)?"
                          r"(?P<level>\d{1,2}(?:st|nd|rd|th)?|"
                          r"one|two|three|four|five|six|seven|eight|nine|ten|"
                          r"first|second|third|fourth|fifth|sixth|seventh|"
                          r"eighth|ninth|tenth)\s+floor\b", t)
        if floor and not re.search(r"\b(?:no|not|without|negative)\s+$",
                                   t[max(0, floor.start()-12):floor.start()]):
            return _addr_title(floor.group(0))
    if profile == "fdny" and not _negative_fire_context(t):
        truck = re.search(r"\b(?:for|reporting)\s+(fire\s+in\s+(?:a\s+)?(?:sanitation\s+)?truck)\b", t)
        if truck and not re.search(r"\b(?:test|training|drill)\b", t):
            return _addr_title(truck.group(1))
        reversed_truck = re.search(r"\b(?:for|reporting)\s+(?:a\s+)?"
                                   r"((?:sanitation\s+)?truck\s+on\s+fire)\b", t)
        if reversed_truck and not re.search(r"\b(?:test|training|drill)\b", t):
            return _addr_title(reversed_truck.group(1))
        vehicle_fire = re.search(r"\b(?:truck|car|vehicle)\s+fire\b", t)
        if vehicle_fire:
            return _addr_title(vehicle_fire.group(0))
    # Water rescues are eligible natures (user instruction relayed by main, 10/1 23:12 EEST).
    if not _negative_fire_context(t):
        water = re.search(
            r"\b(?:(?:person|man|woman|male|female|child|kid|body|jumper|swimmer|diver|boater|vehicle|car)s?\s+(?:is\s+|are\s+)?(?:in|into)\s+the\s+water|"
            r"(?:swift\s+water\s+rescue|water\s+rescue|ice\s+rescue)|"
            r"(?:person|persons|swimmer|boater|boat|vessel)\s+in\s+distress\s+(?:in|on)\s+the\s+water|"
            r"(?:boat|vessel)\s+(?:in\s+distress|capsized|sinking)|"
            r"capsized\s+(?:boat|vessel)|jumper\s+in\s+the\s+water|"
            r"person\s+(?:in\s+the\s+)?(?:river|bay|canal|creek|lake|pond))\b", t)
        if water and not re.search(r"\b(?:no|not|without|negative|test|training|drill)\s+$",
                                   t[max(0, water.start()-12):water.start()]):
            w = re.sub(r"\s+", " ", water.group(0)).strip()
            w = re.sub(r"^(?:persons?|man|woman|male|female|child|kid|body|jumper|swimmer|diver|boater|vehicle|car)s?\s+(?:is\s+|are\s+)?(?:in|into)\s+the\s+water$",
                       lambda m: ("Person in the Water" if not re.match(r"(?:vehicle|car)", m.group(0), re.I) else "Vehicle in the Water"), w, flags=re.I)
            return _addr_title(w)
    # A spoken smoking/smoke-in-apartment complaint is a smoke job.
    if profile == "fdny" and not _negative_fire_context(t):
        smk_apt = re.search(r"\b(?:smoking|smoke\s+in|smoke\s+condition\s+in)\s+(?:the\s+)?apartment\b(?P<rest>\s+\d{1,3}\s*[a-z]?\b)?", t)
        if smk_apt:
            return "Smoke" if smk_apt.group("rest") else "Smoke in Apartment"
    v = vt(r"\b(?:rubbish fire|garbage fire|trash fire|rubbish)\b")
    if v: return v
    v = vt(r"\b(?:outside fire|brush fire)\b")
    if v: return v
    v = vt(r"\baided\b")
    if v: return v
    # An explicit gasoline odor is a complaint, not the phone-alarm prefix.
    gasoline = re.search(r"\bodou?r\s+(?:of\s+)?gasoline\b", t)
    if gasoline and not re.search(r"\b(?:no|not|without|negative)\s+$",
                                  t[max(0, gasoline.start()-20):gasoline.start()]):
        return "Odor of Gasoline"
    # A dispatcher can say either "odor of gas" or "gas odor". Both are
    # explicit complaints and outrank the transmission type (Phone Alarm).
    v = vt(r"\b(?:odou?r (?:of )?gas|gas odou?r|odou?r (?:outside|in the area))\b")
    if v: return v
    # Confirmed FDNY ASR variants for an audible "odor of gas" complaint.
    # Only the complete two/three-word phrase qualifies, not generic "gas".
    if profile == "fdny" and re.search(r"\b(?:notre(?:\s+dame)?|motor)\s+gas\b", t):
        return "Odor of Gas"
    v = vt(r"\bgas leak\b")
    if v: return v
    # 'gas main (struck|ruptured|...)' is a content nature - box 3321 (9/28)
    # posted PHONE ALARM when 'a gas main that was ruptured by a contractor'
    # was said; box 2720 ('gas main struck') suppressed no-nature same hour
    v = vt(r"\bfumes?\b")
    if v: return v
    m_gas = re.search(r"\bgas main\b", t)
    if m_gas:
        mp = re.search(r"\b(ruptured|struck|hit|broken|leaking|leak)\b",
                       t[m_gas.end(): m_gas.end() + 40])
        return _addr_title("gas main " + mp.group(1)) if mp else "Gas Main"
    # Keep "Smoke in the area" distinct from smoke inside a building.
    # Only this spoken phrase, not a bare "smoke", earns the separate nature.
    v = vt(r"\b(?:odou?r\s+of\s+)?smoke\s+in\s+the\s+area\b")
    if v: return "Smoke in the area"
    # In a single-box FDNY phone-alarm dispatch, an explicitly spoken odor
    # of smoke is the complaint even without the word "reporting". Keep
    # negated claims and ambiguous multi-box clips out.
    if (profile == "fdny" and not _negative_fire_context(t)
            and len(set(re.findall(r"\bbox\s*(\d{2,4})\b", t, re.I))) <= 1):
        odor_smoke = re.search(r"\bodou?r\s+of\s+smoke\b", t)
        if odor_smoke and not re.search(r"\b(?:no|not|without|negative)\s+$",
                                        t[max(0, odor_smoke.start()-18):odor_smoke.start()]):
            return "Odor of Smoke"
    # A phone-alarm transmission with a job-local smoke complaint and the
    # callers' apartment is a smoke job, not a mere transmission type. The
    # apartment is captured below; require this complete complaint wording,
    # not a loose "smoke" in mixed radio chatter.
    if (profile == "fdny" and not _negative_fire_context(t)
            and len(set(re.findall(r"\bbox\s*(\d{2,4})\b", t, re.I))) <= 1):
        m_smoke_callers = re.search(
            r"\bsmoke\s*[,;.]?\s*callers?['’]?s?\s+in\s+"
            r"(?:the\s+)?apartment\s+\d{1,3}\s*[a-z]\b", t, re.I)
        if m_smoke_callers:
            return "Smoke"
    # Alarm activation is not evidence of an actual fire. Preserve the
    # spoken alarm nature, unless a specific fire complaint above won first.
    v = vt(r"\b(?:activated\s+(?:fire\s+)?alarm|fire\s+alarm\s+activation)\b")
    if v: return v
    # bare-word fire fallback is FDNY-only: on the EMS channel a lone whisper
    # 'fire' is a hallucination until proven ('I can't have fake coming thru'
    # 9/28) - Hatzalah fire jobs still match the structured patterns above
    if "hatzal" not in profile.lower() and "hatzol" not in profile.lower():
        m = re.search(r"\b(?:fire|smoke|burning)\b(?!\s*—)", t)
        if m and not _negative_fire_context(t) and not re.search(
                r"\b(?:activated\s+(?:fire\s+)?alarm|fire\s+alarm\s+activation|"
                r"(?:fire|smoke|automatic|phone|still)\s+alarm|alarm\s+activation)\b", t):
            return _addr_title(m.group(0))
    if profile == "fdny" and not _negative_fire_context(t):
        v = vt(r"\b(?:reporting|for)\s+(?:an?\s+)?(?:fire|smoke)\b")
        if v:
            return "Fire" if re.search(r"\bfire\b$", v, re.I) else "Smoke"
    # transmission-type fallbacks are LAST RESORT - content natures above
    # always win ('phone alarm... fire in a private dwelling' must post the
    # fire, not the alarm type; 6:04 AM E 84th St job 9/28)
    v = vt(r"\b(?:fire|smoke|automatic|smoke detector|co)\s+alarm\b|\balarm activation\b")
    if v: return v
    # user ruling 9/28 19:54: on FDNY a class-3 readout posts as 'Automatic
    # Alarm', never 'Class 3'. NOT routed through vt(): the readout number
    # follows directly ('class 3 383') and must not trip the unit-chatter
    # digit-skip.
    m3 = re.search(r"\bclass\s*3\b", t)
    if m3:
        return "Automatic Alarm" if profile == "fdny" else _addr_title(m3.group(0))
    v = vt(r"\bstill alarm\b")
    if v: return v
    # "Phone alarm" is the box/transmission type, never a nature (owner ruling
    # 10/1 23:12 EEST). Without a spoken complaint the nature stays empty.
    # EMS/ambulance/BLS are apparatus or response language, not a complaint.
    # A job without a discernible complaint stays suppressed by verify_and_send.
    v = vt(r"\b(?:sick person|medical emergency)\b")
    if v: return v
    return ""


# ---------------------------------------------------------------------------
# Chatter filter + top-level decision
# ---------------------------------------------------------------------------
_CHATTER_RE = re.compile(
    r"\b(?:check your whatsapp|sent you a whatsapp|whatsapp for updates|"
    r"on whatsapp|shift change|roster update|good morning|good night|"
    r"radio check|test test)\b", re.I)


# Hatzalah dispatches often open "Any units in <place> for <nature>" - no
# formal address, but it IS a job. Matches the whole tail; address resolution
# still prefers a real street mention inside it.
_CROSS_STOPWORDS = {
    "for", "the", "and", "with", "units", "year", "old", "male", "female",
    "elderly", "any", "needed", "responding", "respond", "have", "has",
}


_ANY_UNITS_RE = re.compile(
    r"\bany\s+units?\s+(?:needed\s+)?(?:in|to|at)\s+(.{2,120})"
    r"|\bany\s+innocent\s+(.{2,120})"
    r"|\bbanana\s+(.{2,120})"  # whisper slur of "any units in a" on bad audio
    r"|\bany\s+units?\s+(?:that\s+be\s+|to\s+be\s+)?available\s+for\s+a\s+\w*bus\w*\b"
    r"()", re.I)  # Hatzolah 'bus' = ambulance request opener (53rd St job 9/28)


def is_chatter(text: str) -> bool:
    if not _CHATTER_RE.search(text):
        return False
    if detect_box(text):
        return False
    if extract_dispatch_address(text, "hatzolah") or extract_dispatch_address(text, "sullivan"):
        return False
    return True



# ---------------------------------------------------------------------------
# PRIORITY (life-threat) keyword list - the one obvious spot to tune.
# Any alert whose transcript contains one of these lowercase substrings gets
# hit["priority"] = True and a 🚨 PRIORITY tag in the group message.
# EMS (Hatzalah) and fire/rescue (Sullivan/FDNY) vocabulary mixed; edit freely.
# ---------------------------------------------------------------------------
PRIORITY_KEYWORDS = [
    "cpr",
    "respiratory distress",
    "difficulty breathing",
    "cardiac",
    "pediatric",
    "unconscious",
    "unresponsive",
    "not breathing",
    "no pulse",
    "cardiac arrest",
    "choking",
    "anaphylax",
    "overdose",
    "severe bleeding",
    "mva with injuries",
    "pedestrian struck",
    "entrapment",
    "trapped",
    "drowning",
    "electrocution",
    "structure fire",
    "working fire",
    "fire in the structure",
    "people trapped",
]


def is_priority(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in PRIORITY_KEYWORDS)



# abbreviation-blind street identity for the self-leak cross filter
_STREET_CANON = {"hwy": "highway", "st": "street", "ave": "avenue",
                 "blvd": "boulevard", "rd": "road", "dr": "drive",
                 "pl": "place", "ln": "lane", "pkwy": "parkway",
                 "ct": "court", "ter": "terrace", "expwy": "expressway"}


def _canon_street(s: str) -> str:
    """'Kings Hwy' == 'Kings Highway': box 3321 (9/28) posted its own street
    in the cross line because the leak check compared raw strings."""
    w = re.sub(r"^\s*\d+[a-zA-Z-]*\s+", "", s.strip().lower()).split()
    return " ".join(_STREET_CANON.get(x, x) for x in w)


def _merge_split_ordinals(t: str) -> str:
    """Whisper splits a numbered street's ordinal into lone digits ('515 8 1
    Street' = 515 81st Street - box 2720 gas-main job 9/28 suppressed with
    the garbled '8 1 Street'). Merge two lone digits directly before a
    street-type word. Space-separated pairs only (hyphenated '10-4' codes
    untouched); merged value must be a plausible street number (< 200)."""
    def _rep(m):
        n = int(m.group(1) + m.group(2))
        if n >= 200:
            return m.group(0)
        return _ordinal_street_num(n) + " "
    return re.sub(
        r"\b(\d)\s+(\d)\s+(?=(?:street|st|avenue|ave|boulevard|blvd|road|rd|"
        r"drive|dr|place|pl|lane|ln|parkway|pkwy|court|ct|terrace|ter)\b)",
        _rep, t, flags=re.I)



_PHONETIC = {"adam": "A", "alpha": "A", "boy": "B", "baker": "B", "bravo": "B",
             "charles": "C", "charlie": "C", "david": "D", "edward": "E",
             "frank": "F", "george": "G", "henry": "H", "ida": "I",
             "john": "J", "king": "K", "lincoln": "L", "mary": "M", "mike": "M",
             "nora": "N", "ocean": "O", "peter": "P", "queen": "Q",
             "robert": "R", "romeo": "R", "sam": "S", "tom": "T", "union": "U",
             "victor": "V", "william": "W", "x-ray": "X", "xray": "X",
             "young": "Y", "zebra": "Z"}
# The Hatzalah address alphabet is separate from the FDNY apartment phonetics.
# An absent Hatzalah street letter does not revoke the FDNY's spoken apartment.



def extract_apartment(text: str) -> str:
    """Spoken apartment detail -> 'Apartment 1R' (user 9/28: 'Smoke apartment
    1L, 1R, whatever's being said'). FDNY reads the letter phonetically
    ('apartment 1 Robert' = 1R). 'unit N' is apparatus, not an apartment -
    only 'apartment/apt' count."""
    t = _norm(text).lower()
    # ASR punctuation is a separator, not part of a spoken apartment ID.
    # Stay inside the explicit apartment phrase and existing phonetic map.
    t = re.sub(r"(\b(?:apartment|apt)s?)\s*,\s*", r"\1 ", t)
    numbers = {"one":"1", "two":"2", "three":"3", "four":"4", "five":"5",
               "six":"6", "seven":"7", "eight":"8", "nine":"9"}
    t = re.sub(r"\b(apartment|apt)\s+(one|two|three|four|five|six|seven|eight|nine)\b",
               lambda m: m[1] + " " + numbers[m[2]], t)
    t = re.sub(r"(\b(?:apartment|apt)s?\s+\d{1,3})\s*,\s*", r"\1 ", t)
    m = re.search(r"\b(?:apartment|apt)s?\s+(\d{1,3})\s+([a-z][a-z\-]+)\b", t)
    if m and m.group(2) in _PHONETIC:
        return "Apartment " + m.group(1) + _PHONETIC[m.group(2)]
    m = re.search(r"\b(?:apartment|apt)s?\s+(\d{1,3})\s*([a-z])?\b", t)
    if m:
        return "Apartment " + m.group(1) + (m.group(2) or "").upper()
    m = re.search(r"\b(?:apartment|apt)s?\s+([a-z][a-z\-]+)\s+(\d{1,3})\b", t)
    if m and m.group(1) in _PHONETIC:
        return "Apartment " + _PHONETIC[m.group(1)] + m.group(2)
    m = re.search(r"\b(?:apartment|apt)s?\s+([a-z][a-z\-]+)\b", t)
    if m and m.group(1) in _PHONETIC:
        return "Apartment " + _PHONETIC[m.group(1)]
    return ""


def fdny_suffixless_address(text: str) -> str:
    """Keep an explicit all-hands address; never infer its road type."""
    if not re.search(r"\ball hands\b", text, re.I):
        return ""
    if len(set(re.findall(r"\bbox\s*(\d{2,4})\b", text, re.I))) != 1:
        return ""
    matches = list(re.finditer(
        r"\b(?:the\s+)?address\s+is\s+(\d{1,5})\s+"
        r"([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}?)"
        r"(?=[.,;]|$)", text, re.I))
    values = {m.group(1) + " " + _addr_title(m.group(2)) for m in matches}
    if len(values) != 1:
        return ""
    value = values.pop()
    if re.search(r"\b(?:street|st|avenue|ave|road|rd|drive|dr|place|pl|lane|ln|"
                 r"boulevard|blvd|court|ct|parkway|pkwy)\b", value, re.I):
        return ""
    if any(word.lower() in _NAME_STOP for word in value.split()[1:]):
        return ""
    return value


def fdny_spoken_road_pair(text: str) -> tuple[str, str] | None:
    """A single-box bare-road dispatch, never an inferred house/cross."""
    boxes = {m[1].zfill(4) for m in re.finditer(r"\bbox\s+(\d{2,4})\b", text, re.I)}
    if len(boxes) != 1:
        return None
    # Named bare-road corners explicitly tied to one box and a complaint.
    # Do not absorb unit words, a numbered house or two different corners.
    named = r"(?:[A-Za-z][A-Za-z'-]*\s+){1,2}(?:Street|Avenue|Road|Boulevard|Parkway)"
    named_matches = list(re.finditer(
        r"\bbox\s+\d{2,4}\s*[,;]?\s*(?:located\s+at\s+|it'?s\s+)?("+named+r")\s*(?:and|&)\s*("+named+r")\s+(?:for|reporting)\b", text, re.I))
    named_pairs = {(_addr_title(m[1]),_addr_title(m[2])) for m in named_matches}
    if len(named_pairs) == 1:
        return next(iter(named_pairs))
    if len(named_pairs) > 1:
        return None
    road = r"(?:East|West|North|South)\s+\d{1,3}(?:st|nd|rd|th)?\s+(?:Street|St)"
    second = r"(?:[A-Za-z][A-Za-z'-]*\s+){1,3}(?:Avenue|Ave|Street|St|Parkway|Pkwy)"
    matches = list(re.finditer(r"\bbox\s+\d{2,4}\s*[,;]?\s*(?:it'?s\s+)?("+road+r")\s*(?:,|and|&)\s*(?:the\s+)?("+second+r")\s*[,;]", text, re.I))
    pairs = {(_addr_title(m[1]),_addr_title(m[2])) for m in matches}
    return next(iter(pairs)) if len(pairs) == 1 else None


def fdny_request_text(text: str) -> str:
    """Isolate a complete dispatch from preceding unit chatter/fragments.
    Distinct complete box dispatches remain unsplit and fail closed.
    """
    normalized = _split_box_glue(_norm(text))
    openers = list(re.finditer(r"\b(?:phone\s+alarm\s+)?box\s*[,;:]?\s*(\d{3,4})\s*[,;:]?\s+(?=\d{1,5}\s+)", normalized, re.I))
    if not openers:
        # Observed Calls transcription can omit the word Box. Require the
        # same four-digit dispatch ID and full house/road repeated twice,
        # following an explicit completed-unit update, never a lone number.
        repeat = list(re.finditer(r"\b(\d{4})\s+(\d{1,5}\s+(?:East|West|North|South)?\s*\d{1,3}(?:st|nd|rd|th)?\s+Street)\b", normalized, re.I))
        if len(repeat) >= 2 and len({(m[1],m[2].casefold()) for m in repeat}) == 1:
            prefix = normalized[:repeat[0].start()]
            tail = normalized[repeat[0].start():]
            if re.search(r"\bno extension\b", prefix, re.I) and get_nature(tail, "fdny"):
                return tail
        return text
    if len({m.group(1).zfill(4) for m in openers}) != 1:
        return text
    first = openers[0]
    tail = normalized[first.start():]
    if not extract_dispatch_address(tail, "fdny") or not get_nature(tail, "fdny"):
        return text
    prefix = normalized[:first.start()]
    if re.search(r"\b(?:Queens|Bronx|Manhattan|Staten Island)\b", prefix, re.I):
        return text
    if re.search(r"\b\d{1,5}\s+(?:[A-Za-z][A-Za-z'-]*\s+){0,3}(?:Street|Avenue|Road|Place|Lane)\b", prefix, re.I):
        return text
    if first.start() and (fdny_clipped_cross_only(prefix) or re.search(
            r"\b(?:10[- ]?26|no extension|units in the process|to Brooklyn|responding)\b", prefix, re.I)):
        return tail
    return text


def fdny_clipped_cross_only(text: str) -> bool:
    """A mid-readout cross cannot stand in for the missing incident street."""
    return bool(re.match(r"^\s*(?:(?:street|st|avenue|ave|road|rd|place|pl|boulevard|blvd|parkway|pkwy)\s+)?off\s+(?:of\s+)?",
                         text or "", re.I))


def sullivan_single_job_repeat(text: str) -> bool:
    t = text or ""
    if re.search(r"\b(?:first|third|fourth|1st|3rd|4th)\s+(?:call|job)\b|\b(?:two|2) calls\b|\b(?:another|new) (?:job|call)\b", t, re.I):
        return False
    markers = list(re.finditer(r"\b(?:second|2nd) call\b", t, re.I))
    if len(markers) != 2:
        return False
    road = r"(?:[A-Za-z][A-Za-z'-]*\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Court|Ct|Lane|Ln|Way)\b"
    pair = re.compile(r"\b(?:in|from) the area of (?P<a>"+road+r")\s+(?:and|&)\s+(?P<b>"+road+r")", re.I)
    spans = [t[markers[0].end():markers[1].start()], t[markers[1].end():]]
    pairs=[]; natures=[]
    for span in spans:
        matches=list(pair.finditer(span))
        if len(matches)!=1:
            return False
        m=matches[0]
        names=tuple(re.sub(r"\s+"," ",m[x].strip().lower()) for x in ('a','b'))
        # A house or a third typed road makes this more than one anchored job.
        rest=span[:m.start()]+span[m.end():]
        if re.search(road,rest,re.I) or re.search(r"\b\d{1,5}\s+"+road,span,re.I):
            return False
        nature = ('possible structure fire' if re.search(r'\bpossible structure fire\b',span,re.I) else 'odor of smoke' if re.search(r'\bodor of smoke\b',span,re.I) else get_nature(span,'sullivan'))
        if not nature or not re.search(r"\b(?:odor of smoke|smoke in the area|possible structure fire)\b",span,re.I):
            return False
        complaint = span[:m.start()].strip(" ,.").casefold()
        if complaint not in ("odor of smoke", "smoke", "possible structure fire, odor of smoke", "possible structure fire"):
            return False
        ending = span[m.end():]
        expected = (r"[. ,]*For Monticello,?\s+a\s*" if len(pairs)==0 else r"[. ,]*\d{0,4}[. ,]*")
        if not re.fullmatch(expected,ending,re.I):
            return False
        pairs.append(names);natures.append(nature.casefold())
    if re.search(road,t[:markers[0].start()],re.I) or re.search(r"\b\d{1,5}\s+(?:[A-Za-z]+|Broadway)\b",t[:markers[0].start()],re.I):
        return False
    prefix = t[:markers[0].start()]
    if not re.fullmatch(r"\s*(?:Sullivan County )?Dispatch to [A-Za-z ]+Fire[, .]*",prefix,re.I):
        return False
    return pairs[0]==pairs[1] and natures[0]==natures[1]


def sullivan_numbered_jobs(text: str, profile: str) -> bool:
    """Explicit new numbered dispatches are not one address/complaint span.

    A second page, second response, or single first-call repeat is not a new
    incident boundary. Hold an explicit second/third call even when the first
    opener is clipped. Do not try to choose one job from this recording.
    """
    if profile.removeprefix("zello-") != "sullivan":
        return False
    numbered = bool(re.search(r"\b(?:second|third|fourth|2nd|3rd|4th)\s+(?:call|job)\b",
                              text or "", re.I))
    if not numbered:
        return False
    # A second-call re-page can be one repeated job, not two jobs. Require
    # two complete complaint/location spans, identical typed intersections,
    # and no extra road, house or distinct dispatch ordinal anywhere.
    if sullivan_single_job_repeat(text):
        return False
    # This recorded re-page names one patient site. "Second call" belongs
    # to Bethel's mutual-aid crew routing, not a second patient address.
    # Other numbered jobs, another opener or another house retain the hold.
    routing = re.search(r"\bdispatch to Bethel,?\s+(?:a\s+)?second call,?\s+"
                        r"mutual aid to Empress,?\s+County 5262,?\s+first response\b", text or "", re.I)
    houses = {re.sub(r"\s+", " ", m.group().lower()) for m in re.finditer(
        r"\b\d{1,5}\s+(?:[A-Za-z][A-Za-z'-]*\s+){1,4}"
        r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Way|Lane|Ln)\b", text or "", re.I)}
    if (routing and houses == {"10 pleasant street"}
            and re.search(r"\bMonticello (?:Police Department|PD)\b", text, re.I)
            and re.search(r"\bmale mental health emergency\b", text, re.I)
            and not re.search(r"\b(?:first call|third call|fourth call|2 calls|two calls|another job|new call)\b", text, re.I)
            and len(re.findall(r"\bsecond call\b", text, re.I)) == 1):
        return False
    return True


def split_dispatch_jobs(text: str, profile: str) -> list[str]:
    """Split an overlapped Sullivan clip at a NEW dispatch opener, never at a
    repeat/second page within the same job. Nature and address must be read
    from the same span. A leading partial job is kept independently, rather
    than glued to a later complete dispatch.
    """
    if profile == "fdny":
        if re.search(r"\bbox\s+\d{5,}\b", text, re.I):
            return [text]  # ambiguous glued runs must retain their original guard
        normalized = _split_box_glue(_norm(text))
        openers = list(re.finditer(r"\b(?:phone\s+alarm\s+)?box\s*[,;:]?\s*(\d{3,4})\b", normalized, re.I))
        boxes = {m.group(1).zfill(4) for m in openers}
        if len(boxes) < 2:
            return [fdny_request_text(text)]
        prefix = normalized[:openers[0].start()]
        if re.search(r"\b\d{1,5}\s+(?:[A-Za-z][A-Za-z'-]*\s+){0,3}(?:Street|Avenue|Road|Place|Lane)\b", prefix, re.I):
            return [text]
        bounds = [m.start() for m in openers] + [len(normalized)]
        spans = [normalized[a:b].strip() for a,b in zip(bounds,bounds[1:])]
        # Only split complete numbered, typed-road dispatches. A missing
        # complaint stays held, never borrowing another span's complaint.
        for span in spans:
            address = extract_dispatch_address(span, "fdny") or ""
            nature = get_nature(span, "fdny")
            if not re.match(r"^\d{1,5}\s+", address) or not nature or re.fullmatch(r"phone alarm|fire alarm|class 3", nature, re.I):
                return [text]
        # Borough/unit prefixes between jobs cannot be silently dropped.
        if re.search(r"\b(?:Queens|Bronx|Manhattan|Staten Island)\b", normalized, re.I):
            return [text]
        return spans
    if profile.removeprefix("zello-") in ("hatzolah", "hatzalah"):
        # A complete earlier street-pair request cannot donate its location
        # to a later numbered-house complaint. Split only on explicit house
        # plus directional numbered-road evidence, never bare crew numbers.
        bounds = [0]
        # A new explicit request owns its own location and complaint. Crew
        # acknowledgements and backup requests without a complaint are not
        # incident boundaries. Keep the earlier span, even if incomplete.
        requests = list(re.finditer(
            r"\bany\s+units?\s+(?:(?:in|from)\s+(?:the\s+)?[A-Za-z][A-Za-z -]{0,35}\s+|"
            r"(?:available|free|to be|that be)\s+)?(?:for\s+)?", text or "", re.I))
        for index, opener in enumerate(requests):
            end = requests[index + 1].start() if index + 1 < len(requests) else len(text)
            candidate = text[opener.start():end]
            if opener.start() > 0 and extract_dispatch_address(candidate, "hatzolah") and get_nature(candidate, "hatzolah"):
                bounds.append(opener.start())
        bounds = sorted(set(bounds))
        house = re.compile(r"\b\d{3,5}\s+(?:East|West|North|South)\s+\d{1,3}(?:st|nd|rd|th)?\b", re.I)
        for m in house.finditer(text or ""):
            prefix = text[max(b for b in bounds if b <= m.start()):m.start()]
            tail = text[m.end():]
            earlier = extract_direct_street_pair(prefix) or _hatzalah_dispatch_corner(prefix) or extract_audio_crosses(prefix)
            if earlier and re.search(r"\b(?:for|units? available|available for)\b", prefix, re.I) and get_nature(tail, "hatzolah"):
                bounds.append(m.start())
        bounds = sorted(set(bounds + [len(text)]))
        return [text[a:b].strip(" .,\n") for a,b in zip(bounds,bounds[1:]) if text[a:b].strip(" .,\n")]
    if profile.removeprefix("zello-") != "sullivan":
        return [text]
    openers = list(re.finditer(
        r"\b(?:sullivan(?:\s+county)?\s+dispatch|\d{1,2}\s+dispatch)\s+to\s+"
        r"(?:empress|[a-z][a-z0-9-]{2,})\b", text, re.I))
    if len(openers) < 2 and (not openers or openers[0].start() < 20):
        return [text]
    bounds = [0] + [m.start() for m in openers if m.start() >= 20]
    bounds.append(len(text))
    return [text[a:b].strip(" .,\n") for a, b in zip(bounds, bounds[1:])
            if text[a:b].strip(" .,\n")]


def hatzalah_uws_mixed_request(text: str, profile: str) -> bool:
    """Observed first complaint/corner followed by distinct UWS/Broadway request.
    Hold the whole recording, never choose its first incident or borough.
    """
    if profile.removeprefix("zello-") not in ("hatzolah", "hatzalah"):
        return False
    boundary = re.search(r"\bany\s+units?\s+on\s+the\s+upper\s+west\s+side\s+"
                         r"(?:for|to)\s+west\s+7(?:th)?\s+(?:at|and)\s+broadway\b"
                         r".{0,35}\b(?:with\s+the\s+)?backup\s+to\s+west\s+side\s+901\b", text or "", re.I)
    if not boundary:
        return False
    first = (text or "")[:boundary.start()]
    # Ground only this observed first-job shape; repeats and unit labels alone
    # cannot create a second incident. No broad locality or street aliases.
    return bool(re.search(r"\bfranklin\s+(?:and|&)\s+myrtle\b.{0,35}"
                          r"\b(?:for\s+)?child\s+difficulty\s+breathing\b", first, re.I))


def _hatzalah_mixed_backup_medic(text: str) -> bool:
    """Fail closed on backup address plus later separate medic complaint.

    Overlapping Zello clips often carry two jobs. The first full address may
    be verified but cannot become the destination of a new medic request.
    """
    # Include a preceding "backup unit" request even if the clip has one
    # conversational lead-in; do not treat bare later unit numbers as roads.
    backup = re.search(r"\b(?:backup|back\s*up)\s+units?\b", text, re.I)
    if not backup:
        return False
    addr_pat = (r"\b\d{1,5}\s+(?:[A-Za-z][A-Za-z'-]*\s+){0,3}"
                r"(?:Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd|Drive|Dr|"
                r"Place|Pl|Lane|Ln)\b")
    addr = re.search(addr_pat, text[backup.start():], re.I)
    if not addr:
        return False
    addr_end = backup.start() + addr.end()
    before = text[:addr_end]
    if get_nature(before, "hatzolah"):
        return False
    # Strong spoken request boundary, or a clear second street-number job
    # following a backup address. Do not equate bare crew IDs with streets.
    later = text[addr_end:]
    medics = re.search(r"\b(?:can\s+we\s+get|we(?:'ll|\s+will|\s+are\s+going\s+to)\s+get)"
                       r"\s+(?:the\s+)?medics?\b", later, re.I)
    other_job = re.search(r"\b(?:medics?\s+)?\d{1,3}\s+(?:and|&)\s+"
                          r"(?:\d{1,3}(?:st|nd|rd|th)?|[A-Za-z]+)\b.{0,30}"
                          r"\b(?:elderly|chest\s+pain|difficulty\s+breathing)\b", later, re.I)
    if not medics and not other_job:
        return False
    if not get_nature(later, "hatzolah"):
        return False
    # A same-job medic repeat that restates the EXACT backup address is not
    # cross-job stitching. Different or absent address stays ambiguous.
    first_address = re.search(addr_pat, before[backup.start():], re.I)
    later_address = re.search(addr_pat, later, re.I)
    if first_address and later_address and (re.sub(r"\s+", " ", first_address.group().lower().strip()) ==
                                        re.sub(r"\s+", " ", later_address.group().lower().strip())):
        return False
    return True


def hatzalah_corner_unit_repeats(text: str) -> str:
    """Remove crew numbers only when repeated around the same named corner.

    Require an earlier unnumbered dispatch corner and a matching trailing
    crew number. A numbered building or an unrelated corner remains intact.
    """
    road = r"[A-Za-z][A-Za-z'-]*\s+(?:Boulevard|Blvd|Avenue|Ave|Street|St|Road|Rd)"
    first = re.search(r"\b(?:units\s+available\s+for|units\s+for|units\s+at)\s+("+road+r")\s+(?:and|&)\s+("+road+r")\b",text,re.I)
    if not first:
        return text
    a,b = first[1],first[2]
    bname = b.rsplit(" ",1)[0]
    repeat = (r"\b(\d{1,3})\s+"+re.escape(a)+r"\s+(?:and|&)\s+"
              +re.escape(bname)+r"(?:\s+(?:Boulevard|Blvd|Avenue|Ave|Street|St|Road|Rd))?"
              +r"\s*[.,;]?\s*\1\b")
    prefix,tail = text[:first.end()],text[first.end():]
    tail = re.sub(repeat,lambda m:re.sub(r"^\d+\s+|\s*[.,;]?\s*\d+$","",m.group()),tail,flags=re.I)
    return prefix+tail

def _hatzalah_location_text(text: str) -> str:
    """Chapter/member IDs are never house numbers. Keep actual numbered roads."""
    return re.sub(r"\b(?:CH|PH|K|F|B|W|S|Y|HS)\s*[-:]?\s*\d{1,3}\b",
                  "member", text, flags=re.I)


def _hatzalah_clean_road(road: str) -> str:
    road = road.strip()
    tokens = road.split()
    while tokens and tokens[0].lower() in _NAME_STOP:
        tokens.pop(0)
    road = " ".join(tokens)
    for place in list(BERGEN_AREAS) + list(FIVE_TOWNS_AREAS) + ["Bayswater", "Crown Heights"]:
        road = re.sub(r"^" + re.escape(place) + r"\s+(?:for|at|on|to)\s+", "", road, flags=re.I)
    road = re.sub(r"^(?:any units|units|in|for|at|on|to|available for)\s+", "", road, flags=re.I)
    return road

def _hatzalah_dispatch_corner(text: str):
    """First explicit named corner, ahead of later member routing readouts.

    A bare second road remains a candidate, never a claimed full road name;
    the sender must map-check both sides before publishing the intersection.
    """
    highway = re.search(r"\b([A-Za-z][A-Za-z'-]*\s+(?:Boulevard|Blvd|Avenue|Ave|Street|St|Road|Rd))\s+(?:and|at|&)\s+(?:the\s+)?([A-Za-z][A-Za-z'-]*\s+(?:Expressway|Parkway))\b", text, re.I)
    if highway:
        return _addr_title(highway[1]), _addr_title(highway[2])
    beach = re.search(r"\b(Rockaway Beach (?:Boulevard|Blvd))\s+(?:and|at|&)\s+(Beach\s+\d{1,3}(?:st|nd|rd|th)?)(?:\s+(?:Street|St))?\b", text, re.I)
    if beach:
        return _addr_title(beach[1]), _addr_title(beach[2])
    bare = re.search(r"\b(?:to|at|on)\s+(Kingston)\s+and\s+(Montgomery)\b", text, re.I)
    if bare:
        return bare[1].title(), bare[2].title()
    road = r"[A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}\s+(?:Parkway|Pkwy|Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd)"
    m = re.search(r"\b("+road+r")\s+(?:and|&)\s+"
                  r"([A-Za-z][A-Za-z'-]*(?:\s+(?:Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd))?)\b", text, re.I)
    if not m:
        return None
    a,b=m.group(1).strip(),m.group(2).strip()
    # Do not eat a responding person's label or dispatch filler as a road.
    if any(w.lower() in _NAME_STOP or w.lower()=='member' for w in b.split()):
        return None
    a = _hatzalah_clean_road(a)
    return _addr_title(a), _addr_title(b)


def _directional_numbered_corner(text: str):
    """Explicit Manhattan-style directional numbered street, not a house.

    Require a complete named second road. Digit-by-digit numbers are accepted
    only inside this location grammar, never for patient/member fields.
    """
    digit={"zero":"0","one":"1","two":"2","three":"3","four":"4",
           "five":"5","six":"6","seven":"7","eight":"8","nine":"9"}
    words="|".join(digit)
    text=re.sub(r"\b(West|East)\s+("+words+r")[ -]+("+words+r")\b",
                lambda m:m[1]+" "+digit[m[2].lower()]+digit[m[3].lower()],text,flags=re.I)
    road=r"[A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}\s+(?:Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Boulevard|Blvd)"
    road = r"(?:" + road + r"|(?:Avenue|Ave) [ACDHIJKLMNOPRSTUVWXY])"
    m=re.search(r"\b(West|East)\s+(\d{1,3})(?:st|nd|rd|th)?(?:\s+(?:Street|St))?\s+(?:at|and|&)\s+("+road+r")\b",text,re.I)
    if not m or not 1<=int(m[2])<=299:
        return None
    n=int(m[2]);suffix="th" if 11<=n%100<=13 else {1:"st",2:"nd",3:"rd"}.get(n%10,"th")
    return f"{m[1].title()} {n}{suffix} Street",_addr_title(m[3])


def patient_age(text: str) -> str:
    """Explicit age wording only, never a bare member/unit number."""
    ages = re.findall(r"\b(\d{1,3})[ -]+(month|year|day|week)s?[ -]+old\b", text, re.I)
    distinct = {f"{int(n)}-{unit.lower()}-old" for n, unit in ages
                if 0 < int(n) <= (120 if unit.lower() == "year" else 365)}
    # Multiple different patients cannot supply one safe age line.
    return next(iter(distinct)) if len(distinct) == 1 else ""



_STYPES_X = r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Place|Pl|Lane|Ln|Parkway|Pkwy|Terrace|Ter|Court|Ct)"
_NAME_X = r"([A-Z][A-Za-z'\-]*(?:\s+[A-Z][A-Za-z'\-]*){0,2}?)"

def extract_comma_cross(text: str, addr: str) -> str | None:
    """Hatzalah comma cross: 'Kingston Avenue, Lincoln Place, in the restaurant'
    -> 'Lincoln Place'.

    Dispatch often reads the primary street, a comma, then the cross street
    with its own type. Only adjacent comma-separated street mentions count;
    the cross must differ from the incident street. Numbered streets are
    covered by the existing numbered-cross machinery and are excluded here.
    """
    t = _norm(text)
    primary = _canon_street(addr.split(",")[0]) if addr else ""
    pat = re.compile(rf"\b{_NAME_X}\s+({_STYPES_X})\s*,\s*{_NAME_X}\s+({_STYPES_X})\b")
    for m in pat.finditer(t):
        p1 = f"{m.group(1)} {m.group(2)}"
        p2 = f"{m.group(3)} {m.group(4)}"
        if _canon_street(p1) == _canon_street(p2):
            continue
        if primary and _canon_street(p1) != primary:
            continue
        return p2
    return None

_PLACE_KIND_RE = r"(?:Restaurant|Diner|Pizzeria|Deli|Bakery|Caf(?:e|é)|Pharmacy|School|Shul|Yeshiva|Hotel|Motel|Bank|Supermarket|Market|Store|Bagel|Gas Station|Bar|Grill|Kosher)"

def extract_named_place(text: str) -> str:
    """Named venue spoken with the location: "Mendy's Restaurant on Kingston
    Avenue" -> "Mendy's Restaurant"; 'in the restaurant' -> 'restaurant'.

    Detail only - never an address substitute, never a house number source.
    """
    t = _norm(text)
    m = re.search(rf"\b([A-Z][A-Za-z']+(?:'s)?(?:\s+[A-Z][A-Za-z']+(?:'s)?)?\s+{_PLACE_KIND_RE})\b", t)
    if m:
        return m.group(1)
    m = re.search(rf"\b(?:in|at|inside|into|to)\s+(?:the\s+)?({_PLACE_KIND_RE})\b", t, re.I)
    if m:
        return m.group(1).lower()
    return ""


def extract_same_street_house(text: str, addr: str) -> str:
    """A suffixless house repeat needs the same explicitly typed street here."""
    core = re.sub(r"^\d+\s+", "", addr.split(",")[0]).strip()
    typed = re.fullmatch(r"([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*){0,2})\s+(Avenue|Street|Road|Place|Ave|St|Rd|Pl)", core, re.I)
    if not typed or re.match(r"^\d", addr):
        return addr
    name = typed.group(1)
    if not re.search(r"\b" + re.escape(core) + r"\b", text, re.I):
        return addr
    houses = re.findall(r"\b(\d{1,5})\s+" + re.escape(name) + r"(?=[.,;]|$)", text, re.I)
    if len(set(houses)) != 1:
        return addr
    return houses[0] + " " + addr


def extract_repeated_bare_cross(text: str, addr: str) -> str:
    """'Walton, Walton and Harrison' repeats the primary before a bare cross.
    The bare cross stays a candidate; only map proof can give it a type.
    """
    core = re.sub(r"^\d+\s+", "", addr.split(",")[0]).strip()
    typed = re.fullmatch(r"([A-Za-z][A-Za-z.'-]+)\s+(?:Street|Avenue|Road|Place|St|Ave|Rd|Pl)", core, re.I)
    if not typed:
        return ""
    name = typed.group(1)
    m = re.search(r"\b" + re.escape(name) + r"\s*,\s*" + re.escape(name) +
                  r"\s+(?:and|&)\s+([A-Z][A-Za-z.'-]+)(?=\s*[,.;])", text)
    return m.group(1) if m and m.group(1).lower() != name.lower() else ""


def analyze(text: str, profile: str = "hatzolah") -> dict | None:
    """Return an alert dict, or None when this chunk should not alert."""
    source = profile
    if profile == "fdny":
        text = re.sub(r"^\s*\d{1,3}\s*[,;]?\s*fire\s+broken\b", "Unit to Brooklyn", text, flags=re.I)
        text = fdny_request_text(text)
    profile = profile.removeprefix("zello-")  # zello-* reuses base grammar
    if profile == "hatzalah":  # source label spelling -> grammar spelling
        profile = "hatzolah"
    if profile == "hatzolah" and _hatzalah_mixed_backup_medic(text):
        logging.info("suppressed (mixed backup and medic jobs): %s", text[:160])
        return None
    t = _merge_split_ordinals(_split_box_glue(_norm(text)))
    if profile == "hatzolah":
        # User-confirmed Hatzalah street-letter words. Replace only in an
        # avenue name, never an ordinary name or unrelated speech. Other
        # existing phonetics for FDNY apartments do not authorize new streets.
        street_letters = {
            "adam": "A", "charlie": "C", "david": "D", "henry": "H",
            "ida": "I", "john": "J", "king": "K", "larry": "L",
            "moshe": "M", "mary": "M", "nachman": "N", "nancy": "N",
            "ackman": "N",  # heard ASR variant of Nachman
            "oscar": "O", "peter": "P", "robert": "R", "sam": "S",
            "tomas": "T", "union": "U", "victor": "V", "william": "W",
            "x-ray": "X", "xray": "X", "ex ray": "X", "yellow": "Y",
        }
        t = re.sub(
            r"\b(?:Avenue|Ave)\s+(?:" + "|".join(
                sorted(map(re.escape, street_letters), key=len, reverse=True)) + r")\b",
            lambda m: "Avenue " + street_letters[m.group().split(maxsplit=1)[1].lower()],
            t, flags=re.I)
    if profile == "sullivan" and re.search(r"\bMonticello\b", t, re.I) and re.search(r"\bCottage Street\s+(?:and|&)\s+Lanfield Avenue\b", t, re.I):
        # Owner heard this exact corner and confirmed Landfield Avenue.
        # Never rewrite Lanfield at another street or in another town.
        t = re.sub(r"\bLanfield Avenue\b", "Landfield Avenue", t, flags=re.I)
    terminal_street = None
    raw_input = _norm(text)
    if profile == "sullivan":
        t = re.sub(r"\bnumber\s+(\d{1,5})\s+(?=[A-Za-z]+(?:\s+[A-Za-z]+){0,2}\s+(?:Lane|Street|Road|Drive|Place)\b)", r"\1 ", t, flags=re.I)
    if profile == "fdny":
        # A terminal ID is not a street. Strip the ID and leave a bare
        # Street fragment; only independent box+cross evidence can recover
        # a street below. Never promote a terminal number into a house.
        t = re.sub(r"\bterminal\s+(?:\d\s*){5,}(?=street\b)", "", t, flags=re.I)
        # For the independently taught 2685 dispatch, the box row and 8/9th
        # Avenue corridor corroborate the user's reading of 53rd Street.
        # Never use a generic terminal tail as a street number.
        if re.search(r"\bterminal\s+1686753\s+street\b", raw_input, re.I) \
                and re.search(r"\bbox\s+2685\b", raw_input, re.I) \
                and re.search(r"\b8(?:th)?\s+to\s+9th\s+avenues?\b", raw_input, re.I):
            terminal_street = "53rd Street"
        t = re.sub(r"\bterminal\s+\d{5,}\b", "", t, flags=re.I)
    if len(t) < 10:
        return None
    any_units = _ANY_UNITS_RE.search(t)
    head_over = _HEAD_OVER_RE.search(t)
    directional_dispatch = bool(profile == "hatzolah" and
        re.search(r"\bany units? for\b", t, re.I) and
        _directional_numbered_corner(t) and get_nature(t, profile))
    if not is_emergency(t) and not any_units and not head_over and not directional_dispatch:
        return None
    if is_chatter(t):
        return None
    glued_box = re.search(
        r"\bbox\s+\d{6}(?=\s*[,;]?\s+(?:[a-z][a-z.'-]*\s+){0,3}"
        r"(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|place|pl|"
        r"boulevard|blvd|parkway|pkwy)\b)", _norm(text), re.I)
    box_glue_ambiguous = bool(glued_box) or bool(re.search(
        r"\bbox\s+\d{5}(?=\s*[,;]?\s+(?:[a-z][a-z.'-]*\s+){0,3}"
        r"(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|place|pl)\b)",
        _norm(text), re.I))
    # A repeated complete 4-digit box takes precedence over an earlier
    # five-digit ASR glue. Remove that earlier false box token before the
    # box/house split logic; don't derive a house from a terminal panel ID.
    if profile == "fdny":
        full = re.findall(r"\bbox\s+(\d{4})\b", t, re.I)
        if full:
            t = re.sub(r"\bbox\s+\d{5,7}\b", "", t, flags=re.I)
    if profile == "hatzolah":
        t = _hatzalah_location_text(hatzalah_corner_unit_repeats(t))
        # A unit label B50 paired with 18 is not the Boro Park grid corner.
        # A separate complaint later in the clip cannot make it an address.
        t = re.sub(r"\bB\s*50\s+and\s+18\b", "B50 / 18 units", t, flags=re.I)
        # Williamsburg dispatch shorthand: only this map-testable road pair,
        # with cyclist-struck complaint and explicit checking/dispatch phrasing.
        # No historical backfill; sender independently verifies actual roads.
        if re.search(r"\b(?:cyclist|bicyclist)\s+struck\b", t, re.I) and re.search(
                r"\b(?:check\s+out|for|at|on)\s+(?:a\s+)?(?:cyclist|bicyclist)\s+struck\b", t, re.I):
            t = re.sub(r"\bKent\s+and\s+Wilson\b",
                       "Kent Avenue and Wilson Street", t, flags=re.I)
            t = re.sub(r"\bWilson\s+and\s+Kent\b",
                       "Kent Avenue and Wilson Street", t, flags=re.I)
    if profile == "hatzolah":
        # A dropped conjunction in the Bedford/Flushing radio readout is
        # recoverable only with the separate spoken 725 Bedford anchor. The
        # candidate is still tested at a real Brooklyn intersection by the
        # sender; never treat an arbitrary 'X Y Park' as a road pair.
        if re.search(r"\b725[,]?\s+Bedford\b", t, re.I) and re.search(
                r"\bBedford(?:[-,]\s*|\s+)(?:Flushing|Flossing|Sloshingham)\s+(?:Park|apart)\b", t, re.I):
            t = re.sub(r"\bBedford(?:[-,]\s*|\s+)(?:Flushing|Flossing|Sloshingham)\s+(?:Park|apart)\b",
                       "Bedford Avenue and Flushing Avenue", t, flags=re.I)
        # In this Kingston dispatch, two repeats of the named corner and an
        # independent '377 Kingston' readout outweigh the later crew numbers
        # 62/47. Only the real map intersection can make it postable.
        if re.search(r"\b377[,]?\s+Kingston\b", t, re.I) and re.search(
                r"\bKingston\s+and\s+Carroll\b", t, re.I):
            t = re.sub(r"\bKingston\s+and\s+Carroll\b",
                       "Kingston Avenue and Carroll Street", t, flags=re.I)
            t = re.sub(r"\bKingston[,]?\s+Carroll[,]?\s+and\s+Crown\b",
                       "Kingston Avenue and Carroll Street, Crown", t, flags=re.I)
    # A numbered Brighton road is often spoken as an ordinal word without
    # "Street" ("Brighton First and Brighton Beach Avenue"). Convert only
    # in an explicit location pair that includes the full second road. The
    # sender still has to verify both roads at one map intersection.
    if profile == "hatzolah":
        _BRIGHTON_ORD = {"first": "1st", "second": "2nd", "third": "3rd",
                         "fourth": "4th", "fifth": "5th", "sixth": "6th",
                         "seventh": "7th", "eighth": "8th", "ninth": "9th",
                         "tenth": "10th"}
        t = re.sub(r"\bBrighton\s+(first|second|third|fourth|fifth|sixth|seventh|"
                   r"eighth|ninth|tenth)\s+(?:and|&)\s+Brighton Beach Avenue\b",
                   lambda m: "Brighton " + _BRIGHTON_ORD[m.group(1).lower()]
                             + " Street and Brighton Beach Avenue", t, flags=re.I)
    # A spoken location intersection outranks a lone street. For a repeated
    # same-street read in one dispatch, the last complete pair is the final
    # correction (Beach/Church -> Beach/Middle Neck). Do not mix different
    # primary roads into this rule.
    three_roads = extract_spoken_three_road_location(t) if profile != "fdny" else None
    direct_pair = extract_direct_street_pair(t) if profile != "fdny" else None
    placeholder_between = bool(profile == "hatzolah" and re.search(r"\b[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){0,2}\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln|Parkway|Pkwy)\s+between\s+X\s+and\s+Y\b", t))
    if profile == "hatzolah":
        dispatch_corner = _hatzalah_dispatch_corner(t)
        if dispatch_corner:
            direct_pair = dispatch_corner
        if _rego_saunders_corner(t):
            direct_pair = ("Saunders Street", "64 Road")

    if three_roads:
        direct_pair = (three_roads[0], three_roads[1])
    if placeholder_between:
        direct_pair = None
    if profile == "hatzolah" and direct_pair:
        first = direct_pair[0]
        later = list(re.finditer(
            r"\b" + re.escape(first) + r"\s+(?:and|&)\s+"
            r"([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}\s+"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl))\b",
            t, re.I))
        if later and later[-1].group(1).lower() != direct_pair[1].lower():
            direct_pair = (first, later[-1].group(1))
    spoken_pair = extract_audio_crosses(t) if profile != "fdny" else None
    if direct_pair and spoken_pair and spoken_pair.split("&", 1)[0].strip().lower() == direct_pair[0].lower():
        spoken_pair = f"{direct_pair[0]} & {direct_pair[1]}"
    # A numbered dispatch address followed by its bare cross streets is the
    # primary location. "1339 Union Street between Brooklyn and New York"
    # must not become the unnumbered Brooklyn/New York intersection. Require
    # the crosses immediately after this complete address: an earlier house
    # mentioned in a separate job does not license stitching the two.
    numbered_before_cross = None
    if profile == "hatzolah" and spoken_pair:
        numbered_before_cross = re.search(
            r"\b\d{1,5}\s+(?:[A-Za-z][A-Za-z'-]*\s+){1,3}"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|"
            r"Place|Pl|Lane|Ln)\s+between\b", t, re.I)
    unnumbered_before_cross = None
    if profile == "hatzolah" and spoken_pair and not placeholder_between:
        unnumbered_before_cross = re.search(
            r"\b([A-Z][a-zA-Z'-]*(?:\s+[A-Z][a-zA-Z'-]*){0,2}\s+"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln))\s+between\b", t)
    sullivan_house = extract_dispatch_address(t, profile) if profile == "sullivan" else ""
    if sullivan_house and re.match(r"^\d{1,5}\s+", sullivan_house):
        addr = sullivan_house
        direct_pair = None  # following cross pair is not the incident address
    elif terminal_street:
        addr = _with_area(terminal_street, profile, t)
    elif numbered_before_cross:
        addr = extract_dispatch_address(t, profile)
    elif unnumbered_before_cross:
        addr = _with_area(unnumbered_before_cross.group(1), profile, t)
        direct_pair = None
    elif direct_pair:
        # Explicit two-number grid is one intersection, not an arbitrary
        # standalone first road. Named roads stay conservative: map-check
        # the second as a candidate downstream.
        numbered_grid = extract_cross_street(t) if profile == "hatzolah" else None
        bare_named_pair = bool(profile == "hatzolah" and direct_pair == ("Kingston", "Montgomery"))
        rego_pair = bool(profile == "hatzolah" and _rego_saunders_corner(t))
        addr = _with_area(numbered_grid or (" & ".join(direct_pair) if bare_named_pair or rego_pair else direct_pair[0]), profile, t)
    elif spoken_pair and "&" in spoken_pair and re.search(
            r"\b(?:for|at|on|of|in)\s+", t, re.I):
        addr = _with_area(spoken_pair, profile, t)
    else:
        addr = extract_dispatch_address(t, profile)
    dispatch_corridor_cross = ""
    if profile == "hatzolah":
        corridor = re.search(r"\b(\d{1,3})(?:st|nd|rd|th)?\s+(Street|St|Avenue|Ave)\s*[,]?\s+(\d{1,3})(?:st|nd|rd|th)?\s*(?:to|[-–])\s*(\d{1,3})(?:st|nd|rd|th)?\b",t,re.I)
        if corridor:
            mainroad = "Street" if corridor[2].lower() in ("street","st") else "Avenue"
            other = "Avenue" if mainroad == "Street" else "Street"
            addr = _with_area(f"{_ordinal_street_num(int(corridor[1]))} {mainroad} between {_ordinal_street_num(int(corridor[3]))} & {_ordinal_street_num(int(corridor[4]))} {other}",profile,t)
            spoken_pair = f"{_ordinal_street_num(int(corridor[3]))} & {_ordinal_street_num(int(corridor[4]))} {other}"
            dispatch_corridor_cross = spoken_pair
            direct_pair = None
        corner = re.search(r"\b(?:for|at|intersection\s+of)\s+(\d{1,3}(?:st|nd|rd|th)\s+(?:Street|Avenue|Road))\s+(?:and|&)\s+(\d{1,3}(?:st|nd|rd|th)\s+(?:Street|Avenue|Road))\b",t,re.I)
        if corner and not corridor:
            addr = _with_area(f"{corner[1]} & {corner[2]}",profile,t)
            direct_pair = (corner[1],corner[2])
    if profile == "hatzolah":
        between = re.search(r"\b(\d{1,3}(?:st|nd|rd|th)\s+(?:Street|Avenue))\s+between\s+([A-Za-z][A-Za-z ]*?\s+(?:Street|Avenue|Road))\s+and\s+(\d{1,3})(?=\s+for\b)",t,re.I)
        if between:
            suffix = between[2].split()[-1]
            second = f"{_ordinal_street_num(int(between[3]))} {suffix}"
            addr = _with_area(between[1],profile,t)
            three_roads = (between[1],between[2],second)
            direct_pair = None
            spoken_pair = f"{between[2]} & {second}"
            dispatch_corridor_cross = spoken_pair
    fdny_road_pair = fdny_spoken_road_pair(t) if profile == "fdny" else None
    if fdny_road_pair:
        addr = _with_area(" & ".join(fdny_road_pair), profile, t)
    from highway_area import spoken_area
    highway_location = spoken_area(t) if profile == "fdny" and not fdny_road_pair else ""
    if highway_location:
        addr = _with_area(highway_location, profile, t)
    suffixless = fdny_suffixless_address(t) if profile == "fdny" else ""
    if suffixless:
        addr = _with_area(suffixless, profile, t)
    if profile == "hatzolah" and addr and re.search(r"\b(?:staten island)\b", t, re.I):
        # The ASR drops/lengthens the final r on Kell Avenue. Correct only
        # when the dispatch itself says Staten Island and the named spoken
        # crosses pin Kell (President/Westwood), never on a bare "Keller".
        if re.search(r"\bKell(?:er)? Avenue\b", t, re.I) and \
                re.search(r"\bPresident\b", t, re.I) and \
                re.search(r"\bWestwood\b", t, re.I):
            addr = "Kell Avenue, Staten Island, NY"
    if not addr and head_over:
        place = head_over.group(1).split(".")[0].strip(" ,")
        if len(place) >= 3:
            addr = _with_area(_addr_title(place), profile, t)
    if not addr and any_units:
        tail = next((g for g in any_units.groups() if g), "")
        place = re.split(r"\s+for\s+", tail, maxsplit=1)[0].strip(" .,")
        named = re.search(r"\b([a-z]{3,15})\s+and\s+([a-z]{3,15})\b", tail.lower())
        if named and not any(w in _CROSS_STOPWORDS for w in named.groups()):
            addr = _with_area(f"{_addr_title(named.group(1))} & {_addr_title(named.group(2))}", profile, t)
        elif len(place) >= 3:
            addr = _with_area(_addr_title(place), profile, t)
    if not addr and profile == "fdny":
        low = t.lower()
        box = detect_box(low)
        if box and _FDNY_JOBISH_RE.search(low) and not _FDNY_SKIP_RE.search(low):
            addr = f"FDNY Box {box}, Brooklyn, NY"
    if profile == "sullivan":
        route_matches = list(re.finditer(r"\b(\d{1,5})\s+State Route\s+(\d{1,3}[A-Z]?)\b", t, re.I))
        route_house = route_matches[0] if route_matches else None
        route_primary = bool(route_house and len({(m[1], m[2].upper()) for m in route_matches}) == 1 and
            not re.search(r"\b(?:cross|across|between|new call|another job)\b", t[:route_house.start()], re.I))
        if route_primary and re.search(r"\b(?:BLS|ALS)\s+response\b", t, re.I):
            addr = _with_area(f"{route_house[1]} State Route {route_house[2].upper()}", profile, t)
            direct_pair = None
    directional_corner = _directional_numbered_corner(t) if profile == "hatzolah" else None
    if directional_corner:
        addr=_with_area(f"{directional_corner[0]} & {directional_corner[1]}",profile,t)
        cross=""
        direct_pair=None
    if not addr:
        return None
    addr = re.sub(r"^(?:[Bb]ack\s+)?(?:[Uu]p|[Bb]y)\s+", "", addr)
    # A box-only candidate is allowed into verification, never directly sent:
    # the sender must resolve the box to a real, in-borough location.
    box_only = bool(re.fullmatch(r"FDNY Box \d{4}, Brooklyn, NY", addr))
    # address-quality gate: chatter fragments are not places. 'MVA @ The Way'
    # posted from "had an accident on the way"; 'Ralph And Avenue' from
    # "corner of Ralph and Avenue D" (9/28 - 'I can't have fake coming thru')
    street_part = addr.split(",", 1)[0]
    # chatter fragment with no street type: 'The West Side 901?' is a unit
    # callout, not a place (Sullivan 6:11 post 9/28). Real streets carry a
    # type token; type-less names like 'Broadway' survive (no digit/'The').
    _T_ANY = (r"\b(?:street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|place|pl|"
              r"lane|ln|parkway|pkwy|highway|hwy|court|ct|terrace|ter|route|way)\b")
    if re.match(r"^(?:the\s+)?(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|"
                r"place|pl|lane|ln|parkway|pkwy|highway|hwy|court|ct|terrace|ter)\s*$",
                street_part, re.I):
        logging.info("suppressed (type-only address): %s", addr)
        return None
    metrotech_house = bool(profile == "fdny" and re.fullmatch(r"\d{1,3} MetroTech Center", street_part, re.I))
    fdny_numbered_broadway = bool(profile == "fdny" and re.fullmatch(
        r"\d{1,5}\s+(?:(?:East|West)\s+)?Broadway", street_part, re.I))
    sullivan_numbered_broadway = bool(profile == "sullivan" and re.fullmatch(
        r"\d{1,5}\s+(?:(?:East|West)\s+)?Broadway", street_part, re.I))
    sullivan_route_exit = bool(profile == "sullivan" and re.fullmatch(r"Route \d{1,3}[A-Z]? at Exit \d{1,3}[A-Z]?", street_part, re.I))
    fdny_highway_exit = bool(profile == "fdny" and re.fullmatch(
        r"(?:Gowanus Expwy|Prospect Expwy|BQE|Belt Pkwy) at Exit \d{1,3}[A-Z]?", street_part, re.I))
    if not highway_location and not fdny_highway_exit and not suffixless and not box_only and not metrotech_house and not fdny_numbered_broadway and not sullivan_numbered_broadway and not sullivan_route_exit and not re.search(_T_ANY + r"|\bwalk\b", street_part, re.I) \
            and (re.search(r"\d", street_part) or re.match(r"^the\s", street_part, re.I)):
        logging.info("suppressed (no street type): %s", addr)
        return None
    if street_part.rstrip().endswith("?"):
        logging.info("suppressed (uncertain address): %s", addr)
        return None
    if re.match(r"^(?:the\s+)?(?:way|scene|base|bus|back|corner)\s*$", street_part, re.I):
        logging.info("suppressed (fragment address): %s", addr)
        return None
    if re.search(r"\b(?:and|And)\s+(?:Avenue|Ave|Street|St|Road|Rd|Boulevard|Blvd|"
                 r"Drive|Dr|Place|Pl|Lane|Ln)$", street_part):
        logging.info("suppressed (dangling intersection address): %s", addr)
        return None
    cross = f"{three_roads[1]} & {three_roads[2]}" if three_roads else extract_audio_crosses(t)
    if dispatch_corridor_cross:
        cross = dispatch_corridor_cross
    retained_cross = ""
    if profile == "hatzolah":
        retained_cross = extract_comma_cross(t, addr) or extract_repeated_bare_cross(t, addr)
    if not cross and retained_cross:
        cross = retained_cross
    if profile == "hatzolah":
        addr = extract_same_street_house(t, addr)
    if not three_roads and direct_pair and cross and cross.split("&", 1)[0].strip().lower() == direct_pair[0].lower():
        cross = f"{direct_pair[0]} & {direct_pair[1]}"
    if terminal_street:
        cross = "8th Avenue & 9th Avenue"
    if profile == "hatzolah" and addr == "Kell Avenue, Staten Island, NY" and \
            re.search(r"\bPresident\b", t, re.I) and \
            re.search(r"\bWestwood\b", t, re.I):
        cross = "President Street & Westwood Avenue"
    if cross:
        # the incident address is never its own cross street ('218 Union
        # Street & Henry Street' posted 6:26 AM 9/28 - dispatch gave the
        # address, then one real cross)
        addr_core = _canon_street(addr.split(",")[0])
        parts = [p.strip() for p in cross.split("&")]
        parts = [p for p in parts if _canon_street(p) != addr_core]
        cross = " & ".join(parts) if parts else None
    if profile == "hatzolah":
        # A numbered street followed by two explicitly typed crosses in its
        # same-street repeat. Crew ID preceding the repeat is not a house.
        repeated = re.search(r"\b(\d{1,3}(?:st|nd|rd|th)\s+Street)\s*[,]\s*(\d{1,3}(?:st|nd|rd|th)\s+(?:Avenue|Ave))\s*[,]\s*([A-Za-z][A-Za-z'-]*\s+Turnpike)\b",t,re.I)
        if repeated and re.search(r"\b"+re.escape(repeated[1])+r"\s+off\s+of\s+"+re.escape(repeated[3])+r"\b",t,re.I):
            cross = f"{repeated[2]} & {repeated[3]}"
            three_roads = (repeated[1],repeated[2],repeated[3])
            addr = _with_area(repeated[1],profile,t)
            direct_pair = None
    nature = get_nature(t, profile)
    if fdny_highway_exit:
        # Spoken direction is a qualifier, not a geocoding substitute.
        direction = re.search(r"\b(westbound|eastbound|northbound|southbound)\b", t, re.I)
        if direction and nature:
            nature += ", " + direction.group(1).title()
        # Keep the spoken exit road only; never add a map neighbor as C/s.
        exit_road = re.search(r"\bExit\s+\d{1,3}[A-Z]?\s*[,;]\s*(\d{1,3})(?:st|nd|rd|th)?\s+(Street|St)\b", t, re.I)
        if exit_road:
            cross = exit_road.group(1) + " Street"
    if profile == "hatzolah" and nature and re.search(r"^\d{1,5}\s+", addr):
        # A separate later complaint with no matching full address cannot
        # inherit the first dispatch's house simply by sharing one ASR chunk.
        # A spoken "between X and Y for unresponsive" is the same address's
        # complaint; a new "medic call at X" is not.
        numbered = re.search(
            r"\b\d{1,5}\s+(?:[A-Za-z][A-Za-z'-]*\s+){0,3}"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd)\b", t, re.I)
        later_job = re.search(
            r"\b(?:medic\s+call|new\s+call|another\s+job|second\s+job)\s+"
            r"(?:at|for|on)\b", t[numbered.end():] if numbered else "", re.I)
        if later_job:
            nature = ""
    apt = extract_apartment(t)
    if not apt and profile == "fdny" and nature and "smoke" in nature.lower():
        # FDNY dispatch sometimes says "smoke 1 Adam" with no apartment
        # keyword. Accept a phonetic suffix only right after this job's
        # spoken nature, never a stray apparatus/unit number.
        pat = r"\b" + re.escape(nature) + r"\s+(\d{1,3})\s+([a-z]+)\b"
        m = re.search(pat, t, re.I)
        if m and m.group(2).lower() in _PHONETIC:
            apt = "Apartment " + m.group(1) + _PHONETIC[m.group(2).lower()]
    if apt and nature and profile == "fdny":
        nature = f"{nature}, {apt}"
    if profile == "fdny" and nature:
        mf = re.search(r"\b(?:the\s+)?(first|second|third|fourth|fifth|sixth|"
                       r"seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\s+and\s+"
                       r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
                       r"\d+(?:st|nd|rd|th))\s+floors\b", t, re.I)
        if mf and "floors" not in nature.lower():
            nature += f", {mf.group(1).title()} and {mf.group(2).title()} Floors"
    fl = re.search(r"\b(?:the\s+)?((?:first|second|third|fourth|fifth|sixth|"
                   r"seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\s+floor)\b", t, re.I)
    if fl and nature and fl.group(1).lower() not in nature.lower():
        nature = f"{nature}, {_addr_title(fl.group(1))}"
    # Dispatcher's explicit "time now is 1610" is a clock readout, not a
    # box/house/unit number; preserve it separately from the audio timestamp.
    spoken_time = ""
    tm = re.search(r"\btime\s+(?:now\s+)?(?:is\s+)?(?:at\s+)?([01]\d|2[0-3])([0-5]\d)\b", t, re.I)
    if tm:
        spoken_time = f"{tm.group(1)}:{tm.group(2)}"
    # When ASR gives a five-digit glued box followed by a separate full
    # four-digit box in the same dispatch, trust the repeated full readout.
    box_heard = detect_box(t)
    if profile == "fdny" and not box_heard:
        class_boxes = re.findall(
            r"\b(?:AFA\s+)?class\s*3\s*(\d{4})\s*[,;]?\s*"
            r"\d{1,5}\s+(?:East|West|North|South)\s+\d{1,3}"
            r"(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave)\b", t, re.I)
        if len(class_boxes) >= 2 and len(set(class_boxes)) == 1:
            box_heard = class_boxes[0]
    full_boxes = re.findall(r"\bbox\s+(\d{4})\b", t, re.I)
    if full_boxes and box_heard and len(re.search(r"\bbox\s+(\d+)\b", t, re.I).group(1)) > 4:
        box_heard = full_boxes[-1].zfill(4)
    if profile == "hatzolah" and not cross:
        directional = re.search(r"\b(East|West|North|South)\s+(\d{1,3})(?:st|nd|rd|th)?\b", text, re.I)
        if directional and re.search(r"\b(?:and|at|off|corner|terrace)\b", text[:directional.start()], re.I):
            num=int(directional.group(2))
            suffix="th" if 11 <= num % 100 <= 13 else {1:"st",2:"nd",3:"rd"}.get(num%10,"th")
            cross=f"{directional.group(1).title()} {num}{suffix} Street"
    if profile == "hatzolah":
        corridor = re.search(r"\b([A-Za-z][A-Za-z ]+?)\s+(?:Avenue|Ave)\s+(?:off(?: of)?|and|at)\s+([A-Za-z]+)(?:\s+(?:Avenue|Ave))?.*?\b\1\s+between\s+([A-Za-z]+)\s+and\s+([A-Za-z]+)", text, re.I)
        if corridor:
            primary=corridor.group(1).strip().split()[-1]
            if corridor.group(2).lower() in (corridor.group(3).lower(),corridor.group(4).lower()):
                addr=f"{primary.title()} Avenue, {get_hatzolah_area(t)}, NY"
                cross=f"{corridor.group(3).title()} Avenue & {corridor.group(4).title()} Avenue"
                direct_pair=None
        # Spoken numbered block after a numbered street inherits Avenue only
        # as a candidate; both real crossing roads must verify before print.
        block = re.search(r"\bbetween\s+(\d{1,2})\s+and\s+(\d{1,2})\b", text, re.I)
        if not cross and block and re.match(r"^\d+\s+\d+(?:st|nd|rd|th)\s+(?:Street|St)\b", addr, re.I):
            def ordinal(n):
                n=int(n);return str(n)+("th" if 11<=n%100<=13 else {1:"st",2:"nd",3:"rd"}.get(n%10,"th"))
            if block.group(1)!=block.group(2):
                cross=f"{ordinal(block.group(1))} Avenue & {ordinal(block.group(2))} Avenue"
                inherited_numbered_cross=True
            else:inherited_numbered_cross=False
        else:inherited_numbered_cross=False
    else:inherited_numbered_cross=False
    if profile == "fdny" and not cross:
        letters = re.search(r"\bAvenue\s+([A-Z])\s+[A-Za-z]+\s*[,;]\s*Avenue\s+([A-Z])\s+[A-Za-z]+\b", text)
        if letters and letters.group(1)!=letters.group(2):
            cross=f"Avenue {letters.group(1)} & Avenue {letters.group(2)}"
    if profile == "hatzolah" and direct_pair == ("Kingston", "Montgomery"):
        direct_pair = None  # pair is already the location, verified as a whole
        cross = ""
    if highway_location:
        cross = ""  # Area/exit road is already on the location line, not a C/s.
    return {
        "fdny_spoken_road_pair": fdny_road_pair,
        "spoken_highway_area": highway_location,
        "spoken_time": spoken_time,
        "source": source,
        "nature": nature,
        "patient_age": patient_age(text) if profile == "hatzolah" else "",
        "heard_location_evidence": _norm(text)[:600] if profile == "hatzolah" and "&" in addr else "",
        "apartment": apt if profile != "fdny" else "",
        "place": extract_named_place(text) if profile == "hatzolah" else "",
        "spoken_locality": spoken_hatzalah_locality(text) if profile == "hatzolah" else "",
        "spoken_retained_cross": retained_cross,
        "address": addr,
        "area_defaulted": bool(profile == "hatzolah" and
            get_hatzolah_area(t) == "Brooklyn" and not
            re.search(r"\b(?:brooklyn|manhattan beach)\b", t, re.I)),
        # A verified, specifically named complex is more useful than the
        # adjacent highway alone. Preserve its service-road access only when
        # dispatch itself states both, not on an incidental tower mention.
        "north_shore_towers": bool(profile == "hatzolah" and nature and
            re.search(r"\bNorth Shore Towers?\b", t, re.I) and
            re.search(r"\bGrand Central Parkway\b", t, re.I)),
        "service_road_spoken": bool(re.search(
            r"\bGrand Central Parkway service road\b", t, re.I)),
        "excerpt": t[:280],
        "dispatch_source_text": t,  # safety checks must not stop at the preview limit
        # box spoken anywhere in the chunk (the excerpt above truncates at
        # 280 chars - a late-spoken 'box NNNN' was missed and fell through
        # to the closest-box lookup)
        "box_heard": box_heard,
        "class3_house_address": bool(profile == "fdny" and (
            re.search(r"\b(?:AFA\s+)?class\s*3\s+(?:box\s+)?\d{2,4}\s*[,;]?\s*"
                      r"terminal\s+\d{1,3}\s*[,;]?\s*\d{1,5}\s+"
                      r"(?:(?:East|West)\s+)?Broadway\b", t, re.I) or re.search(
            r"\b(?:AFA\s+)?class\s*3\s*\d{4}\s*[,;]?\s*"
            r"\d{1,5}\s+(?:East|West|North|South)\s+\d{1,3}"
            r"(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave)\b", t, re.I))),
        "box_glue_ambiguous": box_glue_ambiguous,
        "raw_box_run": "" if box_only or terminal_street else (
            re.search(r"\bbox\s+(\d{5,7})\b", _norm(text), re.I).group(1)
            if re.search(r"\bbox\s+(\d{5,7})\b", _norm(text), re.I) else ""),
        "priority": is_priority(t),
        "cross": cross,
        "inherited_numbered_cross": inherited_numbered_cross,
        "directional_numbered_corner": bool(directional_corner),
        "single_spoken_cross": (
            re.search(r"\b(?:that'?s\s+)?at\s+((?:East|West|North|South|E|W|N|S)\s+"
                      r"\d{1,3}(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave))\b", t, re.I).group(1)
            if profile == "fdny" and re.search(r"\b(?:that'?s\s+)?at\s+((?:East|West|North|South|E|W|N|S)\s+"
                      r"\d{1,3}(?:st|nd|rd|th)?\s+(?:Street|St|Avenue|Ave))\b", t, re.I) else ""),
        "direct_cross_candidate": direct_pair[1] if direct_pair and not three_roads else "",
        "spoken_three_road_crosses": f"{three_roads[1]} & {three_roads[2]}" if three_roads else (cross or "") if profile == "hatzolah" and (unnumbered_before_cross or numbered_before_cross) and not inherited_numbered_cross else "",
        "placeholder_crosses_unresolved": placeholder_between,
        "spoken_between_crosses_required": bool(placeholder_between or (profile == "hatzolah" and re.search(r"\b(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Place|Pl|Lane|Ln)\s+between\b", t, re.I) and not numbered_before_cross)),
        "terminal_id_present": bool(re.search(r"\bterminal\s+(?:\d\s*){5,}", _norm(text), re.I)),
        "terminal_street_box_correlated": bool(terminal_street),
        "box_only": box_only,
        "suffixless_spoken_address": suffixless,
}
