"""Conservative parser for the free-text ICARUS meta/time values.

Dates arrive in German, Dutch, Polish, English and Latin forms ("um 1440/45",
"2 poł. XIX wieku", "last quarter 15th century (1475 - 1499)"). The parser only
commits to what the text states: it returns an inclusive [start, end] year range,
leaving a bound open (None) for "before 1310"/"after 1626", and never narrows
a century to a year.

Centuries use the 1400-1499 convention for "15th century" (matches RKD's own
normalisation and buckets cleanly as "1400s").
"""
import re

MIN_YEAR, MAX_YEAR = 100, 2026

APPROX = re.compile(r"\b(c|ca|circa|um|gegen|ok|około|omstreeks|rond|vers|environ)\b\.?|\?", re.I)
BEFORE = re.compile(r"\b(vor|before|bis|ante|przed|voor|avant|uiterlijk|spätestens)\b", re.I)
AFTER = re.compile(r"\b(nach|after|post|po|na|na\s+ok|ná|après|frühestens)\b", re.I)

# Trailing normalised range, e.g. "c. 1595 (1590 - 1600)" or "dated 1634 (1634)" (RKD style).
TRAILING = re.compile(r"\((\d{3,4})(?:\s*[-–]\s*(\d{3,4}))?\)\s*$")

CENTURY_WORD = r"(?:jh\.?|jhdt\.?|jahrhunderts?|century|centuries|eeuws?|siècle|wieku?|w\.)"
ARABIC_CENTURY = re.compile(r"(\d{1,2})\s*(?:\.|st|nd|rd|th|e|de|ste|er|ème)?\s*-?\s*" + CENTURY_WORD, re.I)
ROMAN_CENTURY = re.compile(r"\b([IVXL]{1,6})(?:\s*[/-]\s*([IVXL]{1,6}))?\s*" + CENTURY_WORD, re.I)
POLISH_DECADES = re.compile(r"lata\s+(\d)0(?:\s*-\s*(\d)0)?\s*(?:-?te|-?tych)?\s+([IVXL]{1,6})\s*w", re.I)

YEAR = re.compile(r"(?<![\d.,])(\d{3,4})(?:\s*[/–-]\s*(\d{2})(?!\d))?(?![\d])")

PARTS = [  # (pattern, start offset, end offset) within a century
    (r"\b(1\.?\s*hälfte|erste[nr]?\s+hälfte|first half|1\.?\s*poł|eerste helft|1e helft|première moitié)", 0, 49),
    (r"\b(2\.?\s*hälfte|zweite[nr]?\s+hälfte|second half|2\.?\s*poł|tweede helft|2e helft|seconde moitié)", 50, 99),
    (r"\b(1\.?\s*viertel|erste[sn]?\s+viertel|first quarter|1\.?\s*ćw|eerste kwart)", 0, 24),
    (r"\b(2\.?\s*viertel|zweite[sn]?\s+viertel|second quarter|2\.?\s*ćw|tweede kwart)", 25, 49),
    (r"\b(3\.?\s*viertel|dritte[sn]?\s+viertel|third quarter|3\.?\s*ćw|derde kwart)", 50, 74),
    (r"\b(4\.?\s*viertel|letzte[sn]?\s+viertel|vierte[sn]?\s+viertel|last quarter|fourth quarter|4\.?\s*ćw|laatste kwart)", 75, 99),
    (r"\b(anfang|früh\w*|early|begin\w*|początek|vroeg)", 0, 33),
    (r"\b(mitte|mid|middle|midden|połowa)", 33, 66),
    (r"\b(ende|spät\w*|late|eind\w*|koniec|schluss)", 66, 99),
]
PARTS = [(re.compile(p, re.I), a, b) for p, a, b in PARTS]
TURN = re.compile(r"\b(przełom|wende|turn of|um die wende|rond)\b", re.I)

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def roman_to_int(s):
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = ROMAN[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def _result(start, end, kind, approx, text):
    if start is not None and not MIN_YEAR <= start <= MAX_YEAR:
        return unparsed(text, "out_of_range")
    if end is not None and not MIN_YEAR <= end <= MAX_YEAR + 99:
        return unparsed(text, "out_of_range")
    if start is not None and end is not None and start > end:
        start, end = end, start
    return {"start": start, "end": end, "kind": kind, "approx": approx}


def unparsed(text, why="no_pattern"):
    return {"start": None, "end": None, "kind": "unparsed", "approx": False, "why": why}


def parse_time(text):
    """Parse one meta/time string. Returns dict(start, end, kind, approx) or None if empty.

    kind: year | range | century | part_century | before | after | unparsed
    """
    if text is None:
        return None
    s = " ".join(text.split())
    if not s:
        return None
    approx = bool(APPROX.search(s))

    m = TRAILING.search(s)
    if m:
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        return _result(a, b, "year" if a == b else "range", approx, text)

    m = POLISH_DECADES.search(s)
    if m:
        base = (roman_to_int(m.group(3)) - 1) * 100
        a = base + int(m.group(1)) * 10
        b = base + int(m.group(2) or m.group(1)) * 10 + 9
        return _result(a, b, "range", approx, text)

    century = None
    m = ROMAN_CENTURY.search(s)
    if m:
        c1 = roman_to_int(m.group(1))
        c2 = roman_to_int(m.group(2)) if m.group(2) else c1
        century = (c1, c2)
    else:
        m = ARABIC_CENTURY.search(s)
        if m and not YEAR.search(s):
            c = int(m.group(1))
            century = (c, c)
    if century:
        c1, c2 = century
        if not 1 <= c1 <= 21 or not c1 <= c2 <= 21:
            return unparsed(text, "bad_century")
        base1, base2 = (c1 - 1) * 100, (c2 - 1) * 100
        if c2 == c1 + 1 and TURN.search(s):
            return _result(base2 - 25, base2 + 24, "part_century", approx, text)
        if c1 == c2:
            for rx, a, b in PARTS:
                if rx.search(s):
                    return _result(base1 + a, base1 + b, "part_century", approx, text)
        return _result(base1, base2 + 99, "century", approx, text)

    years = []
    for m in YEAR.finditer(s):
        y = int(m.group(1))
        years.append(y)
        if m.group(2):  # "1440/45" -> 1445, "1488–94" -> 1494
            short = int(m.group(2))
            full = y - y % 100 + short
            if full >= y:
                years.append(full)
    years = [y for y in years if MIN_YEAR <= y <= MAX_YEAR]
    if not years:
        return unparsed(text)
    a, b = min(years), max(years)
    if a == b:
        if BEFORE.search(s) or s.startswith("-"):
            return _result(None, a, "before", approx, text)
        if AFTER.search(s) and not re.search(r"\bnach\s+\d{1,2}\.\d{1,2}", s):
            return _result(a, None, "after", approx, text)
        return _result(a, a, "year", approx, text)
    return _result(a, b, "range", approx, text)


def century_of(parsed):
    """Century bucket (e.g. 1500 for 1500-1599) only when the whole range sits in one century."""
    if not parsed or parsed["start"] is None or parsed["end"] is None:
        return None
    c1, c2 = parsed["start"] // 100 * 100, parsed["end"] // 100 * 100
    return c1 if c1 == c2 else None
