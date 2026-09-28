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
    r"\b(?:ped\s+struck|pedestrian|not breathing|unconscious|choking|seizure|stroke|cva|convul|heart\s+attack)\b",
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


def get_hatzolah_area(text: str) -> str:
    """TSL-ChevraHatzalah mixes NYC divisions AND Sullivan County - trust the
    place names in the dispatch itself to set the area (user rule 9/28)."""
    t = text.lower()
    for k, v in SULLIVAN_AREAS.items():
        if k in t:
            # "Liberty Avenue" is Brooklyn, not Sullivan's Liberty / Old Liberty Road
            if k == "liberty" and re.search(r"liberty\s+(?:ave|avenue)", t):
                continue
            return v
    for k, v in FIVE_TOWNS_AREAS.items():
        if k in t:
            return v
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
    num = rf"(?:\d{{1,2}}(?:st|nd|rd|th)?|{_ORD_WORD_RE})"
    m = re.search(
        rf"(?P<n1>{num})\s+(?P<t1>{stypes})\s+(?:and|at|@|&)\s+(?P<n2>{num})\s+(?P<t2>{stypes})",
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
    # bare two-number Brooklyn grid: "units for 14 and 46"
    m = re.search(r"(?<![\d-])(\d{1,2})\s+and\s+(\d{1,2})(?!\d)", t)
    if m:
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
        if any(w.lower() in _STOP1 for w in ws):
            return False
        return all(w[0].isupper() or w[0].isdigit() for w in ws)

    def _pair(a: str, b: str) -> str | None:
        a, b = a.strip(), b.strip()
        if _ok(a) and _ok(b) and a.lower() != b.lower():
            return f"{a} & {b}"
        return None

    m = re.search(rf"\bbetween\s+({_ANCH})\s+and\s+({_ANCH})\b", t, re.I)
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
    m = re.search(rf"\bbetween\s+({_BARE})\s+and\s+({_BARE})\b", t, re.I)
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
    """Whisper glues the house number onto the box readout ('box 957 70
    Herkimer' -> 'box 95770 herkimer'): re-split over-long digit runs so the
    box keeps 2-4 digits and the remainder is a plausible house number
    (starts 1-9). 5+ contiguous digits after 'box' is always glue - FDNY
    boxes are at most 4 digits (bad post 9/28 8:03 AM: box 957 + 70 Herkimer
    posted as box 9577)."""
    def _rep(m):
        run = m.group(1)
        for blen in (4, 3, 2):
            house = run[blen:]
            if 1 <= len(house) <= 4 and house[0] != "0":
                return f"box {run[:blen]}, {house}"
        return m.group(0)
    return re.sub(r"\bbox\s+(\d{5,7})\b", _rep, t, flags=re.I)


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
    area = f"{get_hatzolah_area(text)}, NY" if profile in ("hatzolah", "fdny") else f"{get_sullivan_area(text)}, NY"
    town = area.split(",")[0].strip().lower()
    if town and town in addr.lower():
        return addr if ", NY" in addr else f"{addr}, NY"
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
    if profile == "fdny":
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
            r"lane|ln|parkway|pkwy)\b", _norm(text).lower())
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
                return _with_area(f"{hn.group(1)} {_addr_title(street)}",
                                  profile, text)
        num0 = _FIRE_NUM_DISPATCH_RE.search(text)
        if num0:
            return _with_area(f"{num0.group(1)} {_addr_title(num0.group(2).strip())}", profile, text)
        named = extract_named_cross(text)
        if named:
            return _with_area(named, profile, text)
    else:
        # house number on a named street for the EMS/Sullivan grammar ('67 Old
        # Ryan Road' posted bare 9/28; '2 Marcel 4 Road' lost the 2 - one
        # trailing all-digit word is allowed inside the name: Marcel 4 Road =
        # the map's Marcel Four Road)
        hn = re.search(
            r"\b(\d{1,5})\s+(?:([a-z][a-z'\-]*(?:\s+[a-z][a-z'\-]*){0,2}"
            r"(?:\s+\d{1,2})?)\s+)?(?:(\d{1,3}(?:st|nd|rd|th))\s+)?"
            r"(street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|place|pl|"
            r"lane|ln|parkway|pkwy)\b", _norm(text).lower())
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
                return _with_area(f"{hn.group(1)} {_addr_title(street)}",
                                  profile, text)
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
    # 'firefighter(s)' on scene is not a fire nature (53rd St Hatzolah EMS job
    # posted as 'Fire' 9/28 off a whisper 'Firefight 253' fragment)
    t = re.sub(r"firefight(?:er|ers|ing)?", " ", t)

    def vt(pattern: str) -> str:
        # user ruling 9/28 ('put something that was said'): a nature word
        # immediately followed by a bare number is unit chatter, not a spoken
        # nature - 'Rubbish 265' was a mangled unit readout and posted RUBBISH
        # on a fainting call. Skip digit-followed occurrences.
        for m in re.finditer(pattern, t):
            if re.match(r"\s+\d{2,5}\b", t[m.end():]):
                continue
            return _addr_title(m.group(0))
        return ""

    v = vt(r"\b(?:all hands|10-75|10 75|working fire|second alarm)\b")
    if v: return v
    v = vt(r"\b(?:ped|pedestrian)\s+(?:struck|stricken|hit)\b")
    if v: return v
    v = vt(r"\b(?:mva|mvc|motor vehicle accident|rollover|entrapment|car accident|auto accident|vehicle accident)\b")
    if v: return v
    v = vt(r"difficulty breathing|trouble breathing|shortness of breath|can't breathe|cant breathe|cannot breathe|not breathing|respiratory distress|turning blue")
    if v: return v
    v = vt(r"\b(?:cardiac arrest|heart attack|full arrest|cpr in progress)\b")
    if v: return v
    v = vt(r"\b(?:unresponsive|not responsive)\b")
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
    v = vt(r"\bchest pain\b")
    if v: return v
    v = vt(r"\bdrown\w*\b")
    if v: return v
    v = vt(r"\b(?:syncope|faint(?:ed|ing)?|passed out)\b")
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
    v = vt(r"\b(?:structure|building|house)\s+fire\b")
    if v: return v
    v = vt(r"\bkitchen fire\b")
    if v: return v
    v = vt(r"\b(?:car|vehicle|auto)\s+fire\b")
    if v: return v
    v = vt(r"\btrauma\b")
    if v: return v
    v = vt(r"\bunconscious\b")
    if v: return v
    v = vt(r"(?<![\d-])\bcode\b(?!\s*\d)")
    if v: return v
    v = vt(r"\b(?:water condition|water leak|burst pipe)\b")
    if v: return v
    v = vt(r"\bsprinkler\w*\b")
    if v: return v
    v = vt(r"\bmanhole\b")
    if v: return v
    v = vt(r"\b(?:electrical|wires down|transformer)\b")
    if v: return v
    v = vt(r"\belevator\b")
    if v: return v
    v = vt(r"\b(?:co alarm|carbon monoxide)\b")
    if v: return v
    v = vt(r"\b(?:rubbish fire|garbage fire|trash fire|rubbish)\b")
    if v: return v
    v = vt(r"\b(?:outside fire|brush fire)\b")
    if v: return v
    v = vt(r"\baided\b")
    if v: return v
    v = vt(r"\bodou?r of gas\b")
    if v: return v
    v = vt(r"\bgas leak\b")
    if v: return v
    # 'gas main (struck|ruptured|...)' is a content nature - box 3321 (9/28)
    # posted PHONE ALARM when 'a gas main that was ruptured by a contractor'
    # was said; box 2720 ('gas main struck') suppressed no-nature same hour
    m_gas = re.search(r"\bgas main\b", t)
    if m_gas:
        mp = re.search(r"\b(ruptured|struck|hit|broken|leaking|leak)\b",
                       t[m_gas.end(): m_gas.end() + 40])
        return _addr_title("gas main " + mp.group(1)) if mp else "Gas Main"
    # 'bus' on the Hatzolah channel = ambulance ('any units for a bus?')
    if ("hatzal" in profile.lower() or "hatzol" in profile.lower()) \
            and re.search(r"\bbus\b", t):
        return "EMS"
    # bare-word fire fallback is FDNY-only: on the EMS channel a lone whisper
    # 'fire' is a hallucination until proven ('I can't have fake coming thru'
    # 9/28) - Hatzalah fire jobs still match the structured patterns above
    if "hatzal" not in profile.lower() and "hatzol" not in profile.lower():
        m = re.search(r"\b(?:fire|smoke|burning)\b(?!\s*—)", t)
        if m and not _negative_fire_context(t):
            return _addr_title(m.group(0))
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
    v = vt(r"\bphone alarm\b")
    if v: return v
    v = vt(r"\b(?:ems|ambulance|sick person|medical emergency)\b")
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
             "frank": "F", "george": "G", "henry": "H", "henry": "H", "ida": "I",
             "john": "J", "king": "K", "lincoln": "L", "mary": "M", "mike": "M",
             "nora": "N", "ocean": "O", "peter": "P", "queen": "Q",
             "robert": "R", "romeo": "R", "sam": "S", "tom": "T", "union": "U",
             "victor": "V", "william": "W", "x-ray": "X", "xray": "X",
             "young": "Y", "zebra": "Z"}


