#!/usr/bin/env python3
"""Import the National Gallery of Art, Washington (open data, CC0, https://github.com/NationalGalleryOfArt/opendata).

    python3 scripts/import_nga.py

1. download the collection CSVs (objects, subject terms, artists, images) into data/raw/nga/ once; delete them to refresh
2. map NGA 'Theme' and 'Keyword' terms to Iconclass: the Art Institute import's English term map (theme labels and
   aliases, English labels of Wikidata subjects with an Iconclass notation) plus a reviewed list of NGA terms (TERMS)
   and NGA terms that are too generic (STOP)
3. drop photographs, the Index of American Design (1930s renderings of American objects), portfolios, volumes and
   technical material, and works already harvested from Wikidata, The Met or the Art Institute
4. artists: NGA constituents carry Wikidata and ULAN ids -> existing artists, or new ones looked up on Wikidata (ULAN
   ids through P245); failing that, NGA's nationality is a low-confidence country proxy. NGA's attribution prefixes
   ('Attributed to', 'Workshop of', 'after') are kept as qualifiers. A work's own renown is the number of Wikipedia
   editions of its Wikidata item.
Output: data/sources/nga_objects.jsonl.gz, data/enrichment/nga_creators.tsv
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
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from etl.geo import Countries  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.normalize import ObjectTyper, classify  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(os.path.dirname(__file__), file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wdh = _load("wdh", "fetch_wikidata_artworks.py")
aic = _load("aic", "fetch_aic.py")
ec = _load("ec", "enrich_creators.py")

RAW = os.path.join(ROOT, "data", "raw", "nga")
BASE = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/"
FILES = ("objects", "objects_terms", "objects_constituents", "constituents", "published_images")
UA = "DaedalusThread/0.1 (https://github.com/Farechiga/daedalus-thread; batch harvest)"
OUT = os.path.join(ROOT, "data", "sources", "nga_objects.jsonl.gz")
DB = os.path.join(ROOT, "data", "db", "daedalus.sqlite")
OUT_CRE = os.path.join(ROOT, "data", "enrichment", "nga_creators.tsv")
SKIP_CLASS = {"Photograph", "Index of American Design", "Portfolio", "Volume", "Technical Material",
              "Time-Based Media Art", "(not assigned)"}
ROLES = {"artist", "painter", "sculptor", "medalist", "engraver", "artist after"}
# NGA terms mapped by hand (reviewed 2026-11-14): terms the general map misses, and god names that it would read as
# planets (Venus, Mars, Mercury, Jupiter, Neptune). 'Mother and Child' is left out: at NGA it is often secular (Cassatt).
TERMS = {
    "horse": ["46C1314"], "horses": ["46C1314"], "christ": ["11D"], "life of christ": ["73"], "saints": ["11H"],
    "life of the virgin mary": ["73A"], "cupid": ["92D1"], "putti": ["92D1916"], "sun": ["24"], "moon": ["24"],
    "stars": ["24"], "forest": ["25H15"], "lake": ["25H22"], "ocean": ["25H23"], "seascape": ["25H23"],
    "coast": ["25H23"], "field": ["25H17"], "sky": ["26A"], "clouds": ["26A"], "monster": ["25FF"],
    "deer": ["25F24(DEER)"], "rabbit": ["25F26"], "monkey": ["25F22"], "virtues and vices": ["11M", "11N"],
    "sin": ["11N"], "apocalypse": ["73G"], "sebastian": ["11H(SEBASTIAN)"], "peter": ["11H(PETER)"],
    "minerva": ["92C2"], "mythology": ["92"], "venus": ["92C4"], "mars": ["92B4"], "mercury": ["92B5"],
    "jupiter": ["92B1"], "neptune": ["92H1"],
}
# generic NGA terms that the general map would read too specifically: a skull is often anatomy, not a Vanitas
STOP = {"skull", "season"}
# background terms: NGA tags any tree or cloud in a picture, so a city print or a caricature would land in Landscape.
# They count only when the work is also tagged as a landscape.
INCIDENTAL = {"tree", "trees", "cloud", "clouds", "sky", "grass", "leaf"}
LANDSCAPE = {"landscape", "nature", "topographical", "forest", "country landscape", "mountain", "mountains", "river",
             "seascape", "lake", "waterfall", "panorama", "pastoral", "field"}


def log(msg):
    wdh.log(msg)


def download():
    os.makedirs(RAW, exist_ok=True)
    for f in FILES:
        path = os.path.join(RAW, f + ".csv")
        if not os.path.exists(path):
            log(f"downloading {f}.csv")
            req = urllib.request.Request(BASE + f + ".csv", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as fh:
                while chunk := r.read(1 << 20):
                    fh.write(chunk)
            os.replace(path + ".part", path)


def rows(name):
    csv.field_size_limit(1 << 30)
    with open(os.path.join(RAW, name + ".csv"), encoding="utf-8", newline="") as fh:
        yield from csv.DictReader(fh)


def year(v):
    try:
        y = int(v)
    except (TypeError, ValueError):
        return None
    return y if 100 <= y <= 2026 else None


def main():
    download()
    ic = Iconclass()
    tax = Taxonomy(ic)
    tmap = aic.term_map(tax, ic)
    for term, codes in TERMS.items():
        assert all(ic.resolve(c) for c in codes), term
        tmap[aic.norm(term)] = set(codes)
    stop = aic.STOP_TERMS | STOP

    objects = {r["objectid"]: r for r in rows("objects")}
    terms = collections.defaultdict(list)
    for r in rows("objects_terms"):
        if r["termtype"] in ("Theme", "Keyword"):
            terms[r["objectid"]].append(r["term"])
    images = {}
    for r in rows("published_images"):
        if r["viewtype"] == "primary" and r["openaccess"] == "1":
            images.setdefault(r["depictstmsobjectid"], r["iiifurl"])
    log(f"{len(objects)} NGA objects; {len(terms)} with subject terms; {len(images)} with an open image")

    have = set()
    for f in ("wikidata_paintings.jsonl.gz", "met_objects.jsonl.gz", "aic_objects.jsonl.gz"):
        p = os.path.join(ROOT, "data", "sources", f)
        if os.path.exists(p):
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                have |= {q for q in (json.loads(line).get("qid") for line in fh) if q}

    if os.path.exists(DB):  # ICARUS itself carries a few NGA records (source 'nga'); keep those, skip ours
        have_ids = {re.search(r"art-object-page\.(\d+)", u).group(1) for (u,) in sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
                    .execute("SELECT source_url FROM artwork WHERE source_id = 'nga' AND dataset = 'icarus'")
                    if re.search(r"art-object-page\.(\d+)", u or "")}
    else:
        have_ids = set()
    kept, dropped = [], collections.Counter()
    for oid, o in objects.items():
        if oid in have_ids:
            dropped["in_icarus"] += 1
            continue
        if o["classification"] in SKIP_CLASS or o["isvirtual"] == "1":
            dropped["photo_design_index_portfolio"] += 1
            continue
        if o["wikidataid"] and o["wikidataid"] in have:
            dropped["already_harvested"] += 1
            continue
        names = {aic.norm(t) for t in terms.get(oid, ())}
        scenic = bool(names & LANDSCAPE)
        codes = sorted({c for t in names - stop if scenic or t not in INCIDENTAL for c in tmap.get(t, ())})
        if not codes:
            dropped["no_mapped_subject"] += 1
            continue
        kept.append((o, codes))
    log(f"kept {len(kept)}; dropped {dict(dropped)}")

    # ---- the work's own renown: Wikipedia editions of its Wikidata item (NGA gives the id)
    qids = sorted({o["wikidataid"] for o, _ in kept if re.fullmatch(r"Q\d+", o["wikidataid"] or "")})
    sitelinks = {}
    for i in range(0, len(qids), 300):
        res = wdh.cached("nga_work_links", qids[i:i + 300], lambda keys: wdh.sparql(
            "SELECT ?w ?n WHERE { VALUES ?w { %s } ?w wikibase:sitelinks ?n }" % " ".join(f"wd:{k}" for k in keys)))
        sitelinks.update({wdh.qid(b["w"]["value"]): int(b["n"]["value"]) for b in res})
    log(f"{len(qids)} works on Wikidata; {sum(1 for v in sitelinks.values() if v)} with a Wikipedia article")

    # ---- artists
    keep_ids = {o["objectid"] for o, _ in kept}
    links = collections.defaultdict(list)
    for r in rows("objects_constituents"):
        if r["objectid"] in keep_ids and r["roletype"] == "artist" and r["role"] in ROLES:
            links[r["objectid"]].append(r)
    cons = {r["constituentid"]: r for r in rows("constituents")}
    used = {r["constituentid"] for rs in links.values() for r in rs}
    ulans = sorted({cons[c]["ulanid"] for c in used if c in cons and cons[c]["ulanid"] and not cons[c]["wikidataid"]})
    ulan_q = {}
    for i in range(0, len(ulans), 300):  # ULAN id -> Wikidata (P245)
        chunk = ulans[i:i + 300]
        res = wdh.cached("ulan_qids", chunk, lambda keys: wdh.sparql(
            "SELECT ?id ?c WHERE { VALUES ?id { %s } ?c wdt:P245 ?id }" % " ".join(f'"{k}"' for k in keys)))
        ulan_q.update({b["id"]["value"]: wdh.qid(b["c"]["value"]) for b in res})

    known = {}
    for f in ("creator_geo.tsv", "wikidata_creators.tsv", "met_creators.tsv", "aic_creators.tsv", "zeri_creators.tsv",
              "joconde_creators.tsv"):
        p = os.path.join(ROOT, "data", "enrichment", f)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
                if r.get("wikidata_qid"):
                    known.setdefault(r["wikidata_qid"], r["name_key"])
                if r.get("ulan_id") and r.get("status") == "matched":
                    known.setdefault("ulan:" + r["ulan_id"], r["name_key"])

    def resolve(c):
        """constituent -> (key, qid) or None for anonymous makers."""
        if c["constituenttype"] == "anonymous":
            return None
        name = c["forwarddisplayname"] or c["preferreddisplayname"]
        q = c["wikidataid"] or ulan_q.get(c["ulanid"])
        key = known.get(q) or known.get(f"ulan:{c['ulanid']}") or (f"wd:{q}" if q else None)
        if not key and name:
            cl = classify(name)
            key = cl["name_key"] if cl["kind"] in ("person", "master") else None
        return (key, q) if key else None

    new_q = {r[1] for c in used if c in cons and (r := resolve(cons[c])) and r[1] and r[1] not in known}
    creators = wdh.creator_details(new_q) if new_q else {}
    log(f"{len(used)} NGA artists; {len(new_q)} new Wikidata artists")

    natmap = json.load(open(ec.NATIONALITY_MAP, encoding="utf-8"))["map"]
    unlinked = {}  # key -> (name, ulan, country from nationality, n)
    typer = ObjectTyper()
    n_attr = 0
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for o, codes in kept:
            cre = []
            for r in sorted(links.get(o["objectid"], []), key=lambda r: int(r["displayorder"] or 0))[:4]:
                c = cons.get(r["constituentid"])
                res = resolve(c) if c else None
                if not res:
                    continue
                key, q = res
                qual = " ".join((r["prefix"] or "").split()) or None
                if r["role"] == "artist after" and not re.search(r"after", qual or "", re.I):
                    qual = f"{qual} after" if qual else "after"
                n_attr += bool(qual)
                name = c["forwarddisplayname"] or c["preferreddisplayname"]
                cre.append({"qid": q, "name": name, "key": key, "qualifier": qual})
                if not q and key not in known:
                    nat = (c["nationality"] or "").split(",")[0].strip()
                    prev = unlinked.get(key)
                    unlinked[key] = (name, c["ulanid"] or None, natmap.get(nat), (prev[3] if prev else 0) + 1)
            b, e = year(o["beginyear"]), year(o["endyear"])
            date = [b, e, "year" if b == e else "range"] if b and e and b <= e else None
            image = f"{images[o['objectid']]}/full/640,/0/default.jpg" if o["objectid"] in images else None
            fh.write(json.dumps({
                "id": f"nga-{o['objectid']}", "dataset": "nga", "source_id": "nga",
                "source_url": f"https://www.nga.gov/collection/art-object-page.{o['objectid']}.html",
                "qid": o["wikidataid"] or None, "title": o["title"], "links": sitelinks.get(o["wikidataid"]), "highlight": False,
                "creators": cre, "date": date, "date_text": o["displaydate"] or None,
                "approx": bool(re.search(r"\bc\.|circa", o["displaydate"] or "", re.I)),
                "holding": "National Gallery of Art, Washington", "department": o["departmentabbr"] or None,
                "object_type": typer.type_of([o["classification"], o["subclassification"]], [o["medium"] or ""], "nga"),
                "instance_of": o["classification"], "image": image, "culture": None,
                "subjects": terms.get(o["objectid"]), "iconclass": codes,
            }, ensure_ascii=False) + "\n")
    log(f"{n_attr} artist credits carry an attribution qualifier")

    countries = Countries()
    cols = ["name_key", "display_name", "n_artworks", "status", "match_method", "match_confidence", "ulan_id", "ulan_name",
            "ulan_birth", "ulan_death", "wikidata_qid", "country_code", "country_name", "proxy_type", "evidence_source",
            "geo_confidence", "birth_place", "birth_lat", "birth_lon", "nationality", "notes", "candidates", "links"]
    with open(OUT_CRE, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh, delimiter="\t", lineterminator="\n")
        wr.writerow(cols)
        for c, d in sorted(creators.items()):
            if not d["human"]:
                continue
            code = countries.locate(d["lon"], d["lat"]) if d["lon"] is not None else None
            wr.writerow(["wd:" + c, d["name"], 0, "matched", "wikidata_identifier", "high", d["ulan"], None,
                         d["birth"], d["death"], c, code, countries.info[code]["name"] if code else None,
                         "birthplace" if code else None, "wikidata" if code else None, "high" if code else None,
                         d["place"], d["lat"], d["lon"], None, None, None, d["links"]])
        for key, (name, ulan, code, n) in sorted(unlinked.items()):
            wr.writerow([key, name, n, "unmatched", "nga_constituent", None, ulan, None, None, None, None, code,
                         countries.info[code]["name"] if code and code in countries.info else None,
                         "nationality" if code else None, "nga_nationality" if code else None, "low" if code else None,
                         None, None, None, None, None, None, None])
    log(f"wrote {len(kept)} NGA records -> {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB); "
        f"{len(unlinked)} artists without Wikidata ({sum(1 for v in unlinked.values() if v[2])} with a nationality)")


if __name__ == "__main__":
    main()
