"""Conservative pre-post review of FDNY Calls' fallback classifications.

This module can veto a weak vendor classification. It never upgrades a job,
rewrites an address/box, or declares any crossing roads verified.
"""
from __future__ import annotations

import re

import detect
from fdny_correction_guard import address_parts

_FALLBACK = re.compile(r"^(?:phone alarm|automatic alarm|fire alarm|alarm activation|class 3)\b", re.I)
# Capture a specific complaint that a transmission-type fallback must not
# swallow. A bare "fire" or a radio mention of an alarm is not enough.
_SPECIFIC_FIRE = re.compile(
    r"\b(?:[a-z]{3,18}\s+fire|fire\s+(?:in|on|at)\s+(?:the\s+|an?\s+)?"
    r"(?:[a-z]{3,18}\s+){0,3}(?:building|dwelling|floor|apartment|balcony|"
    r"basement|cellar|hallway|rear))\b", re.I)
_NEGATED = re.compile(r"\b(?:no|not|without|negative)\s+(?:\w+\s+){0,2}$", re.I)


def unclassified_fire_complaint(transcript: str, nature: str) -> bool:
    """Did this text contain specific, non-negated fire evidence but parse a fallback?"""
    if not _FALLBACK.match(nature or ""):
        return False
    for m in _SPECIFIC_FIRE.finditer(transcript or ""):
        snippet = m.group().lower()
        if re.search(r"\b(?:phone|automatic|manual|smoke|still|fire)\s+alarm\b", snippet):
            continue
        if _NEGATED.search((transcript or "")[max(0, m.start()-25):m.start()]):
            continue
        return True
    return False


def compare_weak_fdny(primary: dict, second_text: str) -> str:
    """Empty means the second ASR corroborates, otherwise hold for review.

    The second reading must parse one complete same-address job. It cannot
    authorize a changed house, street, borough, box, nature or crosses.
    """
    if not second_text:
        return "FDNY independent audio unavailable"
    box_ids = {m.group(1).zfill(4) for m in re.finditer(
        r"\bbox\s*[,;:]?\s*(\d{2,5})\b", second_text, re.I)}
    if len(box_ids) > 1:
        return "FDNY independent audio contains multiple jobs"
    second = detect.analyze(second_text, "fdny")
    if not second:
        return "FDNY independent audio inconclusive"
    first_addr, second_addr = address_parts(primary.get("address")), address_parts(second.get("address"))
    if not first_addr or first_addr != second_addr:
        return "FDNY independent audio disagrees on address"
    b1, b2 = primary.get("box_heard") or "", second.get("box_heard") or ""
    if b1 and b2 and b1 != b2:
        return "FDNY independent audio disagrees on box"
    first_nature, second_nature = primary.get("nature") or "", second.get("nature") or ""
    if first_nature.casefold() != second_nature.casefold():
        return "FDNY independent audio disagrees on complaint"
    if unclassified_fire_complaint(second_text, second_nature):
        return "FDNY independent audio contains unclassified fire complaint"
    return ""


def generic_nature_invariant(transcript: str, nature: str) -> bool:
    """Safety invariant, independent of phrase extraction and review flags."""
    generic = re.fullmatch(r"(?:phone alarm|automatic alarm|fire alarm|alarm activation|class 3|fire|unknown|unknown problem)", (nature or "").strip(), re.I)
    if not generic: return False
    # Specific non-fire complaints must never degrade to a transmission
    # label, even if extraction loses them. Require job-local wording and
    # reject negated complaints; unrelated unit chatter supplies no nature.
    for m in re.finditer(r"\b(?:for|reporting)\s+(?:an?\s+)?"
                         r"(?:manhole(?:\s+(?:fire|smoke|explosion|cover))?|"
                         r"elevator|water\s+(?:condition|leak)|burst\s+pipe|"
                         r"wires\s+down|transformer|electrical(?:\s+condition)?|"
                         r"carbon\s+monoxide|co\s+alarm|gas\s+(?:leak|odor)|"
                         r"unstable\s+facade|unsafe\s+facade)\b", transcript or "", re.I):
        if not _NEGATED.search((transcript or "")[max(0,m.start()-25):m.start()]):
            return True
    # Existing escalation/dwelling evidence remains an independent gate.
    return bool(re.search(r"\b(?:all[ -]?hands|going\s+to\s+work|working[ -]?fire|10[- ]?75|dwelling|fire)\b", transcript or "", re.I))
