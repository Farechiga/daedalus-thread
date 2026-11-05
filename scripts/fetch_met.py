#!/usr/bin/env python3
"""Harvest The Metropolitan Museum of Art (Open Access, CC0) via its public Collection API.

    python3 scripts/fetch_met.py [--max-terms N] [--workers 6]

The bulk CSV lives on GitHub LFS (blocked on some networks), so this uses the API instead:
  1. search the Met's subject tags for each Wikidata subject that carries an Iconclass notation
     (v1.1/search?tags=true, paginated), singular and plural label forms
  2. fetch each candidate object; keep it when one of its tags' Wikidata ids maps to Iconclass
  3. drop prints and photographs (the print-room bias this source is meant to counter) and objects
     already harvested from Wikidata (same Wikidata id)
  4. creators: Wikidata ids -> existing artists, or new ones looked up on Wikidata (birthplace etc.)
Output: data/sources/met_objects.jsonl.gz, data/enrichment/met_creators.tsv. Everything cached in data/raw/met/.
The Met asks for at most 80 requests/second; this stays near 10.
"""
import argparse
import collections
import concurrent.futures
import csv
import gzip
import importlib.util
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from etl.geo import Countries  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.normalize import ObjectTyper, classify  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402

_spec = importlib.util.spec_from_file_location("wdh", os.path.join(os.path.dirname(__file__), "fetch_wikidata_artworks.py"))
wdh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wdh)

RAW = os.path.join(ROOT, "data", "raw", "met")
API = "https://collectionapi.metmuseum.org/public/collection"
UA = "DaedalusThread/0.1 (https://github.com/Farechiga/daedalus-thread; batch harvest)"
OUT = os.path.join(ROOT, "data", "sources", "met_objects.jsonl.gz")
OUT_CRE = os.path.join(ROOT, "data", "enrichment", "met_creators.tsv")
SKIP_CLASSIFICATION = re.compile(r"\b(print|photograph|negative|ephemera)", re.I)
_rate = threading.Semaphore(1)
_last = [0.0]


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def get(url, tries=5):
    for attempt in range(tries):
        with _rate:  # global pacing: ~12 requests per second
            wait = _last[0] + 0.11 - time.time()  # ~9 requests/second overall
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"_missing": True}
            # 403 = the Met's bot protection: back right off before trying again
            time.sleep(60 if e.code in (403, 429) else 3 * (attempt + 1))
        except Exception:
            time.sleep(3 * (attempt + 1))
    return None


def search_ids(term):
    os.makedirs(os.path.join(RAW, "search"), exist_ok=True)
    path = os.path.join(RAW, "search", re.sub(r"[^\w-]+", "_", term.lower())[:80] + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    ids, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"tags": "true", "q": term, "limit": 500, "offset": offset})
        d = get(f"{API}/v1.1/search?{q}")
        if d is None:
            return []  # transient failure: not cached
        batch = d.get("objectIDs") or []
        ids += batch
        offset += len(batch)
        if not batch or offset >= (d.get("total") or 0) or offset >= 20000:
            break
    json.dump(ids, open(path, "w"))
    return ids


def fetch_object(oid):
    os.makedirs(os.path.join(RAW, "objects", str(oid % 100)), exist_ok=True)
    path = os.path.join(RAW, "objects", str(oid % 100), f"{oid}.json")
    if os.path.exists(path):
        return json.load(open(path))
    d = get(f"{API}/v1/objects/{oid}")
    if d is None:
        return None  # transient failure: not cached, retried on the next run
    json.dump(d, open(path, "w"))
    return None if d.get("_missing") else d


