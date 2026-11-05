#!/usr/bin/env python3
"""Build data/db/daedalus.sqlite from ICARUS + Iconclass + taxonomy (Phase 2 importer). Stdlib only.

    python3 scripts/build_db.py [--out data/db/daedalus.sqlite]

The build is repeatable: it writes to a temp file and renames it at the end. Nothing is dropped
for missing fields; every column is nullable and charts choose their own eligible subsets.
"""
import argparse
import collections
import csv
import gzip
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from etl.dates import century_of, parse_time  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.icarus import SOURCES, iter_records, source_of  # noqa: E402
from etl.normalize import ObjectTyper, classify  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "data", "raw")
LANGS = ("en", "de", "nl", "fr", "it", "pl")
REPRODUCTION_SOURCES = {"pauart"}
EXTRA_SOURCES = [("wikidata_paintings.jsonl.gz", "wikidata"), ("met_objects.jsonl.gz", "met"),
                 ("aic_objects.jsonl.gz", "aic"), ("zeri_objects.jsonl.gz", "zeri")]
EXTRA_SOURCE_ROWS = [("wikidata", "Wikidata (paintings)", None, "www.wikidata.org"),
                     ("met", "The Metropolitan Museum of Art", "US", "www.metmuseum.org"),
                     ("aic", "Art Institute of Chicago", "US", "www.artic.edu"),
                     ("zeri", "Fondazione Federico Zeri (photo archive)", "IT", "catalogo.fondazionezeri.unibo.it")]
CREATOR_FILES = ("creator_geo.tsv", "wikidata_creators.tsv", "met_creators.tsv", "aic_creators.tsv", "zeri_creators.tsv")  # dates/creators describe a documentary photograph (decision log, open item)

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE source (id TEXT PRIMARY KEY, name TEXT, country TEXT, host TEXT, records INTEGER);
CREATE TABLE object_type (id TEXT PRIMARY KEY, label TEXT, position INTEGER, records INTEGER);
CREATE TABLE artwork (
  rid INTEGER PRIMARY KEY,           -- compact join key
  id TEXT NOT NULL UNIQUE,           -- ICARUS identifier (preserved)
  source_id TEXT NOT NULL REFERENCES source(id),
  source_url TEXT,                   -- link out to the record (and its image) at the source
  link_https INTEGER,                -- 1 if source_url is https; plain-http links sort last and carry a warning
  title TEXT,                        -- first title; all titles in artwork_title
  holding TEXT,                      -- meta/collection: holding institution (raw)
  object_type TEXT REFERENCES object_type(id),
  instance_of TEXT, genre TEXT,      -- raw values, ' | '-joined
  date_text TEXT,                    -- raw meta/time values, ' | '-joined
  date_start INTEGER, date_end INTEGER, date_kind TEXT, date_approx INTEGER,
  century INTEGER,                   -- strict: whole range within one century, else NULL
  century_mid INTEGER,               -- midpoint century when span <= 50 years (approximate)
  date_semantics TEXT,               -- 'object' | 'reproduction'
  n_creators INTEGER, n_named_creators INTEGER, n_codes INTEGER,
  split TEXT,
  dataset TEXT,                      -- 'icarus' | 'wikidata'
  image_url TEXT,                    -- https thumbnail source where the record provides one (Wikimedia Commons)
  fame INTEGER,                      -- Wikipedia sitelinks of the work (Wikidata); NULL when unknown
  highlight INTEGER,                 -- museum highlight flag (The Met)
  fame_score REAL,                   -- 0..1, see compute_fame()
  fame_pct REAL,                     -- share of all artworks with a lower score (0..1)
  notable INTEGER,                   -- 1 = top half by fame (the default "Notable works" view)
  primary_creator INTEGER            -- first credited named artist (for per-artist variety in "Iconic first")
);
CREATE TABLE artwork_title (id INTEGER PRIMARY KEY, artwork_rid INTEGER NOT NULL, position INTEGER, title TEXT);
CREATE TABLE creator (
  id INTEGER PRIMARY KEY, name_key TEXT NOT NULL UNIQUE, display_name TEXT, kind TEXT,
  life_dates TEXT, n_artworks INTEGER, variants TEXT  -- JSON list of raw spellings
);
CREATE TABLE artwork_creator (
  artwork_rid INTEGER NOT NULL, position INTEGER, creator_id INTEGER, raw_name TEXT, qualifier TEXT
);
CREATE TABLE iconclass (
  notation TEXT PRIMARY KEY, parent TEXT, depth INTEGER, in_tree INTEGER,
  label_en TEXT, label_de TEXT, label_nl TEXT, label_fr TEXT, label_it TEXT, label_pl TEXT,
  keywords TEXT,                     -- JSON {lang: [..]}
  n_direct INTEGER, n_rollup INTEGER
);
CREATE TABLE iconclass_ancestor (notation TEXT NOT NULL, ancestor TEXT NOT NULL, distance INTEGER,
  PRIMARY KEY (ancestor, notation)) WITHOUT ROWID;
