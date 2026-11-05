#!/usr/bin/env python3
"""Harvest Wikidata paintings for the taxonomy's themes (second source, pilot).

    python3 scripts/fetch_wikidata_artworks.py [--max-subjects N]

Bridge: Wikidata subject items that carry an Iconclass notation (P1256), e.g. "Annunciation" -> 73A5.
Paintings (P31 Q3305213) that depict (P180) or have as main subject (P921) such a subject inherit its
notation(s), so the existing taxonomy matcher works unchanged.

Passes, each cached under data/raw/wikidata/ (re-runs only fetch what is missing):
  1. paintings per subject batch   2. painting details   3. creator details
Output: data/sources/wikidata_paintings.jsonl.gz (one artwork per line, committed) and
        data/enrichment/wikidata_creators.tsv (creator geography, same columns as creator_geo.tsv).
De-duplication against ICARUS: RKDimages id (P350) and collections already harvested by ICARUS.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from etl.geo import Countries  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "data", "raw", "wikidata")
OUT_ART = os.path.join(ROOT, "data", "sources", "wikidata_paintings.jsonl.gz")
OUT_CRE = os.path.join(ROOT, "data", "enrichment", "wikidata_creators.tsv")
UA = "DaedalusThread/0.1 (https://github.com/Farechiga/daedalus-thread; batch harvest)"
PAINTING = "Q3305213"
# Collections that ICARUS already harvests (its own records would be double counted)
ICARUS_COLLECTIONS = {"Q190804": "Rijksmuseum", "Q303139": "Belvedere", "Q468458": "Städel Museum",
                      "Q214867": "National Gallery of Art", "Q1510467": "Hessen Kassel Heritage"}
ICARUS_COLLECTION_NAMES = {"rijksmuseum", "belvedere", "österreichische galerie belvedere", "städel museum",
                           "national gallery of art", "museumslandschaft hessen kassel", "hessen kassel heritage"}
LANGS = "en,de,nl,fr,it,es,pl"


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def sparql(query, tries=5):
    body = urllib.parse.urlencode({"query": query}).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request("https://query.wikidata.org/sparql", data=body, method="POST", headers={
                "Accept": "application/sparql-results+json", "User-Agent": UA,
                "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:
            wait = 6 * (attempt + 1)
            log(f"  SPARQL error ({str(e)[:80]}); retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError("SPARQL failed repeatedly")


def cached(kind, keys, query_fn):
    """Run query_fn(keys) once per distinct key batch; cache the raw bindings."""
    os.makedirs(os.path.join(RAW, kind), exist_ok=True)
    h = hashlib.sha1(" ".join(keys).encode()).hexdigest()[:16]
    path = os.path.join(RAW, kind, f"{h}.json")
    if os.path.exists(path):
        return json.load(open(path))
    rows = query_fn(keys)
    json.dump(rows, open(path, "w"))
    time.sleep(1.0)
    return rows


def qid(uri):
    return uri.rsplit("/", 1)[-1]


def subject_notations(ic):
    rows = json.load(open(os.path.join(RAW, "subjects_iconclass.json")))["results"]["bindings"]
    out = collections.defaultdict(set)
    for b in rows:
        code = b["ic"]["value"].strip()
        if ic.resolve(code) is not None:
            out[qid(b["s"]["value"])].add(code)
    return out


def curated_subjects(tax):
    """taxonomy/wikidata_subjects.json (reviewed proposals): subject QID -> the theme's first Iconclass notation."""
    path = os.path.join(ROOT, "taxonomy", "wikidata_subjects.json")
    out = collections.defaultdict(set)
    if os.path.exists(path):
        for nid, cands in json.load(open(path, encoding="utf-8")).items():
            if not nid.startswith("_") and nid in tax.nodes and Taxonomy.include(tax.nodes[nid]):
                for c in cands:
                    out[c["qid"]].add(Taxonomy.include(tax.nodes[nid])[0])
    return out


def cached_rows(kind, var):
    """All rows already cached for `kind`, grouped by the value of ?var (per-item reuse across batch layouts)."""
    out = collections.defaultdict(list)
    d = os.path.join(RAW, kind)
    if os.path.isdir(d):
        for name in os.listdir(d):
            for b in json.load(open(os.path.join(d, name))):
                if var in b:
                    out[qid(b[var]["value"])].append(b)
    return out


