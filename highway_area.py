"""Owner-authorized spoken highway areas, no precise map/house claim.

Scope: FDNY named highways with a spoken exit, bounded exit pair, typed road
area, or direction. Ordinary street/house addresses do not enter this path.
"""
import re
_NAMES = r'(?:Gowanus (?:Expressway|Expwy)|Brooklyn[- ]Queens Expressway|BQE|Belt (?:Parkway|Pkwy)|Prospect (?:Expressway|Expwy))'
_NAME = re.compile(r'\b'+_NAMES+r'\b',re.I)
_ROAD = r'(?:\d{1,3}(?:st|nd|rd|th)?\s+|(?:[A-Za-z][A-Za-z\'-]*\s+){1,3})(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Parkway|Pkwy|Bridge)'
_ANCHOR = re.compile(r'\b(?:between\s+exits?\s*\d{1,3}[A-Z]?\s+(?:and|to|&)\s*(?:exit\s*)?\d{1,3}[A-Z]?|(?:in\s+the\s+area\s+of|near|at|by)\s+(?:exit\s*\d{1,3}[A-Z]?|'+_ROAD+r')|exit\s*\d{1,3}[A-Z]?)(?:\s*,\s*'+_ROAD+r')?',re.I)
_DIR = re.compile(r'\b(?:westbound|eastbound|northbound|southbound)\b',re.I)
def spoken_area(text: str) -> str:
 # A complete numbered street incident cannot be replaced by an incidental
 # highway mention in the same recording.
 if re.search(r"\b\d{1,5}\s+(?:[A-Za-z][A-Za-z'-]*\s+){1,3}(?:Avenue|Ave|Road|Rd|Place|Pl|Street|St)\b",text or '',re.I):return ''
 matches=list(_NAME.finditer(text or ''))
 if not matches:return ''
 names={re.sub(r'[- ]','',m.group().lower()).replace('expwy','expressway').replace('pkwy','parkway') for m in matches}
 if len(names)!=1:return ''  # mixed highways require an ordinary verified location
 m=matches[0]
 # Named highway is a location, not a house on a same-name surface road.
 if re.search(r'\d+\s*$',text[max(0,m.start()-8):m.start()]):return ''
 chunk=text[m.end():].split('.',1)[0][:180]
 a=_ANCHOR.search(chunk);d=_DIR.search(chunk)
 if re.search(r'\b(?:in the area of|between|near|at|by)\b',chunk,re.I) and not a:return ''
 if re.search(r'\bbetween\s+exit',chunk,re.I) and (not a or not a.group().lower().startswith('between')):return ''
 if not a and not d:return ''
 if re.search(r'\b(?:maybe|possibly|not on)\b',text[max(0,m.start()-24):m.start()]):return ''
 anchor=a.group().strip(' ,') if a else ''
 direction=d.group() if d else ''
 return ' '.join(x for x in [m.group().strip(),anchor,direction] if x)
