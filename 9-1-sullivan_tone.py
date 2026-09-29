"""Conservative same-job Sullivan agency/area toner; display only, never a location gate."""
from __future__ import annotations
import re

# These are spoken agency/neighborhood labels, not a list of Sullivan coverage.
_NAMES = {'empress': 'Empress EMS', 'bethel': 'Bethel',
          'woodridge': 'Woodridge', 'rock hill': 'Rock Hill'}


def toned_label(excerpt: str) -> str:
    text = (excerpt or '').lower()
    # Only the opening dispatch frame, not a later repeat/second job. A
    # second job opener means its own hit/span must be parsed separately.
    m = re.search(r'\b(?:(?:sullivan(?: county)?|\d{1,2})\s+)?dispatch\b',text)
    if m and m.start() > 45:
        return ''
    if not m:
        return ''
    start = text[m.end():]
    second = re.search(r'\b(?:(?:sullivan(?: county)?|\d{1,2})\s+)?dispatch\s*(?:to|for|,)\s+',start)
    frame = start[:second.start() if second else 90]
    for name, label in _NAMES.items():
        phrase = re.escape(name).replace(r'\ ',r'\s+')
        if re.search(r'^\s*(?:to|for|,|:)\s+(?:the\s+)?'+phrase+r'\b',frame):
            return label
        if re.search(r'^\s*(?:to|for|,|:)\s+(?:the\s+)?'+phrase+r'\s+ems\b',frame):
            return label
    # "Dispatch, Rock Hill, [company]" can identify the neighborhood
    # that was first called, but only in that opening frame.
    return ''
