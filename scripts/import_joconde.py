#!/usr/bin/env python3
"""Import Joconde, the catalogue of the Musées de France (French Ministry of Culture, Licence Ouverte 2.0).

    curl -L -o data/raw/joconde/joconde.csv https://ministere-culture.s3.sbg.io.cloud.ovh.net/POP/joconde.csv  # 1.25 GB
    python3 scripts/import_joconde.py

About 1.06 million records from some 1,200 French museums, about 600,000 of them paintings, drawings, prints and
sculpture. 'Sujet représenté' is a controlled French vocabulary ("scène biblique (Annonciation, ange)"): its terms
are mapped to taxonomy themes by taxonomy/joconde_terms.json (reviewed by hand; scoped by category).
1. keep art domains (painting, drawing, print, sculpture, stained glass, tapestry, illumination) with a mapped subject
2. drop records already harvested from Wikidata (P347 = Joconde id)
3. artists: an existing name key, else Getty ULAN (name + life dates from 'Précisions sur l'auteur') -> Wikidata
   birthplace, else the school ('École') as a nationality proxy
Output: data/sources/joconde_objects.jsonl.gz, data/enrichment/joconde_creators.tsv.
"""
import collections
import csv
import gzip
import importlib.util
import json
import os
import re
import sqlite3
import sys
import unicodedata

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from etl.geo import Countries  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.normalize import classify  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(os.path.dirname(__file__), file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wdh = _load("wdh", "fetch_wikidata_artworks.py")
ec = _load("ec", "enrich_creators.py")

CSV = os.path.join(ROOT, "data", "raw", "joconde", "joconde.csv")
TERMS = os.path.join(ROOT, "taxonomy", "joconde_terms.json")
OUT = os.path.join(ROOT, "data", "sources", "joconde_objects.jsonl.gz")
OUT_CRE = os.path.join(ROOT, "data", "enrichment", "joconde_creators.tsv")
DB = os.path.join(ROOT, "data", "db", "daedalus.sqlite")
csv.field_size_limit(10 ** 9)

# Domaine -> object type, first match wins (a 'dessin;peinture' design for a painting is a drawing)
DOMAINS = [("vitrail", "stained-glass"), ("enluminure", "book-illustration"), ("estampe", "print"),
           ("dessin", "drawing"), ("peinture", "painting"), ("sculpture", "sculpture"), ("tapisserie", "decorative-arts")]
WALL = re.compile(r"peinture murale|fresque|décor peint|plafond", re.I)
# École / pays -> present-day country (schools named after Italian cities are Italian)
SCHOOLS = {"france": "FRA", "alsace": "FRA", "lorraine": "FRA", "francaise": "FRA", "italie": "ITA", "italienne": "ITA",
           "florence": "ITA", "florentine": "ITA", "romaine": "ITA", "ombrienne": "ITA", "bolonaise": "ITA",
           "venitienne": "ITA", "lombarde": "ITA", "napolitaine": "ITA", "sicilienne": "ITA", "genoise": "ITA",
           "siennoise": "ITA", "ferraraise": "ITA", "parmesane": "ITA", "piemontaise": "ITA", "toscane": "ITA",
           "espagne": "ESP", "espagnole": "ESP", "pays-bas": "NLD", "hollandaise": "NLD", "flandres": "BEL",
           "flamande": "BEL", "belgique": "BEL", "allemagne": "DEU", "allemande": "DEU", "grande-bretagne": "GBR",
           "anglaise": "GBR", "suisse": "CHE", "autriche": "AUT", "portugal": "PRT", "russie": "RUS", "pologne": "POL",
           "danemark": "DNK", "suede": "SWE", "etats-unis": "USA", "grece": "GRC", "japon": "JPN", "chine": "CHN"}
ALIAS = re.compile(r"\((dit|dite|pseudonyme|nom de religion|surnom)\)", re.I)


def norm(s):
    return " ".join(unicodedata.normalize("NFC", s.replace("’", "'").casefold()).split())


def fold(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", norm(s)) if not unicodedata.combining(ch))


class SubjectMap:
    def __init__(self, tax, ic):
        cfg = json.load(open(TERMS, encoding="utf-8"))
        self.tax = tax
        self.maps = {}
        # accented source terms must match exactly ('châsse' is a reliquary, not a 'chasse', a hunt);
        # unaccented ones may also match a folded entry ('Education' ~ 'Éducation')
        self.folded = {}
        for scope in ("any", "figure", "animal", "landscape", "allegory"):
            self.maps[scope] = {norm(k): self.code(v) for k, v in cfg[scope].items()}
            self.folded[scope] = {fold(k): c for k, c in self.maps[scope].items()}
        self.fallback = {fold(k): self.code(v) for k, v in cfg["fallback"].items()}
        self.cats = {k: {fold(c) for c in cfg[k]} for k in
                     ("religious_categories", "figure_categories", "myth_categories", "landscape_categories",
                      "allegory_categories", "skip_categories")}
        self.skip_prefix = tuple(fold(p) for p in cfg["skip_category_prefixes"])
        bad = [c for m in list(self.maps.values()) + [self.fallback] for c in m.values() if not ic.resolve(c)]
        assert not bad, bad

    def code(self, v):
        return v[3:] if v.startswith("ic:") else Taxonomy.include(self.tax.nodes[v])[0]

    def lookup(self, scope, term):
        hit = self.maps[scope].get(term)
        if hit is None and term == fold(term):
            hit = self.folded[scope].get(term)
        return hit

    @staticmethod
    def pieces(s):
        out, depth, cur = [], 0, ""
        for ch in s:
            depth += ch == "("
            depth -= ch == ")"
            if ch in ",;" and depth <= 0:
                out.append(cur)
                cur, depth = "", 0
            else:
                cur += ch
        return [p.strip() for p in out + [cur] if p.strip()]

    def codes(self, subject):
        parsed = []
        for p in self.pieces(subject):
            m = re.match(r"([^()]*)\((.*)\)?", p)
            if m and m.group(1).strip():
                parsed.append((fold(m.group(1)), [norm(t) for t in re.split(r"[,;:]", m.group(2).rstrip(")")) if t.strip()]))
            else:
                parsed.append((None, [norm(p.strip("() "))]))
        cats = {c for c, _ in parsed if c} | {fold(t[0]) for c, t in parsed if not c}  # 'paysage;hiver': bare 'paysage' sets the context
        landscape = bool(cats & self.cats["landscape_categories"])
        allegory = bool(cats & self.cats["allegory_categories"])
        out = set()
        for cat, terms in parsed:
            if cat and (cat in self.cats["skip_categories"] or cat.startswith(self.skip_prefix)):
                continue
            scopes = ["any"]
            if cat in self.cats["figure_categories"]:
                scopes.append("figure")
            if cat not in self.cats["religious_categories"] and cat not in self.cats["myth_categories"]:
                scopes.append("animal")
            if cat in self.cats["landscape_categories"] or (cat is None and landscape):
                scopes.append("landscape")
            if cat in self.cats["allegory_categories"] or (cat is None and allegory):
                scopes.append("allegory")
            found = {c for t in terms for s in scopes for c in [self.lookup(s, t)] if c}
            if not found and cat in self.fallback:
                found = {self.fallback[cat]}
            out |= found
        return sorted(out)


ORD = r"(\d+)\s*(?:e|er|ère|eme|ème)"


def parse_period(text):
    """'2e quart 19e siècle', '1ère moitié 17e siècle', 'début 16e siècle' (several joined by ';') -> (start, end)."""
    spans = []
    for part in (text or "").split(";"):
        p = fold(part)
        m = re.search(ORD + r"\s*siecle", p)
        if not m or re.search(r"av\.?\s*j|avant", p):
            continue
        c0 = (int(m.group(1)) - 1) * 100
        q = re.search(ORD + r"\s*quart", p)
        h = re.search(ORD + r"\s*moitie", p)
        if q and 1 <= int(q.group(1)) <= 4:
            a = c0 + (int(q.group(1)) - 1) * 25
            spans.append((a, a + 25))
        elif h and 1 <= int(h.group(1)) <= 2:
            a = c0 + (int(h.group(1)) - 1) * 50
            spans.append((a, a + 50))
        elif "debut" in p:
            spans.append((c0, c0 + 20))
        elif "fin" in p:
            spans.append((c0 + 80, c0 + 100))
        elif "milieu" in p:
            spans.append((c0 + 40, c0 + 60))
        else:
            spans.append((c0, c0 + 100))
    if not spans:
        return None
    s, e = min(a for a, _ in spans), max(b for _, b in spans)
    return (s + 1 if s % 100 == 0 and s else s, e) if 100 <= e <= 2026 else None


def parse_date(row):
    years = [int(y) for y in re.findall(r"\b(1\d{3}|20[0-2]\d)\b", row["Millesime_de_creation"] or "")]
    approx = bool(re.search(r"vers|\?|environ", row["Millesime_de_creation"] or "", re.I))
    if years:
        s, e = min(years), max(years)
        return [s, e, "year" if s == e else "range"], approx
    per = parse_period(row["Periode_de_creation"])
    return ([per[0], per[1], "range"], True) if per else (None, False)


def object_type(row):
    dom = fold(row["Domaine"] or "")
    for word, t in DOMAINS:
        if word in dom:
            if t == "painting" and WALL.search(row["Denomination"] or ""):
                return "wall-painting"
            return t
    return None


def creators_of(row):
    out = []
    for raw in (row["Auteur"] or "").split(";"):
        raw = raw.strip()
        if not raw or ALIAS.search(raw):
            continue
        raw = re.sub(r"\([^)]*$", "", raw).strip()  # 'Millet Jean-François (1814-1875' (unclosed)
        raw = re.sub(r"\s*\([^)]*\)", "", raw).strip()  # roles and attributions: (graveur), (d'après), (atelier de)
        c = classify(raw)
        if c["kind"] in ("person", "master") and c["name_key"]:
            out.append((c["name_key"], display_name(raw)))
    return out


PARTICLE = {"van", "von", "de", "der", "den", "di", "da", "del", "della", "du", "des", "la", "le", "ter", "ten", "y"}


def display_name(raw):
    """'VAN DER MEULEN Adam Frans' -> 'Adam Frans van der Meulen' (Joconde writes the surname in capitals first)."""
    toks = raw.split()
    n = 0
    while n < len(toks) and toks[n].upper() == toks[n] and re.search(r"[A-ZÀ-Ý]{2}", toks[n]):
        n += 1
    if not 0 < n < len(toks):
        return raw
    surname = " ".join(t.lower() if t.lower() in PARTICLE and i < n - 1 else t.capitalize() if "-" not in t else
                       "-".join(x.capitalize() for x in t.split("-")) for i, t in enumerate(toks[:n]))
    return " ".join(toks[n:]) + " " + surname


def life_years(row, n_authors):
    """'Paris, 1789 ; Paris, 1850' -> (1789, 1850) for single-author records."""
    if n_authors != 1:
        return None
    parts = [re.findall(r"\b(1\d{3})\b", p) for p in (row["Precisions_sur_l_auteur"] or "").split(";")]
    if len(parts) == 2 and parts[0] and parts[1]:
        b, d = int(parts[0][-1]), int(parts[1][-1])
        if 15 <= d - b <= 105:
            return b, d
    return None


def schools(row):
    out = set()
    for s in (row["Ecole_pays"] or "").split(";"):
        s = fold(s)
        if "apres" in s:  # 'Espagne (d'après)': the model's school, not the maker's
            continue
        head = re.split(r"[,(]", s)[0].strip()
        if head in SCHOOLS:
            out.add(SCHOOLS[head])
    return out


def sentence_case(t):
    t = " ".join((t or "").split())
    return t[0] + t[1:].lower() if t and t.upper() == t and re.search(r"[A-Z]{3}", t) else t or None


def main():
    ic = Iconclass()
    tax = Taxonomy(ic)
    smap = SubjectMap(tax, ic)

    rows_wd = wdh.cached("joconde_ids", ["all"], lambda _: wdh.sparql("SELECT ?w ?id WHERE { ?w wdt:P347 ?id }"))
    joc_to_qid = {b["id"]["value"]: wdh.qid(b["w"]["value"]) for b in rows_wd}
    have = set()
    for f in ("wikidata_paintings.jsonl.gz", "met_objects.jsonl.gz"):
        p = os.path.join(ROOT, "data", "sources", f)
        if os.path.exists(p):
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                have |= {json.loads(line)["qid"] for line in fh}

    kept, dropped = [], collections.Counter()
    cre_info = collections.defaultdict(lambda: {"names": collections.Counter(), "years": [], "life": collections.Counter(),
                                                "schools": collections.Counter(), "n": 0})
    with open(CSV, encoding="utf-8", errors="replace", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh, delimiter="|")):
            if i % 200000 == 0:
                wdh.log(f"{i} rows read, {len(kept)} kept")
            otype = object_type(row)
            if not otype:
                dropped["not_an_art_domain"] += 1
                continue
            codes = smap.codes(row["Sujet_Represente"] or "")
            if not codes or not any(tax.match([c])[0] for c in codes):
                dropped["no_mapped_subject"] += 1
                continue
            ref = row["Reference"].strip()
            if joc_to_qid.get(ref) in have:
                dropped["already_in_wikidata_harvest"] += 1
                continue
            date, approx = parse_date(row)
            cre = creators_of(row)
            life = life_years(row, len(cre))
            sch = schools(row)
            for key, name in cre[:4]:
                info = cre_info[key]
                info["names"][name] += 1
                info["n"] += 1
                if date:
                    info["years"].append((date[0] + date[1]) / 2)
                if life:
                    info["life"][life] += 1
                for s in sch:
                    info["schools"][s] += 1
            museum = " ".join((row["Nom_officiel_musee"] or "").split())
            city = (row["Ville"] or "").strip()
            holding = (museum[:1].upper() + museum[1:] + (f", {city}" if city and city.lower() not in museum.lower() else "")) if museum else city or None
            kept.append({
                "id": f"joconde-{ref}", "dataset": "joconde", "source_id": "joconde",
                "source_url": f"https://pop.culture.gouv.fr/notice/joconde/{ref}", "qid": joc_to_qid.get(ref),
                "title": sentence_case(row["Titre"]) or sentence_case(row["Denomination"].split(";")[0]),
                "links": None, "highlight": False, "creators": [{"qid": None, "name": n, "key": k} for k, n in cre[:4]],
                "date": date, "date_text": row["Millesime_de_creation"] or row["Periode_de_creation"] or None,
                "approx": approx, "holding": holding, "object_type": otype,
                "instance_of": (row["Denomination"] or "").split(";")[0] or None, "image": None,
                "culture": row["Ecole_pays"] or None, "subjects": row["Sujet_Represente"], "iconclass": codes})
    wdh.log(f"kept {len(kept)}; dropped {dict(dropped)}")
    wdh.log(f"object types: {collections.Counter(r['object_type'] for r in kept).most_common()}")

    # ---- creators: existing key -> ULAN (name + life dates) -> school
    existing, ulan_to_key = set(), {}
    if os.path.exists(DB):
        existing |= {k for (k,) in sqlite3.connect(f"file:{DB}?mode=ro", uri=True).execute(  # not Joconde's own (re-runs)
            "SELECT DISTINCT c.name_key FROM creator c JOIN artwork_creator ac ON ac.creator_id = c.id "
            "JOIN artwork a ON a.rid = ac.artwork_rid WHERE a.dataset <> 'joconde'")}
    for f in ("creator_geo.tsv", "wikidata_creators.tsv", "met_creators.tsv", "aic_creators.tsv", "zeri_creators.tsv"):
        p = os.path.join(ROOT, "data", "enrichment", f)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
                existing.add(r["name_key"])
                if r.get("ulan_id") and r.get("status") == "matched":
                    ulan_to_key.setdefault(r["ulan_id"], r["name_key"])
    new = []
    for key, info in cre_info.items():
        if key in existing:
            continue
        ys = sorted(info["years"])
        span = (ys[int(len(ys) * 0.1)], ys[int(len(ys) * 0.9) - (1 if len(ys) > 1 else 0)]) if ys else None
        life = info["life"].most_common(1)[0][0] if info["life"] else None
        new.append({"key": key, "name": info["names"].most_common(1)[0][0], "kind": "person", "n": info["n"],
                    "life": f"{life[0]}–{life[1]}" if life else None, "variants": list(info["names"]), "years": ys, "span": span})
    wdh.log(f"{len(cre_info)} Joconde artists; {len(cre_info) - len(new)} already known; {len(new)} to reconcile with ULAN")
    needed = set()
    for c in new:
        needed |= {c["key"], ec.base_key(c["key"])}
    needed.discard(None)
    U = ec.load_ulan(needed)
    matches = {c["key"]: ec.match(c, U) for c in new}
    wdh.log(f"ULAN: {collections.Counter(m['status'] for m in matches.values())}")

    remap = {}  # Joconde key -> existing key of the same ULAN person ('pierre paul rubens' -> 'paul peter rubens')
    for key, m in matches.items():
        if m["status"] == "matched" and m["sid"] in ulan_to_key:
            remap[key] = ulan_to_key[m["sid"]]
    W = ec.wikidata_birthplaces([m["sid"] for k, m in matches.items() if m["status"] == "matched" and k not in remap])
    qids = {(W.get(m["sid"]) or {}).get("qid") for k, m in matches.items() if m["status"] == "matched" and k not in remap} - {None}
    details = wdh.creator_details(qids) if qids else {}
    wdh.log(f"{len(remap)} merged into existing artists via ULAN; {len(qids)} new artists with Wikidata items")

    countries = Countries()
    natmap = json.load(open(ec.NATIONALITY_MAP, encoding="utf-8"))["map"]
    cols = ["name_key", "display_name", "n_artworks", "status", "match_method", "match_confidence", "ulan_id", "ulan_name",
            "ulan_birth", "ulan_death", "wikidata_qid", "country_code", "country_name", "proxy_type", "evidence_source",
            "geo_confidence", "birth_place", "birth_lat", "birth_lon", "nationality", "notes", "candidates", "links"]
    outcome = collections.Counter()
    with open(OUT_CRE, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh, delimiter="\t", lineterminator="\n")
        wr.writerow(cols)
        for c in sorted(new, key=lambda c: -c["n"]):
            if c["key"] in remap:
                continue
            m = matches[c["key"]]
            geo = {"country": None, "proxy": None, "evidence": None, "geo_confidence": None, "place": None, "lat": None,
                   "lon": None, "nationality": None, "notes": []}
            sid = m.get("sid") if m["status"] == "matched" else None
            if sid:
                geo = ec.attribute(m, U, W, countries, natmap)
            sch = cre_info[c["key"]]["schools"]
            if not geo["country"] and sch:
                top, n_top = sch.most_common(1)[0]
                if n_top >= 0.8 * sum(sch.values()):
                    geo.update(country=top, proxy="nationality", evidence="joconde_school", geo_confidence="low")
            qid = (W.get(sid) or {}).get("qid") if sid else None
            outcome[geo["proxy"] or "none"] += c["n"]
            wr.writerow([c["key"], c["name"], c["n"], m["status"], m.get("method"), m.get("confidence"), sid,
                         U["preferred"].get(sid) if sid else None, m.get("birth"), m.get("death"), qid, geo["country"],
                         countries.info[geo["country"]]["name"] if geo["country"] else None, geo["proxy"], geo["evidence"],
                         geo["geo_confidence"], geo["place"], geo["lat"], geo["lon"], geo["nationality"],
                         "; ".join(geo["notes"]) or None, " ".join(m.get("candidates", [])) or None,
                         (details.get(qid) or {}).get("links") if qid else None])
    wdh.log(f"new-artist credits by geography: {dict(outcome)}")

    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for r in kept:
            for c in r["creators"]:
                c["key"] = remap.get(c["key"], c["key"])
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    wdh.log(f"wrote {len(kept)} Joconde records -> {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
