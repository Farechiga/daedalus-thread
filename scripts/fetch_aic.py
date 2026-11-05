#!/usr/bin/env python3
"""Harvest the Art Institute of Chicago (CC0 data) via its public API.

    python3 scripts/fetch_aic.py

1. list every artwork (100 per page, the API allows 60 requests/minute) with subject terms, type, dates
2. map AIC subject terms to taxonomy themes: theme labels and aliases, plus English labels of Wikidata subjects
   that carry an Iconclass notation (so "Virgin Mary", "angels", "Saint George" become Iconclass codes)
3. drop prints and photographs, and artworks already harvested from Wikidata (P4610 = AIC artwork id)
4. artists: AIC agents carry Wikidata and ULAN ids -> existing artists, or new ones looked up on Wikidata
Output: data/sources/aic_objects.jsonl.gz, data/enrichment/aic_creators.tsv (cached in data/raw/aic/).
"""
import collections
import csv
import gzip
import importlib.util
import json
import os
import re
import sys
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

RAW = os.path.join(ROOT, "data", "raw", "aic")
API = "https://api.artic.edu/api/v1"
UA = "DaedalusThread/0.1 (https://github.com/Farechiga/daedalus-thread; batch harvest)"
OUT = os.path.join(ROOT, "data", "sources", "aic_objects.jsonl.gz")
OUT_CRE = os.path.join(ROOT, "data", "enrichment", "aic_creators.tsv")
FIELDS = ("id,title,artist_id,artist_ids,artist_title,date_start,date_end,date_display,place_of_origin,artwork_type_title,"
          "classification_titles,subject_titles,image_id,is_public_domain,department_title,medium_display,is_boosted")
SKIP_TYPE = re.compile(r"\b(print|photograph|film|video|book|archit)", re.I)
# AIC subject words that match a theme name but mean something generic (reviewed 2026-11-05): a ring tagged "healing"
# is not a Miracle of Christ, a landscape tagged "winter" is not a personified Season, "water" is not the Element.
STOP_TERMS = {"religion", "water", "fire", "earth", "air", "death", "europe", "africa", "asia", "america", "americas",
              "victory", "logo", "power", "winter", "summer", "autumn", "spring", "fall", "healing", "love", "time",
              "light", "night", "day", "christianity", "religious figures", "religious scenes", "christian subjects"}


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def get(url, tries=6):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "AIC-User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                remaining = int(r.headers.get("x-ratelimit-remaining", "60"))
                data = json.load(r)
            time.sleep(1.05 if remaining > 5 else 15)
            return data
        except Exception as e:
            log(f"  AIC error ({str(e)[:60]}); retry")
            time.sleep(20 * (attempt + 1))
    return None


def list_artworks():
    os.makedirs(os.path.join(RAW, "pages"), exist_ok=True)
    page, out = 1, []
    while True:
        path = os.path.join(RAW, "pages", f"{page:05d}.json")
        if os.path.exists(path):
            d = json.load(open(path))
        else:
            d = get(f"{API}/artworks?page={page}&limit=100&fields={FIELDS}")
            if d is None:
                sys.exit(f"AIC page {page} failed; re-run to resume")
            json.dump(d, open(path, "w"))
        out += d["data"]
        if page % 100 == 0:
            log(f"pages: {page}/{d['pagination']['total_pages']}")
        if page >= d["pagination"]["total_pages"]:
            return out
        page += 1


def agents(ids):
    os.makedirs(os.path.join(RAW, "agents"), exist_ok=True)
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        path = os.path.join(RAW, "agents", f"{chunk[0]}_{len(chunk)}.json")
        if os.path.exists(path):
            d = json.load(open(path))
        else:
            q = urllib.parse.urlencode({"ids": ",".join(map(str, chunk)), "limit": 100,
                                        "fields": "id,title,birth_date,death_date,ulan_id,wikidata_id,is_artist"})
            d = get(f"{API}/agents?{q}") or {"data": []}
            json.dump(d, open(path, "w"))
        for a in d["data"]:
            out[a["id"]] = a
    return out


def norm(term):
    t = re.sub(r"[^\w\s'-]", " ", term.casefold()).strip()
    t = re.sub(r"^(saint|st)\s+", "saint ", t)
    return " ".join(t.split())


def term_map(tax, ic):
    """normalised subject term -> set of Iconclass codes."""
    m = collections.defaultdict(set)

    def add(term, codes):
        for t in {norm(term), norm(term).rstrip("s")}:
            if len(t) > 2:
                m[t] |= set(codes)
    for nid in tax.order:
        node = tax.nodes[nid]
        inc = Taxonomy.include(node)
        if tax.depth[nid] == 0 or not inc or node.get("children"):
            continue  # leaf themes only: group names like "Saints" are too broad to stand for a code
        add(re.sub(r"^The\s+", "", node["label"]), inc[:1])
        for a in node.get("aliases", []):
            add(a, inc[:1])
    labels = json.load(open(os.path.join(ROOT, "data", "raw", "wikidata", "subjects_iconclass.json")))["results"]["bindings"]
    for b in labels:
        lab = b.get("sLabel", {}).get("value")
        code = b["ic"]["value"].strip()
        if lab and not re.fullmatch(r"Q\d+", lab) and ic.resolve(code) and tax.match([code])[0]:
            add(lab, [code])
    return m