CREATE TABLE artwork_iconclass (artwork_rid INTEGER NOT NULL, notation TEXT NOT NULL);
CREATE TABLE artwork_iconclass_original (artwork_rid INTEGER NOT NULL, notation TEXT NOT NULL);
CREATE TABLE taxonomy_node (
  id TEXT PRIMARY KEY, segment_id TEXT, parent_id TEXT, depth INTEGER, position INTEGER,
  label TEXT, description TEXT, flags TEXT, include_codes TEXT, exclude_codes TEXT, aliases TEXT, note TEXT,
  n_artworks INTEGER, n_other INTEGER
);
CREATE TABLE artwork_node (node_id TEXT NOT NULL, artwork_rid INTEGER NOT NULL, is_other INTEGER,
  PRIMARY KEY (node_id, artwork_rid)) WITHOUT ROWID;
CREATE TABLE country (code TEXT PRIMARY KEY, name TEXT, iso2 TEXT, continent TEXT, subregion TEXT,
  in_view INTEGER, ax REAL, ay REAL);
CREATE TABLE birthplace (id INTEGER PRIMARY KEY, name TEXT, country_code TEXT, lat REAL, lon REAL, x REAL, y REAL, in_view INTEGER);
CREATE TABLE creator_geo (               -- Phase 3 enrichment (data/enrichment/creator_geo.tsv)
  creator_id INTEGER PRIMARY KEY, country_code TEXT, proxy TEXT,   -- proxy: 'birthplace' | 'nationality'
  evidence TEXT, geo_confidence TEXT, match_status TEXT, match_method TEXT, match_confidence TEXT,
  ulan_id TEXT, wikidata_qid TEXT, ulan_name TEXT, birth_year INTEGER, death_year INTEGER,
  birthplace_id INTEGER, nationality TEXT, notes TEXT
);
CREATE TABLE suggest (id INTEGER PRIMARY KEY, kind TEXT, ref TEXT, label TEXT, detail TEXT, terms TEXT, weight INTEGER);
"""

INDEXES = """
CREATE INDEX artwork_source ON artwork(source_id);
CREATE INDEX artwork_dataset ON artwork(dataset);
CREATE INDEX artwork_notable ON artwork(notable, fame_score);
CREATE INDEX artwork_type ON artwork(object_type);
CREATE INDEX artwork_century ON artwork(century);
CREATE INDEX artwork_dates ON artwork(date_start, date_end);
CREATE INDEX artwork_title_rid ON artwork_title(artwork_rid);
CREATE INDEX ac_creator ON artwork_creator(creator_id, artwork_rid);
CREATE INDEX ac_artwork ON artwork_creator(artwork_rid);
CREATE INDEX ai_notation ON artwork_iconclass(notation, artwork_rid);
CREATE INDEX ai_artwork ON artwork_iconclass(artwork_rid);
CREATE INDEX aio_artwork ON artwork_iconclass_original(artwork_rid);
CREATE INDEX an_artwork ON artwork_node(artwork_rid, node_id);
CREATE INDEX tn_parent ON taxonomy_node(parent_id, position);
CREATE INDEX cg_country ON creator_geo(country_code, proxy, creator_id);
CREATE INDEX cg_place ON creator_geo(birthplace_id);
CREATE VIRTUAL TABLE suggest_fts USING fts5(terms, content='suggest', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2', prefix='1 2 3');
CREATE VIRTUAL TABLE suggest_tri USING fts5(terms, content='suggest', content_rowid='id',
  tokenize='trigram remove_diacritics 1');
CREATE VIRTUAL TABLE title_fts USING fts5(title, content='artwork_title', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2');
INSERT INTO suggest_fts(suggest_fts) VALUES ('rebuild');
INSERT INTO suggest_tri(suggest_tri) VALUES ('rebuild');
INSERT INTO title_fts(title_fts) VALUES ('rebuild');
"""


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def load_splits():
    split = {}
    for s in ("train", "val", "test"):
        with open(os.path.join(RAW, "icarus", f"{s}.txt")) as fh:
            for line in fh:
                split[line.strip()] = s
    return split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "db", "daedalus.sqlite"))
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)

    ic = Iconclass(langs=LANGS)
    tax = Taxonomy(ic)
    if tax.problems:
        sys.exit("taxonomy problems:\n  " + "\n  ".join(tax.problems))
    typer = ObjectTyper()
    splits = load_splits()
    log("loaded Iconclass, taxonomy, object types, splits")

    db = sqlite3.connect(tmp)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-400000;")
    db.executescript(SCHEMA)

    creators = {}  # name_key -> [id, display Counter, kind, life_dates, artworks set-size counter, variants Counter]
    code_direct = collections.Counter()
    code_rollup = collections.Counter()
    node_count, node_other = collections.Counter(), collections.Counter()
    src_count, type_count = collections.Counter(), collections.Counter()
    rows = {k: [] for k in ("artwork", "title", "ac", "ai", "aio", "an")}

    def flush():
        db.executemany("INSERT INTO artwork VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows["artwork"])
        db.executemany("INSERT INTO artwork_title(artwork_rid, position, title) VALUES (?,?,?)", rows["title"])
        db.executemany("INSERT INTO artwork_creator VALUES (?,?,?,?,?)", rows["ac"])
        db.executemany("INSERT INTO artwork_iconclass VALUES (?,?)", rows["ai"])
        db.executemany("INSERT INTO artwork_iconclass_original VALUES (?,?)", rows["aio"])
        db.executemany("INSERT INTO artwork_node VALUES (?,?,?)", rows["an"])
        for v in rows.values():
            v.clear()

    rid = 0
    for rec in iter_records(os.path.join(RAW, "icarus", "data.jsonl")):
        rid += 1
        sid = source_of(rec["url"])[0]
        src_count[sid] += 1

        parsed = None
        for t in rec["time"]:
            p = parse_time(t)
            if p and p["kind"] != "unparsed":
                parsed = p
                break
        cent = century_of(parsed)
        cent_mid = None
        if parsed and parsed["start"] is not None and parsed["end"] is not None and parsed["end"] - parsed["start"] <= 50:
            cent_mid = (parsed["start"] + parsed["end"]) // 2 // 100 * 100

        otype = typer.type_of(rec["instance_of"], rec["genre"], sid)
        type_count[otype] += 1

        n_named = 0
        seen_creators = set()
        for pos, raw in enumerate(rec["creator"]):
            c = classify(raw)
            cid = None
            if c["kind"] != "qualifier":
                entry = creators.get(c["name_key"])
                if entry is None:
                    entry = creators[c["name_key"]] = [len(creators) + 1, collections.Counter(), c["kind"],
                                                       c["life_dates"], 0, collections.Counter()]
                entry[1][c["display"]] += 1
                entry[5][raw] += 1
                if c["life_dates"] and not entry[3]:
                    entry[3] = c["life_dates"]
                cid = entry[0]
                if cid not in seen_creators:
                    entry[4] += 1
                    seen_creators.add(cid)
                if c["kind"] != "anonymous":
                    n_named += 1
            rows["ac"].append((rid, pos, cid, raw, c["qualifier"]))

        codes = list(dict.fromkeys(rec["iconclass_processed"]))
        rolled = set()
        for code in codes:
            rows["ai"].append((rid, code))
            code_direct[code] += 1
            rolled.update(ic.ancestors(code))
        code_rollup.update(rolled)
        for code in dict.fromkeys(rec["iconclass_original"]):
            rows["aio"].append((rid, code))

        own_hits, matched, _ = tax.match(codes)
        for nid in matched:
            other = int(tax.is_other(nid, own_hits, matched))
            rows["an"].append((nid, rid, other))
            node_count[nid] += 1
            node_other[nid] += other

        for pos, title in enumerate(rec["title"]):
            rows["title"].append((rid, pos, title))

        rows["artwork"].append((
            rid, rec["id"], sid, rec["url"], int((rec["url"] or "").lower().startswith("https://")),
            rec["title"][0] if rec["title"] else None,
            rec["collection"][0] if rec["collection"] else None, otype,
            " | ".join(rec["instance_of"]) or None, " | ".join(rec["genre"]) or None,
            " | ".join(rec["time"]) or None,
            parsed["start"] if parsed else None, parsed["end"] if parsed else None,
            parsed["kind"] if parsed else ("unparsed" if rec["time"] else None),
            int(parsed["approx"]) if parsed else None, cent, cent_mid,
            "reproduction" if sid in REPRODUCTION_SOURCES else "object",
            len(rec["creator"]), n_named, len(codes), splits.get(rec["id"]), "icarus", None, None, None, None, None, None, None,
        ))
        if rid % 50000 == 0:
            flush()
            log(f"{rid} records")
    flush()
    log(f"{rid} ICARUS artworks inserted")

    # ---- additional sources (data/sources/*.jsonl.gz): Wikidata paintings, The Met, ...
    wd_creators = load_wikidata_creators()
    extra = collections.Counter()
    for fname, dataset in EXTRA_SOURCES:
        path = os.path.join(ROOT, "data", "sources", fname)
        if not os.path.exists(path):
            continue
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                w = json.loads(line)
                rid += 1
                extra[dataset] += 1
                sid = w.get("source_id", dataset)
                otype = w.get("object_type", "painting")
                src_count[sid] += 1
                type_count[otype] += 1
                start, end, kind = w["date"] if w["date"] else (None, None, None)
                parsed = {"start": start, "end": end, "kind": kind, "approx": False} if w["date"] else None
                cent = century_of(parsed)
                cent_mid = (start + end) // 2 // 100 * 100 if parsed and end - start <= 50 else None
                n_named, seen_creators = 0, set()
                for pos, c in enumerate(w["creators"]):
                    name = c["name"] or (wd_creators.get(c["key"], {}).get("name"))
                    if not name or not c["key"] or (c.get("qid") and not re.fullmatch(r"Q\d+", c["qid"])):
                        continue
                    key = c["key"]
                    entry = creators.get(key)
                    if entry is None:
                        info = wd_creators.get(key, {})
                        life = f"{info['birth']}–{info['death']}" if info.get("birth") and info.get("death") else None
                        entry = creators[key] = [len(creators) + 1, collections.Counter(), "person", life, 0, collections.Counter()]
                    entry[1][name] += 1
                    entry[5][name] += 1
                    if entry[0] not in seen_creators:
                        entry[4] += 1
                        seen_creators.add(entry[0])
                    n_named += 1
                    rows["ac"].append((rid, pos, entry[0], name, None))
                codes = w["iconclass"]
                rolled = set()
                for code in codes:
                    rows["ai"].append((rid, code))
                    code_direct[code] += 1
                    rolled.update(ic.ancestors(code))
                code_rollup.update(rolled)
                own_hits, matched, _ = tax.match(codes)
                for nid in matched:
                    other = int(tax.is_other(nid, own_hits, matched))
                    rows["an"].append((nid, rid, other))
                    node_count[nid] += 1
                    node_other[nid] += other
                if w["title"]:
                    rows["title"].append((rid, 0, w["title"]))
                image = w.get("image")
                if image and "commons.wikimedia.org" in image:
                    image += "?width=640"
                url = w.get("source_url") or f"https://www.wikidata.org/wiki/{w['qid']}"
                rows["artwork"].append((
                    rid, w["id"], sid, url, int(url.lower().startswith("https://")), w["title"], w["holding"],
                    otype, w.get("instance_of") or "painting (Wikidata)", None, w["date_text"], start, end, kind,
                    int(bool(w.get("approx"))) if parsed else None, cent, cent_mid, "object", len(w["creators"]), n_named,
                    len(codes), None, dataset, image, w.get("links"), int(bool(w.get("highlight"))), None, None, None, None))
                if extra[dataset] % 50000 == 0:
                    flush()
        flush()
        log(f"{extra[dataset]} {dataset} records inserted ({rid} artworks in total)")

    # creators
    db.executemany("INSERT INTO creator VALUES (?,?,?,?,?,?,?)", [
        (e[0], key, e[1].most_common(1)[0][0], e[2], e[3], e[4], json.dumps([v for v, _ in e[5].most_common(12)], ensure_ascii=False))
        for key, e in creators.items()])
    log(f"{len(creators)} creators")

    # iconclass: every used code and all its ancestors
    used = set(code_rollup) | set(code_direct)
    ic_rows, anc_rows = [], []
    for code in used:
        chain = ic.ancestors(code)
        parent = chain[1] if len(chain) > 1 else None
        labels = [ic.label(code, lang) for lang in LANGS]
        kws = {lang: ic.keywords[lang].get(code) for lang in LANGS if ic.keywords[lang].get(code)}
        ic_rows.append((code, parent, len(chain) - 1, int(code in ic.known), *labels,
                        json.dumps(kws, ensure_ascii=False) if kws else None, code_direct[code], code_rollup[code]))
        for dist, anc in enumerate(chain):
            anc_rows.append((code, anc, dist))
    db.executemany("INSERT INTO iconclass VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ic_rows)
    db.executemany("INSERT OR IGNORE INTO iconclass_ancestor VALUES (?,?,?)", anc_rows)
    log(f"{len(ic_rows)} iconclass nodes, {len(anc_rows)} ancestor links")

    # taxonomy
    tn_rows = []
    position = collections.Counter()
    for nid in tax.order:
        node = tax.nodes[nid]
        parent = tax.parent[nid]
        position[parent] += 1
        tn_rows.append((nid, tax.segment[nid], parent, tax.depth[nid],
                        node.get("display_order", position[parent]), node["label"], node.get("description"),
                        json.dumps(node.get("flags", [])), json.dumps(Taxonomy.include(node)),
                        json.dumps(node.get("exclude", [])), json.dumps(node.get("aliases", []), ensure_ascii=False),
                        node.get("note"), node_count[nid], node_other[nid] if tax.children[nid] and Taxonomy.include(node) else None))
    db.executemany("INSERT INTO taxonomy_node VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tn_rows)

    db.executemany("INSERT INTO source VALUES (?,?,?,?,?)",
                   [(sid, name, country, host, src_count[sid]) for host, (sid, name, country) in SOURCES.items()]
                   + [(sid, name, country, host, src_count[sid]) for sid, name, country, host in EXTRA_SOURCE_ROWS if src_count[sid]])
    db.executemany("INSERT INTO object_type VALUES (?,?,?,?)",
                   [(t["id"], t["label"], i, type_count[t["id"]]) for i, t in enumerate(typer.types)])
    log("taxonomy, sources, object types")

    load_geography(db, creators)
    log("geography (countries, birthplaces, creator attribution)")

    compute_fame(db)
    log("fame scores")

    build_suggest(db, ic, tax, node_count, creators)
    log("suggest table")

    db.executescript(INDEXES)
    log("indexes and full-text indexes")

    meta = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "records": rid,
        "taxonomy_version": tax.raw["taxonomy_version"],
        "iconclass_commit": open(os.path.join(RAW, "iconclass", "SOURCE_COMMIT.txt")).read().split()[0],
        "icarus": "Zenodo 18980670 v1.0 (CC BY 4.0)",
        "reproduction_sources": sorted(REPRODUCTION_SOURCES),
    }
    db.executemany("INSERT INTO meta VALUES (?,?)", [(k, json.dumps(v)) for k, v in meta.items()])
    db.commit()
    db.execute("ANALYZE")
    db.execute("VACUUM")
    db.close()
    os.replace(tmp, args.out)
    log(f"done -> {args.out} ({os.path.getsize(args.out) / 1e6:.0f} MB)")


def compute_fame(db):
    """fame_score (0..1) = max(work fame, 0.7 x artist fame) + 0.12 for a museum highlight; halved for documentary photos.
    work fame:   log Wikipedia editions of the artwork itself (Wikidata/Met items; ICARUS works known to Wikidata
                 by RKDimages or Rijksmuseum inventory number), 60 editions = 1.0
    artist fame: log Wikipedia editions of the best-known *visual artist* credited (patrons, authors, rulers don't count),
                 150 editions = 1.0. Anonymous and unlinked artists score 0.
    notable = top half of all artworks by score (ties at the cut go in only if their score is above zero)."""
    import math
    enr = os.path.join(ROOT, "data", "enrichment")
    artist = {}
    p = os.path.join(enr, "fame_creators.tsv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
            artist[r["wikidata_qid"]] = int(r["sitelinks"]) if r.get("visual_artist", "1") == "1" else 0
    # artists first seen in the Wikidata/Met harvests carry their own sitelinks; they are credited painters/makers
    for f in CREATOR_FILES[1:]:
        p = os.path.join(enr, f)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
                if r.get("links") and r["wikidata_qid"] not in artist:
                    artist[r["wikidata_qid"]] = int(r["links"])
    works = {}
    p = os.path.join(enr, "fame_works.tsv")
    if os.path.exists(p):
        works = {r["artwork_id"]: int(r["sitelinks"]) for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t")}
    primary = {}
    for rid, cid in db.execute("SELECT ac.artwork_rid, ac.creator_id FROM artwork_creator ac JOIN creator c ON c.id = ac.creator_id "
                               "WHERE c.kind IN ('person', 'master') ORDER BY ac.artwork_rid, ac.position"):
        primary.setdefault(rid, cid)
    best_artist = collections.Counter()
    for rid, qid in db.execute("SELECT ac.artwork_rid, g.wikidata_qid FROM artwork_creator ac JOIN creator_geo g "
                               "ON g.creator_id = ac.creator_id WHERE g.wikidata_qid IS NOT NULL"):
        n = artist.get(qid, 0)
        if n > best_artist[rid]:
            best_artist[rid] = n
    scores = []
    for rid, aid, fame, highlight, semantics in db.execute("SELECT rid, id, fame, highlight, date_semantics FROM artwork"):
        w = fame if fame is not None else works.get(aid, 0)
        s_work = min(1.0, math.log1p(w) / math.log1p(60))
        s_art = min(1.0, math.log1p(best_artist[rid]) / math.log1p(150))
        score = max(s_work, 0.7 * s_art) + (0.12 if highlight else 0.0)
        if semantics == "reproduction":
            score *= 0.5
        scores.append((round(score, 4), rid))
    scores.sort()
    n = len(scores)
    cut = scores[n // 2][0] if n else 0
    rows, below = [], 0
    for i, (score, rid) in enumerate(scores):
        if i and score != scores[i - 1][0]:
            below = i
        rows.append((score, below / n, int(score > cut or (score == cut and score > 0)), primary.get(rid), rid))
    db.executemany("UPDATE artwork SET fame_score = ?, fame_pct = ?, notable = ?, primary_creator = ? WHERE rid = ?", rows)
    notable = sum(r[2] for r in rows)
    log(f"fame: cut at score {cut:.3f}; {notable} notable of {n} ({100 * notable / max(n, 1):.0f}%)")


def load_wikidata_creators():
    out = {}
    for f in CREATOR_FILES[1:]:
        path = os.path.join(ROOT, "data", "enrichment", f)
        if os.path.exists(path):
            for r in csv.DictReader(open(path, encoding="utf-8", newline=""), delimiter="\t"):
                out.setdefault(r["name_key"], {"name": r["display_name"], "birth": r["ulan_birth"] or None, "death": r["ulan_death"] or None})
    return out


def load_geography(db, creators):
    """Countries and anchors from the basemap, plus creator attribution from the enrichment TSV (if present)."""
    from etl.geo import Countries, Viewport
    countries, view = Countries(), Viewport(width=1000)
    basemap_path = os.path.join(ROOT, "web", "assets", "basemap.json")
    basemap = json.load(open(basemap_path)) if os.path.exists(basemap_path) else {"anchors": {}, "in_view": []}
    db.executemany("INSERT INTO country VALUES (?,?,?,?,?,?,?,?)", [
        (code, i["name"], i["iso2"], i["continent"], i["subregion"], int(code in basemap["in_view"]),
         *(basemap["anchors"].get(code) or (None, None))) for code, i in countries.info.items()])
    paths = [os.path.join(ROOT, "data", "enrichment", f) for f in CREATOR_FILES]
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        log("no data/enrichment/*.tsv: artist geography left empty (run scripts/enrich_creators.py)")
        return
    ids = {key: e[0] for key, e in creators.items()}
    places, rows = {}, []
    for r in (r for path in paths for r in csv.DictReader(open(path, encoding="utf-8", newline=""), delimiter="\t")):
        cid = ids.get(r["name_key"])
        if cid is None:
            continue
        pid = None
        if r["birth_lat"] and r["birth_lon"]:
            lat, lon = float(r["birth_lat"]), float(r["birth_lon"])
            key = (r["birth_place"], round(lat, 2), round(lon, 2))
            if key not in places:
                x, y = view.project(lon, lat)
                places[key] = (len(places) + 1, r["birth_place"], r["country_code"] or None, lat, lon, x, y,
                               int(view.contains(lon, lat)))
            pid = places[key][0]
        rows.append((cid, r["country_code"] or None, r["proxy_type"] or None, r["evidence_source"] or None,
                     r["geo_confidence"] or None, r["status"], r["match_method"] or None, r["match_confidence"] or None,
                     r["ulan_id"] or None, r["wikidata_qid"] or None, r["ulan_name"] or None,
                     int(r["ulan_birth"]) if r["ulan_birth"] else None, int(r["ulan_death"]) if r["ulan_death"] else None,
                     pid, r["nationality"] or None, r["notes"] or None))
    db.executemany("INSERT INTO birthplace VALUES (?,?,?,?,?,?,?,?)", list(places.values()))
    db.executemany("INSERT OR IGNORE INTO creator_geo VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def build_suggest(db, ic, tax, node_count, creators):
    rows = []
    # themes, groups and segments
    for nid in tax.order:
        node = tax.nodes[nid]
        seg_label = tax.nodes[tax.segment[nid]]["label"]
        kind = "segment" if tax.depth[nid] == 0 else "theme"
        terms = " ; ".join([node["label"]] + node.get("aliases", []))
        rows.append((kind, nid, node["label"], seg_label if kind == "theme" else None, terms, node_count[nid]))
    # Iconclass subjects actually used in ICARUS (plus ancestors), multilingual labels + keywords
    for code, n_rollup, *labels_kw in db.execute(
            "SELECT notation, n_rollup, label_en, label_de, label_nl, label_fr, label_it, label_pl, keywords FROM iconclass"):
        labels, kw = labels_kw[:-1], labels_kw[-1]
        if not n_rollup:
            continue
        terms = [code] + [lab for lab in labels if lab]
        if kw:
            for words in json.loads(kw).values():
                terms.extend(words)
        if "(" in code and code.endswith(")"):
            terms.append(code[code.rindex("(") + 1:-1].title())
        label = labels[0] or code
        rows.append(("subject", code, label, code, " ; ".join(terms), n_rollup))
    # creators (named persons, masters, institutions); anonymous is offered as a single entry
    for key, e in creators.items():
        if e[4] < 1:
            continue
        display = e[1].most_common(1)[0][0]
        variants = [v for v, _ in e[5].most_common(12)]
        rows.append(("artist", str(e[0]), display, e[2] if e[2] != "person" else e[3],
                     " ; ".join([display] + variants), e[4]))
    # countries of birth (multilingual names from Natural Earth), weighted by artworks
    from etl.geo import Countries
    props = {f["properties"]["ADM0_A3"]: f["properties"] for f in Countries().features}
    for code, n in db.execute(
            "SELECT g.country_code, count(DISTINCT ac.artwork_rid) FROM creator_geo g JOIN artwork_creator ac "
            "ON ac.creator_id = g.creator_id WHERE g.proxy = 'birthplace' GROUP BY 1").fetchall():
        p = props.get(code, {})
        names = [p.get(k) for k in ("NAME", "NAME_LONG", "NAME_EN", "NAME_DE", "NAME_NL", "NAME_FR", "NAME_IT", "NAME_PL", "NAME_ES")]
        extra = {"NLD": ["Holland"], "GBR": ["Britain", "England", "Scotland"], "DEU": ["Deutschland"], "BEL": ["Flanders", "Vlaanderen"]}
        terms = [t for t in dict.fromkeys(names + extra.get(code, [])) if t]
        rows.append(("country", code, p.get("NAME", code), None, " ; ".join(terms), n))
    for sid, name, n in db.execute("SELECT id, name, records FROM source"):
        rows.append(("source", sid, name, None, name, n))
    for tid, label, n in db.execute("SELECT id, label, records FROM object_type"):
        rows.append(("object_type", tid, label, None, label, n))
    db.executemany("INSERT INTO suggest(kind, ref, label, detail, terms, weight) VALUES (?,?,?,?,?,?)", rows)


if __name__ == "__main__":
    main()
