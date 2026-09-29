"""Conservative FDNY spoken-borough conflict detector.

Only job-local location statements are evidence. A unit affiliation or a road
named Queens is not an incident location. Unclear cases continue through the
normal address verification path rather than changing the borough by inference.
"""
import re

_OTHER_BOROUGH = r"(?:Queens|Manhattan|Bronx|Staten\s+Island)"
_LOCAL_JOB = re.compile(
    rf"\b(?:we(?:'re|\s+are)|(?:the\s+)?(?:job|incident|call|location|address)(?:\s+is)?)"
    rf"\s+(?:in|at)\s+(?:the\s+borough\s+of\s+|the\s+)?(?P<borough>{_OTHER_BOROUGH})\b"
    rf"(?!\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Place|Pl|Boulevard|Blvd))",
    re.I,
)
_ADDRESS_SUFFIX = re.compile(
    rf"\b\d{{1,5}}\s+[A-Za-z][A-Za-z' -]*?\s+"
    rf"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Place|Pl|Boulevard|Blvd)"
    rf"\s*,\s*(?P<borough>{_OTHER_BOROUGH})\b",
    re.I,
)


def spoken_job_borough(transcript: str) -> str:
    """Only a job-local location declaration changes the feed's default borough."""
    shorthand = re.search(
        r"\b(?:Brooklyn\s+Housing|Program\s+announcing)\s*,?\s*"
        r"(?P<borough>Queens|Manhattan|Bronx|Staten\s+Island)\s*,?\s*"
        r"(?:a\s+)?(?:second|third|fourth|fifth)\s+alarm\s+transmitted\b",
        transcript, re.I)
    if shorthand:
        return " ".join(shorthand.group("borough").title().split())
    m = re.search(
        r"\b(?:announcing\s+(?:the\s+)?borough|(?<![A-Za-z])borough|"
        r"(?:job|incident|call|location|address)\s+(?:is\s+)?in|"
        r"(?:we're|we are)\s+in)\s+(?:the\s+borough\s+of\s+)?"
        r"(?P<borough>Queens|Manhattan|Bronx|Staten\s+Island|Brooklyn)\b"
        r"(?!\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Place|Pl))",
        transcript, re.I)
    return " ".join(m.group("borough").title().split()) if m else ""


def spoken_borough_conflict(transcript: str, parsed_address: str) -> str:
    """Return conflicting spoken borough, or empty string if not proven."""
    if not re.search(r",\s*Brooklyn,\s*NY\s*$", parsed_address, re.I):
        return ""
    for pattern in (_LOCAL_JOB, _ADDRESS_SUFFIX):
        match = pattern.search(transcript)
        if match:
            return " ".join(match.group("borough").title().split())
    return ""


# PL geocoding may return a fuzzy same-token street or a different house.
# For numbered FDNY addresses, both must be exact after abbreviation expansion.
_STREET_TYPE = {"st": "street", "ave": "avenue", "rd": "road",
                "dr": "drive", "pl": "place", "blvd": "boulevard",
                "ct": "court", "ln": "lane", "pkwy": "parkway", "ter": "terrace"}

def _street_key(value: str) -> str:
    words = re.findall(r"[a-z]+|\d+(?:st|nd|rd|th)?", value.lower())
    normalized = []
    for word in words:
        word = re.sub(r"^(\d+)(?:st|nd|rd|th)$", r"\1", word)
        normalized.append(_STREET_TYPE.get(word, word))
    return " ".join(normalized)

def exact_numbered_fdny_match(address: str, geocode_label: str) -> bool:
    """False on an inexact numbered house/road map result; otherwise true."""
    m = re.match(r"^(\d{1,5}(?:-\d{1,3})?[A-Za-z]?)\s+(.+?),\s*(?:Brooklyn|Queens|Manhattan|Bronx|Staten Island),\s*NY$", address, re.I)
    if not m:
        return True  # This gate applies only to numbered Brooklyn addresses.
    # Neighborhood labels are allowed, but the map provider's borough feature
    # is independently checked in geocode_verify before this label is used.
    first = (geocode_label or "").split(",", 1)[0]
    found = re.match(r"^(\d{1,5}(?:-\d{1,3})?[A-Za-z]?)\s+(.+)$", first, re.I)
    return bool(found and found.group(1).lower() == m.group(1).lower()
                and _street_key(found.group(2)) == _street_key(m.group(2)))


def box_street_conflict(address: str, locality: str, box_rows: list[tuple[str, str]]) -> bool:
    """A numbered job and a resolved box have no same-borough incident road."""
    match = re.match(r"^\d+[A-Za-z]?\s+(.+?),", address)
    if not match or not locality or not box_rows:
        return False
    def road_key(road: str) -> str:
        road = road.strip()
        road = re.sub(r"^(?:E|W|N|S)\s+", lambda m: {"e": "East ", "w": "West ", "n": "North ", "s": "South "}[m.group().strip().lower()], road, flags=re.I)
        return _street_key(road)
    incident = road_key(match.group(1))
    for location, borough in box_rows:
        if borough.lower() != locality.lower():
            continue
        for side in re.split(r"\s+at\s+|\s*&\s*", location, flags=re.I):
            if road_key(side) == incident:
                return False
    return True


_NUMBERED_BUILDING = re.compile(
    r"\b(?P<house>\d{1,5}[A-Za-z]?)\s+"
    r"(?P<road>(?:(?:North|South|East|West|N|S|E|W)\s+)?"
    r"(?:[A-Za-z][A-Za-z'-]*\s+){1,3}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Place|Pl|"
    r"Boulevard|Blvd|Court|Ct|Walk))\b", re.I)


def unnumbered_with_spoken_building(transcript: str, parsed_address: str) -> str:
    """Return a spoken numbered building if the candidate dropped its number.

    Do not synthesize an address from this match: a positive result is a hold.
    Box digits and numbered street ordinals are not house numbers.
    """
    # Queens house numbers use a two-part hyphenated form (159-22). The
    # second half is not an unparsed building, and a numbered candidate has
    # already preserved the house. Still hold when the candidate is bare.
    if re.match(r"^\s*\d{1,5}(?:-\d{1,4})?[A-Za-z]?\s+", parsed_address):
        return ""
    for match in _NUMBERED_BUILDING.finditer(transcript):
        prefix = transcript[max(0, match.start() - 7):match.start()]
        if re.search(r"\bbox\s*$", prefix, re.I):
            continue
        # "East 12 to Coney Island Avenue" is a cross-road corridor,
        # not building 12 on a road named "to Coney Island Avenue".
        if re.match(r"(?:to|toward|towards|and)\s+", match.group("road"), re.I):
            continue
        return f"{match.group('house')} {match.group('road')}"
    return ""