def main():
    ic = Iconclass()
    tax = Taxonomy(ic)
    tmap = term_map(tax, ic)
    log(f"{len(tmap)} subject terms map to Iconclass")
    works = list_artworks()
    log(f"{len(works)} AIC artworks listed")

    rows = wdh.cached("aic_ids", ["all"], lambda _: wdh.sparql("SELECT ?w ?id WHERE { ?w wdt:P4610 ?id }"))
    aic_to_qid = {b["id"]["value"]: wdh.qid(b["w"]["value"]) for b in rows}
    have = set()
    for f in ("wikidata_paintings.jsonl.gz", "met_objects.jsonl.gz"):
        p = os.path.join(ROOT, "data", "sources", f)
        if os.path.exists(p):
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                have |= {json.loads(line)["qid"] for line in fh}

    kept, dropped = [], collections.Counter()
    for w in works:
        if SKIP_TYPE.search(w.get("artwork_type_title") or ""):
            dropped["print_photo_film_book"] += 1
            continue
        if aic_to_qid.get(str(w["id"])) in have:
            dropped["already_in_wikidata_harvest"] += 1
            continue
        codes = sorted({c for t in (w.get("subject_titles") or []) if norm(t) not in STOP_TERMS for c in tmap.get(norm(t), ())})
        if not codes:
            dropped["no_mapped_subject"] += 1
            continue
        kept.append((w, codes))
    log(f"kept {len(kept)}; dropped {dict(dropped)}")

    ag = agents({a for w, _ in kept for a in (w.get("artist_ids") or [])})
    known = {}
    for f in ("creator_geo.tsv", "wikidata_creators.tsv", "met_creators.tsv"):
        p = os.path.join(ROOT, "data", "enrichment", f)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
                if r.get("wikidata_qid"):
                    known.setdefault(r["wikidata_qid"], r["name_key"])
                if r.get("ulan_id") and r.get("status") == "matched":
                    known.setdefault("ulan:" + r["ulan_id"], r["name_key"])
    new_q = {a["wikidata_id"] for a in ag.values() if a.get("wikidata_id") and a["wikidata_id"] not in known}
    creators = wdh.creator_details(new_q) if new_q else {}
    log(f"{len(ag)} AIC agents; {len(new_q)} new Wikidata artists")

    typer = ObjectTyper()
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for w, codes in kept:
            cre = []
            for aid in (w.get("artist_ids") or [])[:4]:
                a = ag.get(aid) or {}
                if not a or a.get("is_artist") is False:
                    continue
                q = a.get("wikidata_id")
                key = known.get(q) or known.get(f"ulan:{a.get('ulan_id')}") or (f"wd:{q}" if q else None)
                if not key and a.get("title"):
                    key = classify(a["title"])["name_key"]
                if key:
                    cre.append({"qid": q, "name": a.get("title"), "key": key})
            b, e = w.get("date_start"), w.get("date_end")
            date = [b, e, "year" if b == e else "range"] if isinstance(b, int) and isinstance(e, int) and 100 <= b <= e <= 2026 else None
            image = (f"https://www.artic.edu/iiif/2/{w['image_id']}/full/640,/0/default.jpg"
                     if w.get("image_id") and w.get("is_public_domain") else None)
            fh.write(json.dumps({
                "id": f"aic-{w['id']}", "dataset": "aic", "source_id": "aic", "source_url": f"https://www.artic.edu/artworks/{w['id']}",
                "qid": aic_to_qid.get(str(w["id"])), "title": w.get("title"), "links": None, "highlight": bool(w.get("is_boosted")),
                "creators": cre, "date": date, "date_text": w.get("date_display"),
                "approx": bool(re.search(r"\bc\.|circa", w.get("date_display") or "", re.I)),
                "holding": "Art Institute of Chicago", "department": w.get("department_title"),
                "object_type": typer.type_of([w.get("artwork_type_title") or ""] + (w.get("classification_titles") or []),
                                             [w.get("medium_display") or ""], "aic"),
                "instance_of": w.get("artwork_type_title"), "image": image, "culture": w.get("place_of_origin"),
                "subjects": w.get("subject_titles"), "iconclass": codes,
            }, ensure_ascii=False) + "\n")

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
    log(f"wrote {len(kept)} AIC records -> {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