def harvest_paintings(subjects, batch=25, collection=None):
    """subject QID -> set(artwork QID): paintings by default, or any object held by `collection`."""
    found = collections.defaultdict(set)
    subs = sorted(subjects)
    kind = "paintings_by_subject" if not collection else f"objects_by_subject_{collection}"
    for i in range(0, len(subs), batch):
        chunk = subs[i:i + batch]

        def q(keys):
            values = " ".join(f"wd:{k}" for k in keys)
            scope = f"?w wdt:P31 wd:{PAINTING} ." if not collection else f"?w wdt:P195 wd:{collection} ."
            return sparql("SELECT ?s ?w WHERE { VALUES ?s { %s } %s { ?w wdt:P180 ?s } UNION { ?w wdt:P921 ?s } }"
                          % (values, scope))
        for b in cached(kind, chunk, q):
            found[qid(b["w"]["value"])].add(qid(b["s"]["value"]))
        if (i // batch) % 20 == 0:
            log(f"pass 1: {min(i + batch, len(subs))}/{len(subs)} subjects, {len(found)} paintings so far")
    return found


def painting_details(qids, batch=150):
    det = {}
    have = cached_rows("painting_details", "w")
    ids = sorted(q for q in qids if q not in have)
    log(f"pass 2: {len(qids) - len(ids)} paintings already cached, {len(ids)} to fetch")
    chunks = [ids[i:i + batch] for i in range(0, len(ids), batch)] + [["__cached__"]]
    for i, chunk in enumerate(chunks):

        def q(keys):
            values = " ".join(f"wd:{k}" for k in keys)
            return sparql(
                "SELECT ?w ?wLabel ?links ?creator ?time ?prec ?coll ?collLabel ?collCountry ?img ?rkd ?met ?clsLabel WHERE { VALUES ?w { %s } "
                "OPTIONAL { ?w wdt:P3634 ?met } OPTIONAL { ?w wdt:P31 ?cls } "
                "?w wikibase:sitelinks ?links . OPTIONAL { ?w wdt:P170 ?creator } "
                "OPTIONAL { ?w p:P571/psv:P571 [ wikibase:timeValue ?time ; wikibase:timePrecision ?prec ] } "
                "OPTIONAL { ?w wdt:P195 ?coll . OPTIONAL { ?coll wdt:P17 ?collCountry } } "
                "OPTIONAL { ?w wdt:P18 ?img } OPTIONAL { ?w wdt:P350 ?rkd } "
                "SERVICE wikibase:label { bd:serviceParam wikibase:language \"%s\". } }" % (values, LANGS))
        rows = [b for w in qids if w in have for b in have[w]] if chunk == ["__cached__"] else cached("painting_details", chunk, q)
        for b in rows:
            w = qid(b["w"]["value"])
            d = det.setdefault(w, {"qid": w, "title": None, "links": 0, "creators": [], "times": [], "collections": {},
                                   "image": None, "rkd": set(), "met": None, "classes": []})
            if "met" in b:
                d["met"] = d["met"] or b["met"]["value"]
            if b.get("clsLabel") and b["clsLabel"]["value"] not in d["classes"]:
                d["classes"].append(b["clsLabel"]["value"])
            d["title"] = d["title"] or b.get("wLabel", {}).get("value")
            d["links"] = int(b["links"]["value"])
            if "creator" in b and re.fullmatch(r"Q\d+", qid(b["creator"]["value"])) and qid(b["creator"]["value"]) not in d["creators"]:
                d["creators"].append(qid(b["creator"]["value"]))
            if "time" in b:
                t = (b["time"]["value"], int(b["prec"]["value"]))
                if t not in d["times"]:
                    d["times"].append(t)
            if "coll" in b:
                d["collections"][qid(b["coll"]["value"])] = (b.get("collLabel", {}).get("value"),
                                                              qid(b["collCountry"]["value"]) if "collCountry" in b else None)
            if "img" in b and not d["image"]:
                d["image"] = b["img"]["value"].replace("http://", "https://", 1)
            if "rkd" in b:
                d["rkd"].add(b["rkd"]["value"])
        if i % 40 == 0:
            log(f"pass 2: {min((i + 1) * batch, len(ids))}/{len(ids)} new paintings")
    return det


def creator_details(qids, batch=150):
    det = {}
    have = cached_rows("creator_details", "c")
    ids = sorted(q for q in qids if q not in have)
    chunks = [ids[i:i + batch] for i in range(0, len(ids), batch)] + [["__cached__"]]
    for i, chunk in enumerate(chunks):

        def q(keys):
            values = " ".join(f"wd:{k}" for k in keys)
            return sparql(
                "SELECT ?c ?cLabel ?links ?bp ?bpLabel ?coord ?birth ?death ?ulan ?human WHERE { VALUES ?c { %s } "
                "?c wikibase:sitelinks ?links . OPTIONAL { ?c wdt:P31 ?human . FILTER(?human = wd:Q5) } "
                "OPTIONAL { ?c wdt:P19 ?bp . OPTIONAL { ?bp wdt:P625 ?coord } } "
                "OPTIONAL { ?c wdt:P569 ?birth } OPTIONAL { ?c wdt:P570 ?death } OPTIONAL { ?c wdt:P245 ?ulan } "
                "SERVICE wikibase:label { bd:serviceParam wikibase:language \"%s\". } }" % (values, LANGS))
        rows = [b for c in qids if c in have for b in have[c]] if chunk == ["__cached__"] else cached("creator_details", chunk, q)
        for b in rows:
            c = qid(b["c"]["value"])
            d = det.setdefault(c, {"qid": c, "name": None, "links": 0, "place": None, "lon": None, "lat": None,
                                   "birth": None, "death": None, "ulan": None, "human": False})
            d["name"] = d["name"] or b.get("cLabel", {}).get("value")
            d["links"] = int(b["links"]["value"])
            d["human"] = d["human"] or "human" in b
            if "coord" in b and d["lon"] is None and b["coord"]["value"].startswith("Point("):
                d["lon"], d["lat"] = (float(x) for x in b["coord"]["value"][6:-1].split())
                d["place"] = b.get("bpLabel", {}).get("value")
            for k in ("birth", "death"):
                if k in b and d[k] is None:
                    m = re.match(r"^(-?\d+)-", b[k]["value"])
                    d[k] = int(m.group(1)) if m else None
            d["ulan"] = d["ulan"] or b.get("ulan", {}).get("value")
        if i % 20 == 0:
            log(f"pass 3: {min((i + 1) * batch, len(ids))}/{len(ids)} new creators")
    return det


def date_range(times):
    """Wikidata inception with precision -> (start, end, kind) without adding precision."""
    best = None
    for value, prec in times:
        m = re.match(r"^([+-]?\d+)-", value)
        if not m:
            continue
        y = int(m.group(1))
        if y < 100 or y > 2026:
            continue
        if prec >= 9:
            r = (y, y, "year")
        elif prec == 8:
            r = (y // 10 * 10, y // 10 * 10 + 9, "range")
        elif prec == 7:  # Wikidata stores e.g. 16th century as 1501-1600 (any year within): use its century
            c0 = (y - 1) // 100 * 100
            r = (c0, c0 + 99, "century")
        else:
            continue
        if best is None or (r[1] - r[0]) < (best[1] - best[0]):
            best = r
    return best


def date_text(rng):
    if not rng:
        return None
    a, b, kind = rng
    if kind == "century":
        n = a // 100 + 1
        return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')} century"
    if kind == "range":
        return f"{a}s"
    return str(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-subjects", type=int, default=0, help="limit subjects (testing)")
    ap.add_argument("--collection", help="harvest every object (any type) held by this collection QID instead of paintings, "
                                         "e.g. Q160236 = The Metropolitan Museum of Art")
    ap.add_argument("--dataset", default="wikidata", help="dataset name for --collection output (e.g. met)")
    args = ap.parse_args()
    out_art = OUT_ART if not args.collection else os.path.join(ROOT, "data", "sources", f"{args.dataset}_objects.jsonl.gz")
    out_cre = OUT_CRE if not args.collection else os.path.join(ROOT, "data", "enrichment", f"{args.dataset}_creators.tsv")
    ic = Iconclass()
    tax = Taxonomy(ic)
    notes = subject_notations(ic)
    # keep only subjects that reach at least one taxonomy theme
    useful = {s: codes for s, codes in notes.items() if any(tax.match([c])[0] for c in codes)}
    for s, codes in curated_subjects(tax).items():  # reviewed subjects for themes the Iconclass bridge misses
        useful.setdefault(s, set()).update(codes)
    subjects = sorted(useful)[: args.max_subjects or None]
    log(f"{len(notes)} Wikidata subjects with Iconclass; {len(useful)} reach a theme; harvesting {len(subjects)}")

    by_painting = harvest_paintings(subjects, collection=args.collection)
    if args.collection and os.path.exists(OUT_ART):  # already harvested as paintings: don't duplicate
        with gzip.open(OUT_ART, "rt", encoding="utf-8") as fh:
            have = {json.loads(line)["qid"] for line in fh}
        by_painting = {w: s for w, s in by_painting.items() if w not in have}
    log(f"pass 1 done: {len(by_painting)} paintings")
    det = painting_details(by_painting)

    db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'db', 'daedalus.sqlite')}?mode=ro", uri=True)
    icarus_rkd = {u.rsplit("/", 1)[-1] for (u,) in db.execute("SELECT source_url FROM artwork WHERE source_id = 'rkd'")}
    known_qids = {}
    for key, wq in db.execute("SELECT c.name_key, g.wikidata_qid FROM creator_geo g JOIN creator c ON c.id = g.creator_id "
                              "WHERE g.wikidata_qid IS NOT NULL AND g.match_status = 'matched'"):
        known_qids[wq] = key

    kept, dropped = [], collections.Counter()
    for w, d in det.items():
        if d["rkd"] & icarus_rkd:
            dropped["duplicate_rkd"] += 1
            continue
        labels = {(lab or "").casefold() for lab, _ in d["collections"].values()}
        if set(d["collections"]) & set(ICARUS_COLLECTIONS) or labels & ICARUS_COLLECTION_NAMES:
            dropped["collection_in_icarus"] += 1
            continue
        if args.collection and any(re.search(r"\bprint|photograph|negative|banknote|coin|postage", c, re.I) for c in d["classes"]):
            dropped["print_or_photo"] += 1
            continue
        kept.append(d)
    log(f"kept {len(kept)} paintings; dropped {dict(dropped)}")

    creators = creator_details({c for d in kept for c in d["creators"]})
    countries = Countries()

    from etl.normalize import ObjectTyper
    typer = ObjectTyper()
    os.makedirs(os.path.dirname(out_art), exist_ok=True)
    with gzip.open(out_art, "wt", encoding="utf-8") as fh:
        for d in sorted(kept, key=lambda d: d["qid"]):
            codes = sorted({c for s in by_painting[d["qid"]] for c in useful.get(s, ())})
            rng = date_range(d["times"])
            coll = next(iter(d["collections"].values()), (None, None))
            fh.write(json.dumps({
                "id": "wd-" + d["qid"], "qid": d["qid"], "title": d["title"] if d["title"] != d["qid"] else None,
                "links": d["links"], "creators": [{"qid": c, "name": creators.get(c, {}).get("name"),
                                                    "key": known_qids.get(c, "wd:" + c)} for c in d["creators"]],
                "date": rng, "date_text": date_text(rng),
                "holding": coll[0], "holding_country": coll[1], "image": d["image"],
                "subjects": sorted(by_painting[d["qid"]]), "iconclass": codes,
                **({"dataset": args.dataset, "source_id": args.dataset,
                    "source_url": f"https://www.metmuseum.org/art/collection/search/{d['met']}" if d.get("met") else None,
                    "object_type": typer.type_of(d["classes"], [], args.dataset) if d["classes"] else "other",
                    "instance_of": " | ".join(d["classes"]) or None} if args.collection else {}),
            }, ensure_ascii=False) + "\n")

    cols = ["name_key", "display_name", "n_artworks", "status", "match_method", "match_confidence", "ulan_id", "ulan_name",
            "ulan_birth", "ulan_death", "wikidata_qid", "country_code", "country_name", "proxy_type", "evidence_source",
            "geo_confidence", "birth_place", "birth_lat", "birth_lon", "nationality", "notes", "candidates", "links"]
    n_by_creator = collections.Counter(c for d in kept for c in d["creators"])
    if args.collection and os.path.exists(OUT_CRE):  # creators already attributed by the paintings harvest
        known_qids.update({r["wikidata_qid"]: r["name_key"] for r in csv.DictReader(open(OUT_CRE, encoding="utf-8"), delimiter="\t")})
    with open(out_cre, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh, delimiter="\t", lineterminator="\n")
        wr.writerow(cols)
        for c, d in sorted(creators.items()):
            if c in known_qids or not d["human"]:
                continue  # already attributed through ICARUS/ULAN, or not a person (e.g. 'anonymous')
            code = countries.locate(d["lon"], d["lat"]) if d["lon"] is not None else None
            wr.writerow(["wd:" + c, d["name"], n_by_creator[c], "matched", "wikidata_identifier", "high", d["ulan"], None,
                         d["birth"], d["death"], c, code, countries.info[code]["name"] if code else None,
                         "birthplace" if code else None, "wikidata" if code else None, "high" if code else None,
                         d["place"], d["lat"], d["lon"], None, None, None, d["links"]])
    size = os.path.getsize(out_art) / 1e6
    log(f"wrote {len(kept)} records ({size:.1f} MB) -> {out_art}; creators -> {out_cre}")


if __name__ == "__main__":
    main()
