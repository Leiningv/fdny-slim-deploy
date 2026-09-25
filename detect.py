"""Detection for fdny-slim: emergency patterns, nature classification, address extraction.

Simplified port of the useful logic from fdny_monitor_full.py (read-only reference).
Two source profiles: "hatzolah" (Brooklyn) and "sullivan" (Sullivan County).
"""
from __future__ import annotations

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
    r"\b(?:allergic|anaphylaxis|epi\s*pen|overdose|unresponsive|syncope|fall|bleeding)\b",
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
SULLIVAN_AREAS = {
    "south fallsburg": "S Fallsburg",
    "woodridge": "Woodridge",
    "woodbourne": "Woodbourne",
    "monticello": "Monticello",
    "liberty": "Liberty",
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
def _norm(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t


def _ordinal_street_num(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{'st' if n % 10 == 1 else 'nd' if n % 10 == 2 else 'rd' if n % 10 == 3 else 'th'}"


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
        r"\b(\d{1,5})\s+(\d{1,3}(?:st|nd|rd|th)?)\s+"
        r"(avenue|ave|street|st|road|rd|drive|dr|boulevard|blvd|place|pl|lane|ln)\b",
        t,
    )
    if m:
        return f"{m.group(1)} {_format_cross_street_part(m.group(2), m.group(3))}"
    return None


def detect_box(text: str) -> str | None:
    t = text.lower()
    m = re.search(r"(?:box|alarm)\s+(\d{2,4})", t)
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
    area = "Brooklyn, NY" if profile == "hatzolah" else f"{get_sullivan_area(text)}, NY"
    town = area.split(",")[0].strip().lower()
    if town and town in addr.lower():
        return addr if ", NY" in addr else f"{addr}, NY"
    return f"{addr}, {area}"


def extract_dispatch_address(text: str, profile: str = "hatzolah") -> str | None:
    """Best-effort dispatch location for one transcript chunk."""
    hwy = extract_highway_intersection(text, profile)
    if hwy:
        return _with_area(hwy, profile, text)
    cross = extract_cross_street(text)
    if cross:
        return _with_area(cross, profile, text)
    house = extract_house_address(text)
    if house:
        return _with_area(house, profile, text)
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


def get_nature(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ["all hands", "10-75", "10 75", "working fire", "second alarm"]):
        return "All Hands Fire"
    if re.search(r"\b(?:ped|pedestrian)\s+(?:struck|stricken|hit)\b", t):
        return "Pedestrian Struck"
    if re.search(r"\b(?:mva|mvc|motor vehicle accident|rollover|entrapment|car accident|auto accident|vehicle accident)\b", t):
        return "MVA"
    if any(x in t for x in ["difficulty breathing", "trouble breathing", "shortness of breath",
                            "can't breathe", "cant breathe", "cannot breathe", "not breathing",
                            "respiratory distress", "turning blue"]):
        return "Difficulty Breathing"
    if re.search(r"\b(?:cardiac arrest|heart attack|full arrest|cpr in progress)\b", t):
        return "Cardiac Arrest"
    if re.search(r"\b(?:unresponsive|not responsive|unconscious)\b", t):
        return "Unresponsive"
    if re.search(r"\bchok(?:ing|e)\b", t):
        return "Choking"
    if re.search(r"\b(?:overdose|o\.d\.|narcotic)\b", t):
        return "Overdose"
    if re.search(r"\b(?:accident|collision|crash)\b", t):
        return "MVA"
    if re.search(r"\b(?:stroke|cva|seizure|convuls)\b", t):
        return "Medical Emergency"
    if re.search(r"\bfall\b|\bfell\b", t):
        return "Fall"
    if re.search(r"\b(?:bleeding|hemorrhage)\b", t):
        return "Bleeding"
    if re.search(r"\bchest pain\b", t):
        return "Chest Pain"
    if re.search(r"\b(?:fire|smoke|burning)\b", t) and not _negative_fire_context(t):
        return "Fire" if "fire" in t or "burning" in t else "Smoke Condition"
    if re.search(r"\bgas leak\b|\bodou?r of gas\b", t):
        return "Gas Leak"
    return "EMS"


# ---------------------------------------------------------------------------
# Chatter filter + top-level decision
# ---------------------------------------------------------------------------
_CHATTER_RE = re.compile(
    r"\b(?:check your whatsapp|sent you a whatsapp|whatsapp for updates|"
    r"on whatsapp|shift change|roster update|good morning|good night|"
    r"radio check|test test)\b", re.I)


def is_chatter(text: str) -> bool:
    if not _CHATTER_RE.search(text):
        return False
    if detect_box(text):
        return False
    if extract_dispatch_address(text, "hatzolah") or extract_dispatch_address(text, "sullivan"):
        return False
    return True


def analyze(text: str, profile: str = "hatzolah") -> dict | None:
    """Return an alert dict, or None when this chunk should not alert."""
    t = _norm(text)
    if len(t) < 10:
        return None
    if not is_emergency(t):
        return None
    if is_chatter(t):
        return None
    addr = extract_dispatch_address(t, profile)
    if not addr:
        return None
    return {
        "source": profile,
        "nature": get_nature(t),
        "address": addr,
        "excerpt": t[:280],
    }
