#!/usr/bin/env python3
"""Propose Wikidata subject items for taxonomy themes the Iconclass bridge misses or covers thinly.

    python3 scripts/find_wikidata_subjects.py [--themes id,id,...]

For each theme: search Wikidata (wbsearchentities) for its label and first aliases, count how many items
use each candidate as "depicts" (P180), and keep real subjects (not paintings, films, names) with enough use.
Output: taxonomy/wikidata_subjects.json  {theme_id: [{qid, label, description, depicts}]}  for review.
The harvester maps a painting depicting one of these QIDs to the theme's first Iconclass notation.
"""
import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from etl.iconclass import Iconclass  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402

_spec = importlib.util.spec_from_file_location("wdh", os.path.join(os.path.dirname(__file__), "fetch_wikidata_artworks.py"))
wdh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wdh)
OUT = os.path.join(ROOT, "taxonomy", "wikidata_subjects.json")
CACHE = os.path.join(ROOT, "data", "raw", "wikidata", "search")
NOT_A_SUBJECT = re.compile(r"\b(painting|drawing|print|engraving|fresco|sculpture|statue|film|album|song|novel|opera|"
                           r"family name|given name|surname|disambiguation|television|band|video game|ship|asteroid|"
                           r"village|commune|municipality|human settlement|street|church in|company|newspaper|journal|"
                           r"poem|play by|book by|episode|series|genus of|species of)\b", re.I)
MIN_DEPICTS = 15


def search(term):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, re.sub(r"[^\w-]+", "_", term.lower())[:90] + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    q = urllib.parse.urlencode({"action": "wbsearchentities", "search": term, "language": "en", "type": "item",
                                "limit": 8, "format": "json"})
    req = urllib.request.Request(f"https://www.wikidata.org/w/api.php?{q}", headers={"User-Agent": wdh.UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r).get("search", [])
            break
        except Exception:
            time.sleep(4 * (attempt + 1))
    else:
        res = []
    json.dump(res, open(path, "w"))
    time.sleep(0.3)
    return res


def depicts_counts(qids):
    """One COUNT per subject: the query service currently returns no rows for multi-value VALUES + GROUP BY."""
    import concurrent.futures

    def one(q):
        # a capped sample is enough: we need ">= MIN_DEPICTS" and a rough rank (full COUNTs on common subjects are slow)
        return q, len(wdh.cached("depicts_upto400", [q], lambda keys: wdh.sparql(
            "SELECT ?w WHERE { ?w wdt:P180 wd:%s } LIMIT 400" % keys[0])))
    out = {}
    with concurrent.futures.ThreadPoolExecutor(4) as ex:  # Wikidata allows a few parallel queries per client
        for i, (q, n) in enumerate(ex.map(one, sorted(qids))):
            out[q] = n
            if i % 100 == 0:
                wdh.log(f"depicts counts: {i}/{len(qids)}")
    return out


def theme_terms(node):
    label = re.sub(r"^(The|Saint)\s+", "", node["label"])
    terms = [node["label"], label] + [a for a in node.get("aliases", [])[:4] if re.fullmatch(r"[A-Za-z' .-]+", a)]
    # split "X & Y" / "X and Y" themes into their parts too (e.g. "Storks, Herons & Cranes")
    for part in re.split(r"\s*(?:,|&| and )\s*", label):
        if len(part) > 2:
            terms.append(part)
    return list(dict.fromkeys(t.strip() for t in terms if t.strip()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--themes", help="comma-separated theme ids (default: gaps + thin from the current database)")
    args = ap.parse_args()
    tax = Taxonomy(Iconclass())
    if args.themes:
        themes = args.themes.split(",")
    else:
        db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'db', 'daedalus.sqlite')}?mode=ro", uri=True)
        extra = dict(db.execute("SELECT an.node_id, count(*) FROM artwork_node an JOIN artwork a ON a.rid = an.artwork_rid "
                                "WHERE a.dataset <> 'icarus' GROUP BY 1"))
        themes = [n for n in tax.order if tax.depth[n] > 0 and not tax.children[n] and extra.get(n, 0) < 30]
    cands = {}
    for nid in themes:
        for term in theme_terms(tax.nodes[nid]):
            for r in search(term):
                desc = r.get("description", "")
                if NOT_A_SUBJECT.search(desc):
                    continue
                cands.setdefault(nid, {})[r["id"]] = {"qid": r["id"], "label": r.get("label"), "description": desc, "term": term}
    counts = depicts_counts({q for c in cands.values() for q in c})
    out = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for nid in themes:
        keep = [dict(c, depicts=counts.get(q, 0)) for q, c in cands.get(nid, {}).items() if counts.get(q, 0) >= MIN_DEPICTS]
        keep.sort(key=lambda c: -c["depicts"])
        if keep:
            out[nid] = keep[:4]
    json.dump(out, open(OUT, "w"), indent=1, ensure_ascii=False)
    wdh.log(f"{len(out)} themes with proposed Wikidata subjects -> {OUT}")
    for nid in themes:
        print(f"  {nid:28}", "; ".join(f"{c['label']} ({c['qid']}, {c['depicts']})" for c in out.get(nid, [])) or "-")


if __name__ == "__main__":
    main()
