#!/usr/bin/env python3
"""Fame signals from Wikidata (cached): Wikipedia sitelinks for artists and for individual works.

    python3 scripts/fetch_fame.py

- artists: every Wikidata id linked to an ICARUS/Wikidata/Met creator -> number of Wikipedia editions
- works:   ICARUS records Wikidata knows by identifier -> that item's sitelinks
           (RKDimages id P350 for RKD records; Rijksmuseum inventory number P217 for Rijksmuseum records)
Output: data/enrichment/fame_creators.tsv, data/enrichment/fame_works.tsv
"""
import csv
import importlib.util
import os
import re
import sqlite3
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
_spec = importlib.util.spec_from_file_location("wdh", os.path.join(os.path.dirname(__file__), "fetch_wikidata_artworks.py"))
wdh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wdh)
ENR = os.path.join(ROOT, "data", "enrichment")


def creator_links(qids, batch=300):
    out = {}
    ids = sorted(qids)
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        rows = wdh.cached("creator_links", chunk, lambda keys: wdh.sparql(
            "SELECT ?c ?links WHERE { VALUES ?c { %s } ?c wikibase:sitelinks ?links }" % " ".join(f"wd:{k}" for k in keys)))
        for b in rows:
            out[wdh.qid(b["c"]["value"])] = int(b["links"]["value"])
        if (i // batch) % 10 == 0:
            wdh.log(f"artist sitelinks: {min(i + batch, len(ids))}/{len(ids)}")
    return out


# Wikidata occupations (P106) that make a creator's fame count for the artwork. Patrons, authors, rulers and
# publishers credited as "creators" (Napoleon, Goethe, Homer) are excluded so their fame doesn't lift illustrations.
ARTIST_OCCUPATIONS = {  # labels verified against Wikidata
    "Q1028181",   # painter
    "Q10862983",  # etcher
    "Q1114448",   # cartoonist
    "Q11569986",  # printmaker
    "Q1281618",   # sculptor
    "Q15296811",  # draftsperson
    "Q16947657",  # lithographer
    "Q18074503",  # installation artist
    "Q1925963",   # graphic artist
    "Q211423",    # goldsmith
    "Q21550489",  # conceptual artist
    "Q2519376",   # jewelry designer
    "Q329439",    # engraver
    "Q33231",     # photographer
    "Q3391743",   # visual artist
    "Q42973",     # architect
    "Q483501",    # artist
    "Q627325",    # graphic designer
    "Q644687",    # illustrator
    "Q7541856",   # ceramicist
    "Q2133309",   # interior designer
}


def visual_artists(qids, batch=300):
    out = set()
    ids = sorted(qids)
    occ = " ".join(f"wd:{o}" for o in sorted(ARTIST_OCCUPATIONS))
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        rows = wdh.cached("creator_artist_v2", chunk, lambda keys: wdh.sparql(
            "SELECT DISTINCT ?c WHERE { VALUES ?c { %s } VALUES ?o { %s } ?c wdt:P106 ?o }"
            % (" ".join(f"wd:{k}" for k in keys), occ)))
        out |= {wdh.qid(b["c"]["value"]) for b in rows}
    wdh.log(f"{len(out)} of {len(ids)} creators have a visual-art occupation")
    return out


def main():
    qids = set()
    for f in ("creator_geo.tsv", "wikidata_creators.tsv", "met_creators.tsv"):
        p = os.path.join(ENR, f)
        if os.path.exists(p):
            qids |= {r["wikidata_qid"] for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t") if r.get("wikidata_qid")}
    ids = {q for q in qids if re.fullmatch(r"Q\d+", q)}
    links = creator_links(ids)
    artist = visual_artists(ids)
    with open(os.path.join(ENR, "fame_creators.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["wikidata_qid", "sitelinks", "visual_artist"])
        for q, n in sorted(links.items()):
            w.writerow([q, n, int(q in artist)])
    wdh.log(f"{len(links)} artists with sitelinks")

    # works: RKD (P350) and Rijksmuseum (P217 within collection Q190804) items that have any Wikipedia article
    rkd = wdh.cached("fame_rkd", ["all"], lambda _: wdh.sparql(
        "SELECT ?id ?links WHERE { ?w wdt:P350 ?id ; wikibase:sitelinks ?links . FILTER(?links > 0) }"))
    rijks = wdh.cached("fame_rijks", ["all"], lambda _: wdh.sparql(
        "SELECT ?id ?links WHERE { ?w wdt:P195 wd:Q190804 ; wdt:P217 ?id ; wikibase:sitelinks ?links . FILTER(?links > 0) }"))
    by_rkd = {b["id"]["value"]: int(b["links"]["value"]) for b in rkd}
    by_rijks = {b["id"]["value"].upper(): int(b["links"]["value"]) for b in rijks}
    db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'db', 'daedalus.sqlite')}?mode=ro", uri=True)
    hits = []
    for aid, sid, url in db.execute("SELECT id, source_id, source_url FROM artwork WHERE source_id IN ('rkd', 'rijksmuseum')"):
        key = url.rstrip("/").rsplit("/", 1)[-1]
        n = by_rkd.get(key) if sid == "rkd" else by_rijks.get(key.upper())
        if n:
            hits.append((aid, n))
    with open(os.path.join(ENR, "fame_works.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["artwork_id", "sitelinks"])
        w.writerows(sorted(hits))
    wdh.log(f"{len(by_rkd)} RKD and {len(by_rijks)} Rijksmuseum Wikidata items with articles -> {len(hits)} ICARUS works")


if __name__ == "__main__":
    main()
