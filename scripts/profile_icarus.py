#!/usr/bin/env python3
"""Phase 1 profile of ICARUS data.jsonl.

Writes data/profile/profile.json plus TSV detail tables. Stdlib only; one pass, ~1-2 min.
    python3 scripts/profile_icarus.py
"""
import collections
import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from etl.dates import century_of, parse_time  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.icarus import iter_records, source_of  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data", "raw", "icarus", "data.jsonl")
OUT = os.path.join(ROOT, "data", "profile")

FIELDS = ("title", "creator", "time", "instance_of", "genre", "collection",
          "iconclass_original", "iconclass_processed")

ANON = re.compile(r"\b(anonym\w*|anoniem|unbekannt\w*|unknown|onbekend\w*|nieokreślony|nieznany|anonim\w*|ignoto|n\.\s?n\.)", re.I)
MONOGRAM = re.compile(r"\bmonogramm\w*|\bmeister\b.*\b[A-Z]{1,3}\b\.?$", re.I)
MASTER = re.compile(r"^(meister|master|meester)\b", re.I)
QUALIFIED = re.compile(
    r"\b(werkstatt|umkreis|nachfolger|nachahmer|schule|kopie|art des|zugeschrieben|attributed|toegeschreven|"
    r"workshop|circle|follower|manner|copy|school|naar|omgeving|navolger|atelier|kring|after|nach)\b", re.I)
EMBEDDED_DATES = re.compile(r"\d{3,4}")


def norm_name(s):
    s = unicodedata.normalize("NFKC", s).casefold()
    return " ".join(re.sub(r"[^\w\s,.'-]", " ", s).split())


def shape(s):
    s = re.sub(r"\d", "9", s)
    return re.sub(r"[^\W\d_]+", "a", s)


def pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def top(counter, n):
    return [[k, v] for k, v in counter.most_common(n)]


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    ic = Iconclass()

    n = 0
    field_any = collections.Counter()
    field_values = collections.Counter()
    multi = collections.Counter()  # records with >1 value per field
    src_n = collections.Counter()
    src_field = collections.defaultdict(collections.Counter)
    src_meta = {}
    has_image = collections.Counter()
    img_min_side = collections.Counter()

    creators_raw = collections.Counter()
    creators_norm = collections.Counter()
    creator_flags = collections.Counter()
    creator_flag_examples = collections.defaultdict(list)
    creator_records_flag = collections.Counter()

    time_kind = collections.Counter()
    time_approx = 0
    time_unparsed_shapes = collections.Counter()
    time_unparsed_examples = {}
    rec_time_status = collections.Counter()
    cent_strict = collections.Counter()
    cent_mid = collections.Counter()
    span_bins = collections.Counter()
    src_time_ok = collections.Counter()

    codes_per_rec = collections.Counter()
    direct_ann = collections.Counter()
    direct_rec = collections.Counter()
    rollup_rec = collections.Counter()
    unresolved = collections.Counter()
    exact_known = 0
    total_proc = 0
    total_orig = 0
    orig_with_keys = 0
    bracketed = 0
    top_level_rec = collections.Counter()
    top_level_pairs = collections.Counter()

    values = {f: collections.Counter() for f in ("instance_of", "genre", "collection")}
    src_values = {f: collections.defaultdict(collections.Counter) for f in ("instance_of", "genre")}
    ids = set()

    for rec in iter_records(DATA):
        n += 1
        ids.add(rec["id"])
        sid, sname, scountry = source_of(rec["url"])
        src_n[sid] += 1
        src_meta[sid] = (sname, scountry)

        for f in FIELDS:
            vs = rec[f]
            if vs:
                field_any[f] += 1
                src_field[sid][f] += 1
                field_values[f] += len(vs)
                if len(vs) > 1:
                    multi[f] += 1
        if rec["image_path"]:
            has_image["any"] += 1
            src_field[sid]["image"] += 1
            if rec["image_size"]:
                m = min(rec["image_size"])
                for b in (100, 200, 400, 600, 800, 1200):
                    if m < b:
                        img_min_side[f"<{b}"] += 1
                        break
                else:
                    img_min_side[">=1200"] += 1

        # --- creators
        flags = set()
        for c in rec["creator"]:
            creators_raw[c] += 1
            creators_norm[norm_name(c)] += 1
            for flag, rx in (("anonymous", ANON), ("monogrammist", MONOGRAM), ("named_master", MASTER),
                             ("qualified_attribution", QUALIFIED), ("embedded_dates", EMBEDDED_DATES)):
                if rx.search(c):
                    creator_flags[flag] += 1
                    flags.add(flag)
                    if len(creator_flag_examples[flag]) < 15 and c not in creator_flag_examples[flag]:
                        creator_flag_examples[flag].append(c)
        for f in flags:
            creator_records_flag[f] += 1
        if rec["creator"] and not ({"anonymous"} & flags):
            src_field[sid]["creator_named"] += 1

        # --- time
        best = None
        status = "missing"
        for t in rec["time"]:
            p = parse_time(t)
            if p is None:
                continue
            time_kind[p["kind"]] += 1
            time_approx += p["approx"]
            if p["kind"] == "unparsed":
                sh = shape(t)
                time_unparsed_shapes[sh] += 1
                time_unparsed_examples.setdefault(sh, t)
                if status == "missing":
                    status = "unparsed"
            elif best is None:
                best = p
        if best:
            status = "bounded" if best["start"] is not None and best["end"] is not None else "open_bound"
            src_time_ok[sid] += 1
            c = century_of(best)
            if c is not None:
                cent_strict[c] += 1
            if best["start"] is not None and best["end"] is not None:
                span = best["end"] - best["start"]
                for b in (0, 5, 10, 25, 50, 100, 200):
                    if span <= b:
                        span_bins[f"<={b}"] += 1
                        break
                else:
                    span_bins[">200"] += 1
                if span <= 50:
                    cent_mid[(best["start"] + best["end"]) // 2 // 100 * 100] += 1
        rec_time_status[status] += 1

        # --- iconclass
        codes = list(dict.fromkeys(rec["iconclass_processed"]))
        codes_per_rec[min(len(codes), 30)] += 1
        total_proc += len(rec["iconclass_processed"])
        total_orig += len(rec["iconclass_original"])
        orig_with_keys += sum("(+" in c for c in rec["iconclass_original"])
        seen = set()
        tops = set()
        for c in codes:
            direct_ann[c] += 1
            if c in ic.known:
                exact_known += 1
            if "(" in c and "(+" not in c:
                bracketed += 1
            chain = ic.ancestors(c)
            if ic.resolve(c) is None:
                unresolved[c] += 1
                continue
            seen.update(chain)
            tops.add(chain[-1])
        for c in set(codes):
            direct_rec[c] += 1
        for node in seen:
            rollup_rec[node] += 1
        for t in tops:
            top_level_rec[t] += 1
        for a in tops:
            for b in tops:
                if a < b:
                    top_level_pairs[f"{a}+{b}"] += 1

        for f in values:
            for v in rec[f]:
                values[f][v] += 1
                if f in src_values:
                    src_values[f][sid][v] += 1

    # --- splits
    splits = {}
    in_split = set()
    for s in ("train", "val", "test"):
        with open(os.path.join(ROOT, "data", "raw", "icarus", f"{s}.txt")) as fh:
            sids = {line.strip() for line in fh if line.strip()}
        splits[s] = len(sids)
        in_split |= sids
    splits["records_not_in_any_split"] = len(ids - in_split)
    splits["split_ids_not_in_data"] = len(in_split - ids)

    distinct_creators = len(creators_norm)
    works_per_creator = collections.Counter()
    for c, k in creators_norm.items():
        for b in (1, 2, 5, 10, 50, 100, 500, 1000):
            if k <= b:
                works_per_creator[f"<={b}"] += 1
                break
        else:
            works_per_creator[">1000"] += 1

    per_source = []
    for sid, cnt in src_n.most_common():
        f = src_field[sid]
        per_source.append({
            "source": sid, "name": src_meta[sid][0], "country": src_meta[sid][1], "records": cnt,
            "pct_title": pct(f["title"], cnt), "pct_creator": pct(f["creator"], cnt),
            "pct_creator_named": pct(f["creator_named"], cnt),
            "pct_time": pct(f["time"], cnt), "pct_time_parsed": pct(src_time_ok[sid], cnt),
            "pct_iconclass": pct(f["iconclass_processed"], cnt), "pct_image": pct(f["image"], cnt),
            "pct_instance_of": pct(f["instance_of"], cnt), "pct_genre": pct(f["genre"], cnt),
            "pct_collection": pct(f["collection"], cnt),
            "top_instance_of": top(src_values["instance_of"][sid], 5),
            "top_genre": top(src_values["genre"][sid], 3),
        })

    profile = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "records": n,
        "annotations": {"original": total_orig, "processed": total_proc,
                        "original_with_keys": orig_with_keys,
                        "distinct_processed_codes": len(direct_ann),
                        "processed_codes_exact_in_iconclass": exact_known,
                        "processed_codes_bracketed": bracketed,
                        "distinct_unresolvable_codes": len(unresolved),
                        "unresolvable_annotations": sum(unresolved.values()),
                        "top_unresolvable": top(unresolved, 20),
                        "codes_per_record": sorted(codes_per_rec.items()),
                        "records_without_processed_codes": codes_per_rec[0]},
        "top_level_records": {k: [ic.label(k), v, pct(v, n)] for k, v in sorted(top_level_rec.items())},
        "top_level_pairs": top(top_level_pairs, 45),
        "splits": splits,
        "field_coverage": {f: {"records": field_any[f], "pct": pct(field_any[f], n),
                               "values": field_values[f], "records_multi": multi[f]} for f in FIELDS},
        "images": {"records_with_image": has_image["any"], "pct": pct(has_image["any"], n),
                   "min_side_px": dict(img_min_side)},
        "per_source": per_source,
        "creators": {"values": sum(creators_raw.values()), "distinct_raw": len(creators_raw),
                     "distinct_normalized": distinct_creators,
                     "flag_values": dict(creator_flags), "flag_records": dict(creator_records_flag),
                     "flag_examples": creator_flag_examples,
                     "works_per_creator": dict(works_per_creator),
                     "top": top(creators_norm, 60)},
        "time": {"value_kinds": dict(time_kind), "values_approx": time_approx,
                 "record_status": dict(rec_time_status),
                 "century_strict": dict(sorted(cent_strict.items())),
                 "century_midpoint_span_le_50": dict(sorted(cent_mid.items())),
                 "span_years": dict(span_bins),
                 "top_unparsed_shapes": [[s, c, time_unparsed_examples[s]]
                                         for s, c in time_unparsed_shapes.most_common(40)]},
        "values": {f: {"distinct": len(c), "top": top(c, 40)} for f, c in values.items()},
        "seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(OUT, "profile.json"), "w", encoding="utf-8") as fh:
        json.dump(profile, fh, ensure_ascii=False, indent=1)

    with open(os.path.join(OUT, "iconclass_nodes.tsv"), "w", encoding="utf-8") as fh:
        fh.write("notation\tparent\tdepth\tin_tree\trollup_records\tdirect_records\tlabel_en\n")
        for code, k in sorted(rollup_rec.items(), key=lambda x: -x[1]):
            chain = ic.ancestors(code)
            parent = chain[1] if len(chain) > 1 else ""
            label = (ic.label(code) or "").replace("\t", " ")
            fh.write(f"{code}\t{parent}\t{len(chain) - 1}\t{int(code in ic.known)}\t{k}\t{direct_rec[code]}\t{label}\n")

    with open(os.path.join(OUT, "creators.tsv"), "w", encoding="utf-8") as fh:
        fh.write("creator_raw\trecords\n")
        for c, k in creators_raw.most_common():
            fh.write(f"{c.replace(chr(9), ' ')}\t{k}\n")

    print(f"{n} records profiled in {profile['seconds']}s -> {OUT}")


if __name__ == "__main__":
    main()
