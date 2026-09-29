"""Conservative FDNY address-correction suppression. No sends or network calls."""
import re
import time

_WINDOW = 180
_CORRECTION = re.compile(r"\b(?:correct(?:ed)? address|address (?:was |is )?changed to|"
                         r"address correction|correction[,;:]? (?:the )?address)\b", re.I)
_HOUSE = re.compile(r"^\s*(\d{1,5}[A-Za-z]?)\s+(.+?),\s*"
                    r"(Brooklyn|Queens|Manhattan|Bronx|Staten Island),\s*NY$", re.I)


def address_parts(addr):
    m = _HOUSE.fullmatch(addr or "")
    if not m:
        return None
    return m.group(1).lower(), re.sub(r"\s+", " ", m.group(2).lower().strip()), m.group(3).lower()


def call_time(call):
    try:
        return float(call.get("audio_start_ts") or call.get("ts") or 0)
    except (ValueError, TypeError):
        return 0


class CorrectionGuard:
    def __init__(self):
        self.corrections = []  # (source ts, corrected address parts, transcript, box)
        self.sent = {}  # key (borough, spoken box): (address, send time)
        self.recent = []  # (borough, house, street, box, send time)

    def ingest(self, calls):
        """Index explicit corrections before workers run; return sent-job conflicts."""
        conflicts = []
        now = time.time()
        self.corrections = [x for x in self.corrections if now-x[0] < 900]
        for call in calls:
            text = str(call.get('transcription') or '')
            if not _CORRECTION.search(text):
                continue
            # Parse ONLY the suffix following the explicit correction, not an
            # unrelated first dispatch in the same Calls clip.
            import detect
            tail = text[_CORRECTION.search(text).end():]
            hit = detect.analyze(tail, 'fdny')
            parts = address_parts((hit or {}).get('address'))
            ts = call_time(call)
            if parts and ts and abs(now-ts) < 900:
                boxes = {m.group(1).zfill(4) for m in re.finditer(r"\bbox\s*(\d{2,4})\b", text, re.I)}
                key = (ts, parts, text[:120], next(iter(boxes)) if len(boxes) == 1 else None)
                if key not in self.corrections:
                    self.corrections.append(key)
                    for borough, house, street, box, sent_at in self.recent:
                        if ((street, borough) == (parts[1], parts[2])
                                and house != parts[0] and now-sent_at < _WINDOW
                                and (key[3] is None or key[3] == box)):
                            old_addr = f"{house} {street}, {borough.title()}, NY"
                            conflicts.append((box or 'unspoken', old_addr, hit['address']))
        return conflicts

    def reason(self, hit, call):
        """Return reason to hold or empty string; never infer a replacement."""
        parts = address_parts(hit.get('address'))
        if not parts:
            return ''
        house, street, borough = parts
        box = hit.get('box_heard')
        ts = call_time(call)
        # Explicit later correction in the same source-time window and same
        # street: hold the superseded original even if it arrived in the same
        # batch and another worker processed it first.
        for cts, (new_house, new_street, new_borough), _, corrected_box in self.corrections:
            if (street, borough) == (new_street, new_borough) and house != new_house \
                    and ts and 0 <= cts-ts <= _WINDOW \
                    and (corrected_box is None or corrected_box == box):
                return 'superseded by explicit later address correction'
        if box:
            old = self.sent.get((borough, box))
            if old and old[0].lower() != hit['address'].lower() and time.time()-old[1] < 1800:
                return 'same spoken box already posted at a different address; review correction'
        return ''

    def mark_sent(self, hit):
        box = hit.get('box_heard')
        parts = address_parts(hit.get('address'))
        if parts:
            now = time.time()
            self.recent = [row for row in self.recent if now-row[4] < 1800]
            self.recent.append((parts[2], parts[0], parts[1], box, now))
        if box and parts:
            self.sent[(parts[2], box)] = (hit['address'], time.time())