def wqid(url):
    m = re.search(r"(Q\d+)", url or "")
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-terms", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--departments", default="17,7,15,11,13,12",
                    help="Met department ids to enumerate in full (default: Medieval, Cloisters, Lehman, European Paintings, "
                         "Greek & Roman, European Sculpture & Decorative Arts); 'none' to use tag search only")
    ap.add_argument("--tag-search", action="store_true", help="also search tags for every mapped subject (slow)")
    args = ap.parse_args()
    ic = Iconclass()
    tax = Taxonomy(ic)
    notes = wdh.subject_notations(ic)
    useful = {s: codes for s, codes in notes.items() if any(tax.match([c])[0] for c in codes)}
    labels = {wdh.qid(b["s"]["value"]): b.get("sLabel", {}).get("value") for b in
              json.load(open(os.path.join(ROOT, "data", "raw", "wikidata", "subjects_iconclass.json")))["results"]["bindings"]}
    terms = set()
    for s in useful:
        lab = labels.get(s)
        if lab and not re.fullmatch(r"Q\d+", lab) and len(lab) <= 60:
            terms.add(lab)
            if not lab.endswith("s"):
                terms.add(lab + "s")
    terms = sorted(terms)[: args.max_terms or None]
    log(f"{len(useful)} Iconclass subjects reach a theme -> {len(terms)} Met tag search terms")

    candidates = set()
    if args.departments != "none":
        for dep in args.departments.split(","):
            path = os.path.join(RAW, f"department_{dep}.json")
            if not os.path.exists(path):
                d = get(f"{API}/v1/objects?departmentIds={dep}")
                if d is None:
                    sys.exit(f"could not list department {dep} (Met API unavailable or blocking); try again later")
                json.dump(d.get("objectIDs") or [], open(path, "w"))
            ids = json.load(open(path))
            candidates.update(ids)
            log(f"department {dep}: {len(ids)} objects")
    if args.tag_search:
        with concurrent.futures.ThreadPoolExecutor(args.workers) as ex:
            for i, ids in enumerate(ex.map(search_ids, terms)):
                candidates.update(ids)
                if i % 200 == 0:
                    log(f"search: {i + 1}/{len(terms)} terms, {len(candidates)} candidate objects")
    log(f"{len(candidates)} candidate objects")

    objs = {}
    with concurrent.futures.ThreadPoolExecutor(args.workers) as ex:
        for i, d in enumerate(ex.map(fetch_object, sorted(candidates))):
            if d and d.get("objectID"):
                objs[d["objectID"]] = d
            if i % 5000 == 0:
                log(f"objects: {i + 1}/{len(candidates)}")
    log(f"{len(objs)} objects fetched")

    # de-duplicate against the Wikidata harvest and ICARUS-linked creators
    wd_ids = set()
    wd_path = os.path.join(ROOT, "data", "sources", "wikidata_paintings.jsonl.gz")
    if os.path.exists(wd_path):
        with gzip.open(wd_path, "rt", encoding="utf-8") as fh:
            wd_ids = {json.loads(line)["qid"] for line in fh}
    db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'db', 'daedalus.sqlite')}?mode=ro", uri=True)
    known_qids = {wq: key for key, wq in db.execute(
        "SELECT c.name_key, g.wikidata_qid FROM creator_geo g JOIN creator c ON c.id = g.creator_id "
        "WHERE g.wikidata_qid IS NOT NULL AND g.match_status = 'matched'")}
    wd_cre_path = os.path.join(ROOT, "data", "enrichment", "wikidata_creators.tsv")
    if os.path.exists(wd_cre_path):
        for r in csv.DictReader(open(wd_cre_path, encoding="utf-8"), delimiter="\t"):
            known_qids.setdefault(r["wikidata_qid"], r["name_key"])

    typer = ObjectTyper()
    kept, dropped = [], collections.Counter()
    for oid, d in sorted(objs.items()):
        if SKIP_CLASSIFICATION.search(d.get("classification") or "") or SKIP_CLASSIFICATION.search(d.get("objectName") or ""):
            dropped["print_or_photo"] += 1
            continue
        if wqid(d.get("objectWikidata_URL")) in wd_ids:
            dropped["already_in_wikidata_harvest"] += 1
            continue
        subjects = sorted({wqid(t.get("Wikidata_URL")) for t in d.get("tags") or [] if wqid(t.get("Wikidata_URL")) in useful})
        codes = sorted({c for s in subjects for c in useful[s]})
        if not codes:
            dropped["no_mapped_subject"] += 1
            continue
        kept.append((d, subjects, codes))
    log(f"kept {len(kept)}; dropped {dict(dropped)}")

    new_creator_qids = {wqid(d.get("artistWikidata_URL")) for d, _, _ in kept} - set(known_qids) - {None}
    creators = wdh.creator_details(new_creator_qids) if new_creator_qids else {}
    countries = Countries()

    def creator_key(d):
        q = wqid(d.get("artistWikidata_URL"))
        if q:
            return q, known_qids.get(q, "wd:" + q)
        name = (d.get("artistDisplayName") or "").strip()
        return None, (classify(name)["name_key"] if name else None)

    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for d, subjects, codes in kept:
            b, e = d.get("objectBeginDate"), d.get("objectEndDate")
            date = None
            if isinstance(b, int) and isinstance(e, int) and 100 <= b <= e <= 2026:
                date = [b, e, "year" if b == e else "range"]
            q, key = creator_key(d)
            name = (d.get("artistDisplayName") or "").strip()
            cre = [{"qid": q, "name": name or (creators.get(q) or {}).get("name"), "key": key}] if key and (name or q) else []
            fh.write(json.dumps({
                "id": f"met-{d['objectID']}", "dataset": "met", "source_id": "met", "source_url": d.get("objectURL"),
                "qid": wqid(d.get("objectWikidata_URL")), "title": d.get("title") or None, "links": None,
                "highlight": bool(d.get("isHighlight")), "creators": cre, "date": date,
                "date_text": d.get("objectDate") or None, "approx": bool(re.search(r"\bca\.|\bc\.|circa", d.get("objectDate") or "", re.I)),
                "holding": "The Metropolitan Museum of Art", "department": d.get("department"),
                "object_type": typer.type_of([d.get("classification") or "", d.get("objectName") or ""], [d.get("medium") or ""], "met"),
                "instance_of": " | ".join(x for x in (d.get("objectName"), d.get("classification")) if x) or None,
                "image": d.get("primaryImageSmall") or None, "culture": d.get("culture") or None,
                "subjects": subjects, "iconclass": codes,
            }, ensure_ascii=False) + "\n")

    cols = ["name_key", "display_name", "n_artworks", "status", "match_method", "match_confidence", "ulan_id", "ulan_name",
            "ulan_birth", "ulan_death", "wikidata_qid", "country_code", "country_name", "proxy_type", "evidence_source",
            "geo_confidence", "birth_place", "birth_lat", "birth_lon", "nationality", "notes", "candidates", "links"]
    n_by = collections.Counter(wqid(d.get("artistWikidata_URL")) for d, _, _ in kept)
    with open(OUT_CRE, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh, delimiter="\t", lineterminator="\n")
        wr.writerow(cols)
        for c, d in sorted(creators.items()):
            if not d["human"]:
                continue
            code = countries.locate(d["lon"], d["lat"]) if d["lon"] is not None else None
            wr.writerow(["wd:" + c, d["name"], n_by[c], "matched", "wikidata_identifier", "high", d["ulan"], None,
                         d["birth"], d["death"], c, code, countries.info[code]["name"] if code else None,
                         "birthplace" if code else None, "wikidata" if code else None, "high" if code else None,
                         d["place"], d["lat"], d["lon"], None, None, None, d["links"]])
    log(f"wrote {len(kept)} Met objects -> {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB); {len(creators)} new creators")


if __name__ == "__main__":
    main()