def extract_apartment(text: str) -> str:
    """Spoken apartment detail -> 'Apartment 1R' (user 9/28: 'Smoke apartment
    1L, 1R, whatever's being said'). FDNY reads the letter phonetically
    ('apartment 1 Robert' = 1R). 'unit N' is apparatus, not an apartment -
    only 'apartment/apt' count."""
    t = _norm(text).lower()
    m = re.search(r"\b(?:apartment|apt)s?\s+(\d{1,3})\s+([a-z][a-z\-]+)\b", t)
    if m and m.group(2) in _PHONETIC:
        return "Apartment " + m.group(1) + _PHONETIC[m.group(2)]
    m = re.search(r"\b(?:apartment|apt)s?\s+(\d{1,3})\s*([a-z])?\b", t)
    if m:
        return "Apartment " + m.group(1) + (m.group(2) or "").upper()
    m = re.search(r"\b(?:apartment|apt)s?\s+([a-z][a-z\-]+)\b", t)
    if m and m.group(1) in _PHONETIC:
        return "Apartment " + _PHONETIC[m.group(1)]
    return ""


def analyze(text: str, profile: str = "hatzolah") -> dict | None:
    """Return an alert dict, or None when this chunk should not alert."""
    source = profile
    profile = profile.removeprefix("zello-")  # zello-* reuses base grammar
    if profile == "hatzalah":  # source label spelling -> grammar spelling
        profile = "hatzolah"
    t = _merge_split_ordinals(_split_box_glue(_norm(text)))
    if len(t) < 10:
        return None
    any_units = _ANY_UNITS_RE.search(t)
    head_over = _HEAD_OVER_RE.search(t)
    if not is_emergency(t) and not any_units and not head_over:
        return None
    if is_chatter(t):
        return None
    addr = extract_dispatch_address(t, profile)
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
    if not addr:
        return None
    addr = re.sub(r"^(?:[Bb]ack\s+)?(?:[Uu]p|[Bb]y)\s+", "", addr)
    # address-quality gate: chatter fragments are not places. 'MVA @ The Way'
    # posted from "had an accident on the way"; 'Ralph And Avenue' from
    # "corner of Ralph and Avenue D" (9/28 - 'I can't have fake coming thru')
    street_part = addr.split(",", 1)[0]
    # chatter fragment with no street type: 'The West Side 901?' is a unit
    # callout, not a place (Sullivan 6:11 post 9/28). Real streets carry a
    # type token; type-less names like 'Broadway' survive (no digit/'The').
    _T_ANY = (r"\b(?:street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|place|pl|"
              r"lane|ln|parkway|pkwy|highway|hwy|court|ct|terrace|ter)\b")
    if re.match(r"^(?:the\s+)?(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|"
                r"place|pl|lane|ln|parkway|pkwy|highway|hwy|court|ct|terrace|ter)\s*$",
                street_part, re.I):
        logging.info("suppressed (type-only address): %s", addr)
        return None
    if not re.search(_T_ANY, street_part, re.I) \
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
    cross = extract_audio_crosses(t)
    if cross:
        # the incident address is never its own cross street ('218 Union
        # Street & Henry Street' posted 6:26 AM 9/28 - dispatch gave the
        # address, then one real cross)
        addr_core = _canon_street(addr.split(",")[0])
        parts = [p.strip() for p in cross.split("&")]
        parts = [p for p in parts if _canon_street(p) != addr_core]
        cross = " & ".join(parts) if parts else None
    nature = get_nature(t, profile)
    apt = extract_apartment(t)
    if apt and nature:
        nature = f"{nature}, {apt}"
    return {
        "source": source,
        "nature": nature,
        "address": addr,
        "excerpt": t[:280],
        # box spoken anywhere in the chunk (the excerpt above truncates at
        # 280 chars - a late-spoken 'box NNNN' was missed and fell through
        # to the closest-box lookup)
        "box_heard": detect_box(t),
        "priority": is_priority(t),
        "cross": cross,
    }
