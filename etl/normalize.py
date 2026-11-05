"""Creator-name and object-type normalisation for the importer.

Creators: each raw `meta/creator` value is classified (person, anonymous, monogrammist/named
master, institution, qualifier-only) and given a `name_key` (accent-folded, order-independent
token set) used to merge spelling variants such as "Rubens, Peter Paul" / "Peter Paul Rubens".
Life dates and qualifiers in parentheses are split off, not discarded.
"""
import json
import os
import re
import unicodedata

OBJECT_TYPES = os.path.join(os.path.dirname(__file__), "..", "taxonomy", "object_types.json")

ANON = re.compile(r"\b(anonym\w*|anoniem|unbekannt\w*|unknown|onbekend\w*|nieokreślony|nieznany|anonim\w*|ignoto|n\.\s?n\.)", re.I)
MONOGRAM = re.compile(r"\bmonogramm\w*", re.I)
MASTER = re.compile(r"^(meister|master|meester|maître|mistrz)\b", re.I)
INSTITUTION = re.compile(
    r"\b(staten|staten-generaal|kroon|crown|hof|court|regering|stadsbestuur|verlag|druck|drukkerij|druckerei|"
    r"gebr\.?|& co|co\.|firma|compagnie|maatschappij|gesellschaft|universit\w*|museum|kaiser|keizer|könig|koning|"
    r"koningin|emperor|king|queen|paus|pope|papst|veb)\b", re.I)
QUALIFIER_WORDS = (r"werkstatt|umkreis|nachfolger|nachahmer|schule|kopie|zugeschrieben|attributed|toegeschreven|workshop|"
                   r"circle|follower|manner|copy|school|naar|omgeving|navolger|atelier|kring|after|nach|alternativ|art des|und werkstatt")
QUALIFIER_ONLY = re.compile(rf"^\(?\s*({QUALIFIER_WORDS})\s*\)?\.?$", re.I)
QUALIFIER_IN = re.compile(rf"\b({QUALIFIER_WORDS})\b", re.I)
PAREN = re.compile(r"\(([^)]*)\)")
LIFE_DATES = re.compile(r"\b(\d{3,4})\s*[-–]\s*(\d{3,4})\b")


def fold(s):
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c)).replace("ß", "ss")


def classify(raw):
    """Return dict(kind, name_key, display, qualifier, life_dates) for one raw creator string."""
    s = " ".join(raw.split())
    if QUALIFIER_ONLY.match(s):
        return {"kind": "qualifier", "name_key": None, "display": s, "qualifier": s.strip("() ."), "life_dates": None}
    if ANON.search(s):
        return {"kind": "anonymous", "name_key": "anonymous", "display": "Anonymous / unknown",
                "qualifier": None, "life_dates": None}
    life = LIFE_DATES.search(s)
    qualifiers = []
    core = s
    for inner in PAREN.findall(s):
        if re.search(r"\d", inner) or QUALIFIER_IN.search(inner):
            qualifiers.append(inner.strip())
            core = core.replace(f"({inner})", " ")
    core = LIFE_DATES.sub(" ", core)
    core = re.sub(r",\s*(werkstatt|umkreis|schule|nachfolger|workshop|circle|school)\b.*$", "", core, flags=re.I)
    core = " ".join(core.replace("( )", " ").split()).strip(" ,;")
    tokens = sorted(set(re.findall(r"[a-z0-9]+", fold(core))))
    kind = "person"
    if MONOGRAM.search(s) or MASTER.search(s):
        kind = "master"
    elif INSTITUTION.search(s):
        kind = "institution"
    return {"kind": kind, "name_key": " ".join(tokens) or fold(core), "display": display_form(core),
            "qualifier": "; ".join(q for q in qualifiers if not re.fullmatch(r"[\d\s/–-]+", q)) or None,
            "life_dates": f"{life.group(1)}–{life.group(2)}" if life else None}


def display_form(core):
    """'Galle, Philips' -> 'Philips Galle'; leaves multi-comma or institutional strings alone."""
    if core.count(",") == 1:
        last, first = (p.strip() for p in core.split(","))
        if first and last and not re.search(r"\d", core) and len(first.split()) <= 4:
            suffix = " ".join(PAREN.findall(first))  # "Hans (d.Ä.)" -> "Hans Holbein (d.Ä.)"
            first = PAREN.sub("", first).strip()
            return f"{first} {last}" + (f" ({suffix})" if suffix else "")
    return core


class ObjectTyper:
    def __init__(self, path=OBJECT_TYPES):
        cfg = json.load(open(path, encoding="utf-8"))
        self.types = cfg["types"]
        self.patterns = [(t, re.compile(p, re.I)) for t, p in cfg["patterns"]]
        self.source_defaults = cfg["source_defaults"]
        self._cache = {}

    def _match(self, value):
        hit = self._cache.get(value)
        if hit is None:
            hit = next((t for t, rx in self.patterns if rx.search(value)), "")
            self._cache[value] = hit
        return hit or None

    def type_of(self, instance_of, genre, source_id):
        for v in list(instance_of) + list(genre):
            t = self._match(v)
            if t:
                return t
        return self.source_defaults.get(source_id, "other")
