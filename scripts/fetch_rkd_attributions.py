#!/usr/bin/env python3
"""Attribution qualifiers for ICARUS's RKDimages records, from the RKD Knowledge Graph (SPARQL, open data).

    python3 scripts/fetch_rkd_attributions.py

ICARUS keeps only the artist's name of an RKD record ('Rembrandt') and drops RKD's qualifier ('school of',
'after', 'attributed to'). The RKD graph models each attribution as a CIDOC-CRM attribute assignment on the
production: its type (a narrower term of thesaurus 96686, 'attribution qualifier') and the artist it names.
RKD artist ids map to Wikidata through P650, so a qualifier lands on the right creator of a multi-artist record
(an engraving by X 'after Rubens' discounts Rubens, not X).
Output: data/enrichment/rkd_attributions.tsv (image_id, rkd_artist, artist_label, wikidata_qid, qualifier);
responses cached in data/raw/rkd/.
"""
import csv
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
EP = "https://api.rkd.triply.cc/datasets/rkd/RKD-Knowledge-Graph/services/SPARQL/sparql"
UA = "DaedalusThread/0.1 (https://github.com/Farechiga/daedalus-thread; batch enrichment)"
CACHE = os.path.join(ROOT, "data", "raw", "rkd")
OUT = os.path.join(ROOT, "data", "enrichment", "rkd_attributions.tsv")
DB = os.path.join(ROOT, "data", "db", "daedalus.sqlite")

_spec = importlib.util.spec_from_file_location("wdh", os.path.join(os.path.dirname(__file__), "fetch_wikidata_artworks.py"))
wdh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wdh)

QUERY = """PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?img ?x ?artist ?alabel ?ql WHERE {
  VALUES ?img { %s }
  ?img crm:P108i_was_produced_by/crm:P141i_was_assigned_by/rdf:rest*/rdf:first ?x .
  OPTIONAL { ?x crm:P141_assigned/crm:P14_carried_out_by ?artist . OPTIONAL { ?artist rdfs:label ?alabel } }
  OPTIONAL { ?x crm:P2_has_type ?q . ?q skos:broader+ <https://data.rkd.nl/thesaurus/96686> ; skos:prefLabel ?ql . FILTER(lang(?ql) = "en") }
}"""


def sparql(ids):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(" ".join(ids).encode()).hexdigest()[:16] + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    q = QUERY % " ".join(f"<https://data.rkd.nl/images/{i}>" for i in ids)
    for attempt in range(5):
        try:
            req = urllib.request.Request(EP, data=urllib.parse.urlencode({"query": q}).encode(),
                                         headers={"Accept": "application/sparql-results+json", "User-Agent": UA})
            rows = json.load(urllib.request.urlopen(req, timeout=180))["results"]["bindings"]
            json.dump(rows, open(path, "w"))
            time.sleep(0.5)
            return rows
        except Exception as e:
            wdh.log(f"  RKD error ({str(e)[:60]}); retry")
            time.sleep(10 * (attempt + 1))
    sys.exit("RKD SPARQL failed; re-run to resume")


def main():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ids = sorted({u.rsplit("/", 1)[1] for (u,) in db.execute(
        "SELECT source_url FROM artwork WHERE source_id = 'rkd' AND source_url LIKE '%/images/%'")})
    wdh.log(f"{len(ids)} RKD image records in ICARUS")
    found = {}
    for i in range(0, len(ids), 250):
        for b in sparql(ids[i:i + 250]):
            img = b["img"]["value"].rsplit("/", 1)[1]
            key = (img, b["x"]["value"])
            rec = found.setdefault(key, {"artist": None, "label": None, "quals": set()})
            if "artist" in b:
                rec["artist"] = b["artist"]["value"].rsplit("/", 1)[1]
                rec["label"] = rec["label"] or b.get("alabel", {}).get("value")
            if "ql" in b:
                rec["quals"].add(b["ql"]["value"])
        if i // 250 % 20 == 0:
            wdh.log(f"  {min(i + 250, len(ids))}/{len(ids)}")
    artists = sorted({r["artist"] for r in found.values() if r["artist"]})
    qid = {}
    for i in range(0, len(artists), 300):  # RKDartists id -> Wikidata (P650)
        chunk = artists[i:i + 300]
        rows = wdh.cached("rkd_artists", chunk, lambda keys: wdh.sparql(
            "SELECT ?id ?c WHERE { VALUES ?id { %s } ?c wdt:P650 ?id }" % " ".join(f'"{k}"' for k in keys)))
        qid.update({b["id"]["value"]: wdh.qid(b["c"]["value"]) for b in rows})
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["image_id", "rkd_artist", "artist_label", "wikidata_qid", "qualifier"])
        n_q = 0
        for (img, _), r in sorted(found.items()):
            qual = "|".join(sorted(r["quals"])) or None
            n_q += bool(qual)
            w.writerow([img, r["artist"], r["label"], qid.get(r["artist"]) if r["artist"] else None, qual])
    wdh.log(f"{len(found)} attributions for {len({k[0] for k in found})} records; {n_q} qualified; "
            f"{len(qid)} of {len(artists)} RKD artists on Wikidata -> {OUT}")


if __name__ == "__main__":
    main()
