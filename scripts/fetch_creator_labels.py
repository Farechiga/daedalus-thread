#!/usr/bin/env python3
"""English Wikidata labels for artists recorded under several spellings ('Raffael', 'Raphael', 'RAPHAEL Urbin').

    python3 scripts/fetch_creator_labels.py

build_db.py merges creators that share a Wikidata item and names the merged artist by this label.
Output: data/enrichment/creator_labels.tsv (wikidata_qid, label); responses cached in data/raw/wikidata/.
"""
import collections
import csv
import importlib.util
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
ENR = os.path.join(ROOT, "data", "enrichment")
FILES = ("creator_geo.tsv", "wikidata_creators.tsv", "met_creators.tsv", "aic_creators.tsv", "zeri_creators.tsv",
         "joconde_creators.tsv")
_spec = importlib.util.spec_from_file_location("wdh", os.path.join(os.path.dirname(__file__), "fetch_wikidata_artworks.py"))
wdh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wdh)


def main():
    keys = collections.defaultdict(set)
    for f in FILES:
        p = os.path.join(ENR, f)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
                if r.get("wikidata_qid"):
                    keys[r["wikidata_qid"]].add(r["name_key"])
    qids = sorted(q for q, k in keys.items() if len(k) > 1)
    labels = {}
    for i in range(0, len(qids), 300):
        rows = wdh.cached("creator_labels", qids[i:i + 300], lambda ks: wdh.sparql(
            "SELECT ?c ?l WHERE { VALUES ?c { %s } ?c rdfs:label ?l . FILTER(lang(?l) = 'en') }"
            % " ".join(f"wd:{k}" for k in ks)))
        labels.update({wdh.qid(b["c"]["value"]): b["l"]["value"] for b in rows})
    with open(os.path.join(ENR, "creator_labels.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["wikidata_qid", "label"])
        w.writerows(sorted(labels.items()))
    wdh.log(f"{len(labels)} labels for {len(qids)} artists with several spellings")


if __name__ == "__main__":
    main()
