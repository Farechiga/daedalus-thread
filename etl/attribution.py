"""Attribution qualifiers ('school of', 'after', 'zugeschrieben', "d'après") -> one English label and a fame weight.

A work credited to a famous name with a qualifier is not that artist's work: a copy or print 'after Rubens' borrows
almost none of his renown, a 'school of Rembrandt' sheet little, an 'attributed to' work most of it.
Labels come from ICARUS (German, Dutch, English), Joconde (French) and RKD (English). Qualifiers that only carry
dates ('um 1435-um 1529', '17e eeuw') are not attributions.
"""
import re
import unicodedata

# checked in order: the strongest discount wins ('manner of/after' -> after; 'workshop of, attributed' -> workshop)
RULES = [
    (r"\bcop(y|ie|ia)\b|\bkopie", "copy after", 0.15),
    (r"\bafter\b|\bnach\b|\bnaar\b|d'?apres|\bd apres", "after", 0.15),
    (r"\bmanner\b|maniere|maniera|art des\b|in de trant|genre de|style of|\bstijl", "manner of", 0.15),
    (r"imitat|navolging|nachahm", "imitator of", 0.15),
    (r"workshop|werkstatt|werkplaats|atelier|bottega|\bstudio\b", "workshop of", 0.35),
    (r"school|schule|\becole\b|scuola", "school of", 0.35),
    (r"circle|umkreis|\bkring\b|entourage|cerchia|omgeving", "circle of", 0.35),
    (r"follower|nachfolge|navolger|suiveur|seguace", "follower of", 0.35),
    (r"attrib|zugeschr|toegeschr", "attributed to", 0.7),
    (r"possibl|probabl|\bwohl\b|vermutlich|alternativ|\?|^or\b|\bor\b", "possibly", 0.7),
]
_COMPILED = [(re.compile(p), label, w) for p, label, w in RULES]


def _fold(s):
    s = unicodedata.normalize("NFKD", s.replace("’", "'").casefold())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def classify_attribution(qualifier):
    """-> (label, weight); (None, 1.0) when the qualifier is empty or not an attribution."""
    if not qualifier:
        return None, 1.0
    q = _fold(qualifier)
    for rx, label, weight in _COMPILED:
        if rx.search(q):
            return label, weight
    return None, 1.0


WEIGHT = {label: w for _, label, w in RULES}
