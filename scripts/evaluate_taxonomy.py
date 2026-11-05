#!/usr/bin/env python3
"""Validate taxonomy/segments.json against Iconclass and measure every node on ICARUS.

For each node: unique artworks, the coverage of the fields each chart needs (named creator,
parsed date, single-century date, image), source diversity, and a size verdict.
    python3 scripts/evaluate_taxonomy.py [taxonomy/segments.json]
Writes data/profile/taxonomy_eval.json and data/profile/taxonomy_eval.tsv.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from etl.dates import century_of, parse_time  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.icarus import iter_records, source_of  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data", "raw", "icarus", "data.jsonl")
OUT = os.path.join(ROOT, "data", "profile")
ANON = re.compile(r"\b(anonym\w*|unbekannt\w*|unknown|onbekend\w*|anoniem|nieokreślony|nieznany|anonim\w*|ignoto)", re.I)

SIZE_OK, SIZE_SMALL = 300, 100


def main():
    tax_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "taxonomy", "segments.json")
    tax_obj = Taxonomy(Iconclass(), tax_path)
    tax = tax_obj.raw
    nodes, parent_of, depth_of, segment_of = tax_obj.nodes, tax_obj.parent, tax_obj.depth, tax_obj.segment
    order, problems, children = tax_obj.order, tax_obj.problems, tax_obj.children

    stats = {nid: collections.Counter() for nid in nodes}
    centuries = {nid: collections.Counter() for nid in nodes}
    sources = {nid: collections.Counter() for nid in nodes}
    creators = {nid: set() for nid in nodes}
    seg_pairs = collections.Counter()
    n = 0

    for rec in iter_records(DATA):
        n += 1
        own_hits, matched, ann_hits = tax_obj.match(rec["iconclass_processed"])
        if not own_hits:
            continue
        for h in own_hits:  # "Other <node>": matched by the node's own include but by none of its children
            if tax_obj.is_other(h, own_hits, matched):
                stats[h]["other"] += 1

        named = [c for c in rec["creator"] if not ANON.search(c)]
        parsed = None
        for t in rec["time"]:
            p = parse_time(t)
            if p and p["kind"] != "unparsed":
                parsed = p
                break
        cent = century_of(parsed)
        sid = source_of(rec["url"])[0]
        for nid in matched:
            s = stats[nid]
            s["records"] += 1
            s["annotations"] += ann_hits.get(nid, 0)
            s["named_creator"] += bool(named)
            s["date_parsed"] += parsed is not None
            s["single_century"] += cent is not None
            s["image"] += bool(rec["image_path"])
            s["chart_ready"] += bool(named) and cent is not None
            if cent is not None:
                centuries[nid][cent] += 1
            sources[nid][sid] += 1
            for c in named:
                creators[nid].add(c.casefold())
        segs = sorted({segment_of[m] for m in matched})
        for i, a in enumerate(segs):
            for b in segs[i + 1:]:
                seg_pairs[f"{a} + {b}"] += 1

    def pct(a, b):
        return round(100.0 * a / b, 1) if b else 0.0

    report = []
    for nid in order:
        s, node = stats[nid], nodes[nid]
        r = s["records"]
        verdict = "ok" if r >= SIZE_OK else "small" if r >= SIZE_SMALL else "too_small"
        top_sources = sources[nid].most_common(3)
        report.append({
            "id": nid, "label": node["label"], "segment": segment_of[nid], "parent": parent_of[nid],
            "depth": depth_of[nid], "status": node.get("status"), "flags": node.get("flags", []),
            "include": Taxonomy.include(node), "exclude": node.get("exclude"),
            "records": r, "annotations": s["annotations"], "verdict": verdict,
            "other_records": s["other"] if children[nid] and Taxonomy.include(node) else None,
            "pct_named_creator": pct(s["named_creator"], r), "pct_date": pct(s["date_parsed"], r),
            "pct_single_century": pct(s["single_century"], r), "pct_image": pct(s["image"], r),
            "pct_chart_ready": pct(s["chart_ready"], r),
            "distinct_named_creators": len(creators[nid]), "sources": len(sources[nid]),
            "top_source_share": pct(top_sources[0][1], r) if top_sources else 0,
            "top_sources": top_sources,
            "peak_century": centuries[nid].most_common(1)[0][0] if centuries[nid] else None,
            "centuries": dict(sorted(centuries[nid].items())),
        })

    out = {"taxonomy": tax_path, "records_total": n, "problems": problems,
           "segment_overlap": seg_pairs.most_common(), "nodes": report}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "taxonomy_eval.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    cols = ["records", "other_records", "verdict", "pct_named_creator", "pct_date", "pct_single_century", "pct_image",
            "pct_chart_ready", "distinct_named_creators", "sources", "top_source_share", "peak_century"]
    with open(os.path.join(OUT, "taxonomy_eval.tsv"), "w", encoding="utf-8") as fh:
        fh.write("node\tlabel\t" + "\t".join(cols) + "\n")
        for row in report:
            fh.write(f"{'  ' * row['depth']}{row['id']}\t{row['label']}\t" + "\t".join(str(row[c]) for c in cols) + "\n")

    for p in problems:
        print("PROBLEM:", p)
    print(f"{len(report)} nodes evaluated over {n} records -> {OUT}/taxonomy_eval.*")


if __name__ == "__main__":
    main()
