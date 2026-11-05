#!/usr/bin/env python3
"""Phase 3 batch enrichment: reconcile ICARUS creators with Getty ULAN, add Wikidata birthplaces,
and attribute a present-day country to each creator.

    python3 scripts/enrich_creators.py [--no-wikidata]

Inputs: data/db/daedalus.sqlite (creators, artwork dates), data/raw/getty/ulan/rel/*.out,
        Natural Earth 10m countries, Wikidata SPARQL (cached in data/cache/wikidata/).
Output: data/enrichment/creator_geo.tsv (one row per creator name_key, committed), summary.json.

Attribution hierarchy (brief section 4):
  1. birthplace -> present-day country (Wikidata birthplace coordinates + Natural Earth polygons;
     else the present-day nation in ULAN's birthplace string)
  2. nationality (ULAN preferred nationality, mapped to a present-day country only when unambiguous)
  3. unknown
Name matching is identifier-free (ICARUS has no authority IDs), so it is cautious: an exact
token-set name match, checked against life dates; homonyms without a clear winner stay 'ambiguous'.
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from etl.geo import Countries, parse_place_country  # noqa: E402
from etl.normalize import classify  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
ULAN = os.path.join(ROOT, "data", "raw", "getty", "ulan", "rel")
CACHE = os.path.join(ROOT, "data", "cache", "wikidata")
OUT = os.path.join(ROOT, "data", "enrichment")
NATIONALITY_MAP = os.path.join(ROOT, "taxonomy", "nationality_countries.json")
DB = os.path.join(ROOT, "data", "db", "daedalus.sqlite")
UA = "DaedalusThread/0.1 (https://github.com/Farechiga/daedalus-thread; batch enrichment)"
MAX_CANDIDATES = 25
GENERATION = {"i", "ii", "iii", "iv", "d", "a", "j", "ae", "elder", "younger", "the", "oude", "jonge", "jr", "sr",
              "senior", "junior", "altere", "jungere", "ainé", "aine", "le", "jeune", "pere", "fils"}
PARTICLES = {"van", "de", "der", "den", "von", "vom", "zu", "di", "da", "del", "della", "dei", "du", "des", "la", "le",
             "ten", "ter", "t", "s", "y", "e"}


def base_key(key):
    """Name key without generation markers ('I', 'd. Ä.', 'the elder')."""
    return " ".join(t for t in (key or "").split() if t not in GENERATION) or None


def core_key(key):
    """Base key without particles: used only by the fuzzy fallback."""
    return " ".join(t for t in (base_key(key) or "").split() if t not in PARTICLES) or None

csv.field_size_limit(10 ** 9)


def log(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def rows(name):
    with open(os.path.join(ULAN, name), encoding="utf-8", errors="replace", newline="") as fh:
        yield from csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)


def num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- ICARUS side
def load_creators(db):
    years = collections.defaultdict(list)
    for cid, s, e in db.execute(
            "SELECT ac.creator_id, a.date_start, a.date_end FROM artwork_creator ac JOIN artwork a ON a.rid = ac.artwork_rid "
            "WHERE a.date_semantics = 'object' AND ac.creator_id IS NOT NULL AND (a.date_start IS NOT NULL OR a.date_end IS NOT NULL)"):
        years[cid].append(((s if s is not None else e) + (e if e is not None else s)) / 2)
    out = []
    for cid, key, name, kind, life, n, variants in db.execute(
            "SELECT id, name_key, display_name, kind, life_dates, n_artworks, variants FROM creator "
            "WHERE kind IN ('person', 'master') ORDER BY n_artworks DESC"):
        ys = sorted(years.get(cid, []))
        span = (ys[int(len(ys) * 0.1)], ys[int(len(ys) * 0.9) - (1 if len(ys) > 1 else 0)]) if ys else None
        out.append({"id": cid, "key": key, "name": name, "kind": kind, "life": life, "n": n,
                    "variants": json.loads(variants or "[]"), "years": ys, "span": span})
    return out


# ---------------------------------------------------------------- ULAN side
def load_ulan(needed_keys):
    log("ULAN: subjects")
    rtype = {r[6]: r[3] for r in rows("SUBJECT.out") if len(r) >= 7}
    log("ULAN: names")
    index = collections.defaultdict(set)
    base_index = collections.defaultdict(set)
    token_index = collections.defaultdict(set)
    needed_tokens = {t for k in needed_keys if k for t in (core_key(k) or "").split() if len(t) >= 4}
    preferred, n_terms = {}, collections.Counter()
    for r in rows("TERM.out"):
        if len(r) < 13:
            continue
        sid, term, pref = r[9], r[10], r[7]
        n_terms[sid] += 1
        if pref == "P":
            preferred[sid] = term
        key = classify(term)["name_key"]
        if key in needed_keys:
            index[key].add(sid)
        bk = base_key(key)
        if bk in needed_keys:
            base_index[bk].add(sid)
        ck = core_key(key)
        if ck:
            for tok in ck.split():
                if tok in needed_tokens:
                    token_index[tok].add((sid, ck))
    log("ULAN: biographies, nationalities, places")
    bio = {}
    for r in rows("BIOGRAPHY.out"):
        if len(r) >= 10 and r[7] == "P":
            bio[r[9]] = {"text": r[1], "birth": num(r[2]), "birth_place": r[3] or None,
                         "death": num(r[5]), "death_place": r[6] or None}
    labels = {r[1]: r[2] for r in rows("LOOKUP_VALUES.out") if len(r) >= 3 and r[0] == "nat_nationality_code"}
    nat = {}
    for r in rows("NATIONALITY.out"):
        if len(r) >= 5 and r[3] == "P":
            nat.setdefault(r[4], labels.get(r[2], r[2]))
    places_needed = {b[k] for b in bio.values() for k in ("birth_place",) if b[k]}
    place = {r[1]: r[0] for r in rows("PLACE.out") if len(r) >= 2 and r[1] in places_needed}
    return {"rtype": rtype, "index": index, "base_index": base_index, "token_index": token_index,
            "preferred": preferred, "n_terms": n_terms,
            "bio": bio, "nat": nat, "place": place}


# ---------------------------------------------------------------- matching
def life_window_fit(years, birth, death):
    """Share of the creator's dated works that fall inside [birth+10, death+10]."""
    if not years or birth is None:
        return None
    hi = (death if death is not None else birth + 90) + 10
    lo = birth + 10
    return sum(lo <= y <= hi for y in years) / len(years)


def plausible(c, b):
    """Reject candidates who cannot be the author of these dated works."""
    if c["span"] and b.get("birth") is not None and b["birth"] > c["span"][1] + 5:
        return False  # born after (nearly) all the works
    if c["span"] and b.get("death") is not None and b["death"] + 300 < c["span"][0]:
        return False  # works more than three centuries after death
    return True


def match(c, U):
    keys = {c["key"]} | {classify(v)["name_key"] for v in c["variants"]}
    keys.discard(None)
    tier, cands = "exact", set()
    for k in keys:
        cands |= U["index"].get(k, set())
    if not cands:  # second pass: ignore generation markers; life dates then choose elder/younger
        tier = "generation"
        for k in keys:
            cands |= U["base_index"].get(base_key(k), set())
    if not cands:
        fz = fuzzy(c, keys, U)
        return fz or {"status": "unmatched", "method": "no_name_match"}
    if len(cands) > MAX_CANDIDATES:
        return {"status": "ambiguous", "method": f"too_many_name_matches:{len(cands)}"}
    res = choose(c, cands, U)
    if res["status"] == "matched" and tier == "generation":
        res["method"] = "generation_stripped+" + res["method"]
        if res["confidence"] == "high" and not res.get("fit"):
            res["confidence"] = "medium"
    return res


def fuzzy(c, keys, U):
    """Cautious spelling-variant fallback ('Chrispyn de Passe' ~ 'Crispijn van de Passe'): a shared rare
    token, a very similar particle-free name, AND a life window that fits the dated works."""
    if not c["years"]:
        return None
    mine = {core_key(k) for k in keys} - {None}
    pool = {}
    for ck in mine:
        for tok in ck.split():
            for sid, uck in U["token_index"].get(tok, ()):
                r = one_token_variant(ck, uck)
                if r:
                    pool[sid] = max(pool.get(sid, 0), r)
    good = []
    for sid, r in pool.items():
        b = real_dates(U["bio"].get(sid, {}))
        fit = life_window_fit(c["years"], b.get("birth"), b.get("death"))
        if fit is not None and fit >= 0.6 and plausible(c, b):
            good.append((r, fit, sid, b))
    if len(good) != 1:
        return None
    r, fit, sid, b = good[0]
    return {"status": "matched", "method": f"fuzzy_name:{r:.2f}+dates", "confidence": "low", "sid": sid, "fit": fit,
            "birth": b.get("birth"), "death": b.get("death"), "exact": False, "life_ok": False, "terms": U["n_terms"][sid]}


def one_token_variant(a, b):
    """Similarity if two particle-free names have the same tokens except ONE close spelling variant
    (same first letter, length within 2, ratio >= 0.8): Doetichum ~ Doetechum, Susanna ~ Susanne."""
    import difflib
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb) or len(ta) < 2:
        return None
    da, db = sorted(set(ta) - set(tb)), sorted(set(tb) - set(ta))
    if len(da) != 1 or len(db) != 1:
        return None
    x, y = da[0], db[0]
    if x[0] != y[0] or abs(len(x) - len(y)) > 2 or min(len(x), len(y)) < 4:
        return None
    r = difflib.SequenceMatcher(None, x, y).ratio()
    return round(r, 2) if r >= 0.8 else None


def real_dates(b):
    """ULAN uses placeholder spans for unknown lives (1800-2100, 1-2100): treat spans > 110 years as undated."""
    if b.get("birth") is not None and b.get("death") is not None and b["death"] - b["birth"] > 110:
        return dict(b, birth=None, death=None)
    return b


def choose(c, cands, U):
    life = None
    if c["life"]:
        a, _, b = c["life"].partition("–")
        life = (num(a), num(b))
    scored = []
    for sid in cands:
        b = real_dates(U["bio"].get(sid, {}))
        if life and b.get("birth") and b.get("death"):
            if abs(b["birth"] - life[0]) > 3 or abs(b["death"] - life[1]) > 3:
                continue
        if not plausible(c, b):
            continue
        fit = life_window_fit(c["years"], b.get("birth"), b.get("death"))
        exact = classify(U["preferred"].get(sid, ""))["name_key"] == c["key"]
        scored.append({"sid": sid, "fit": fit, "exact": exact, "life_ok": bool(life and b.get("birth")),
                       "terms": U["n_terms"][sid], "birth": b.get("birth"), "death": b.get("death")})
    if not scored:
        return {"status": "unmatched", "method": "candidates_rejected_by_dates", "candidates": sorted(cands)[:8]}
    scored.sort(key=lambda s: (s["life_ok"], s["fit"] if s["fit"] is not None else -1, s["exact"], s["terms"]), reverse=True)
    top = scored[0]
    if len(scored) == 1:
        if top["life_ok"]:
            conf = "high"
        elif top["fit"] is None:
            conf = "medium" if c["years"] else "low"
        else:
            conf = "high" if top["fit"] >= 0.5 else "medium" if top["fit"] >= 0.15 else "low"
        return {"status": "matched", "method": "unique_name" + ("+life_dates" if top["life_ok"] else ""), "confidence": conf, **top}
    second = scored[1]
    if top["life_ok"] and not second["life_ok"]:
        return {"status": "matched", "method": "life_dates_disambiguated", "confidence": "high", **top}
    tf, sf = top["fit"] or 0, second["fit"] or 0
    if tf >= 0.6 and tf - sf >= 0.4:
        return {"status": "matched", "method": "dates_disambiguated", "confidence": "medium", **top}
    # prominence: the record with by far the most name forms is the well-known artist (van Gogh, Michelangelo)
    if top["terms"] >= 3 * max(1, second["terms"]) and top["terms"] >= 8 and tf >= sf:
        return {"status": "matched", "method": f"prominence:{top['terms']}v{second['terms']}", "confidence": "medium", **top}
    return {"status": "ambiguous", "method": f"homonyms:{len(scored)}",
            "candidates": [s["sid"] for s in scored[:8]]}


# ---------------------------------------------------------------- Wikidata
def wikidata_birthplaces(ulan_ids, use_network=True, batch=200):
    """ULAN id -> {qid, places[]} from Wikidata (P245 -> P19 -> P625). Cached per id; misses are cached as null."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "ulan_birthplaces.json")
    cache = json.load(open(path)) if os.path.exists(path) else _import_batch_caches()
    todo = sorted(set(ulan_ids) - set(cache))
    if todo and use_network:
        log(f"Wikidata: querying {len(todo)} uncached ULAN ids")
        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            values = " ".join(f'"{u}"' for u in chunk)
            query = ("SELECT ?ulan ?item ?bp ?bpLabel ?coord WHERE { VALUES ?ulan { %s } ?item wdt:P245 ?ulan . "
                     "OPTIONAL { ?item wdt:P19 ?bp . OPTIONAL { ?bp wdt:P625 ?coord } } "
                     "SERVICE wikibase:label { bd:serviceParam wikibase:language \"en,de,nl,fr,it\". } }") % values
            found = _parse_bindings(_sparql(query))
            for u in chunk:
                cache[u] = found.get(u)
            json.dump(cache, open(path, "w"))
            time.sleep(1.0)
            if (i // batch) % 10 == 0:
                log(f"Wikidata: {min(i + batch, len(todo))}/{len(todo)}")
    json.dump(cache, open(path, "w"))
    return {u: v for u, v in cache.items() if v}


def _parse_bindings(data):
    out = {}
    for b in data["results"]["bindings"]:
        u = b["ulan"]["value"]
        rec = out.setdefault(u, {"qid": b["item"]["value"].rsplit("/", 1)[-1], "places": []})
        if "bp" in b:
            coord = b.get("coord", {}).get("value")
            lon = lat = None
            if coord and coord.startswith("Point("):
                lon, lat = (float(x) for x in coord[6:-1].split())
            place = {"qid": b["bp"]["value"].rsplit("/", 1)[-1], "label": b.get("bpLabel", {}).get("value"), "lon": lon, "lat": lat}
            if place not in rec["places"]:
                rec["places"].append(place)
    return out


def _import_batch_caches():
    """One-time migration from the first run's per-batch files (only ids that were found)."""
    cache = {}
    for name in sorted(os.listdir(CACHE)):
        if name.startswith("ulan_birth_") and name.endswith(".json"):
            cache.update(_parse_bindings(json.load(open(os.path.join(CACHE, name)))))
    return cache


def _sparql(query, tries=4):
    body = urllib.parse.urlencode({"query": query}).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request("https://query.wikidata.org/sparql", data=body, method="POST", headers={
                "Accept": "application/sparql-results+json", "User-Agent": UA,
                "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:  # rate limits or timeouts: back off and retry
            wait = 5 * (attempt + 1)
            log(f"Wikidata error ({e}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Wikidata query failed repeatedly")


# ---------------------------------------------------------------- geography
def attribute(m, U, W, countries, natmap):
    """Pick the country for one matched creator following the attribution hierarchy."""
    sid = m["sid"]
    b = U["bio"].get(sid, {})
    geo = {"country": None, "proxy": None, "evidence": None, "geo_confidence": None,
           "place": None, "lat": None, "lon": None, "nationality": U["nat"].get(sid), "notes": []}
    ulan_place, ulan_country_name = parse_place_country(U["place"].get(b.get("birth_place")))
    ulan_code = countries.code_for_name(ulan_country_name)
    if ulan_country_name and not ulan_code:
        geo["notes"].append(f"unmapped ULAN nation '{ulan_country_name}'")
    wd = W.get(sid)
    wd_place = next((p for p in (wd or {}).get("places", []) if p["lon"] is not None), None)
    wd_code = countries.locate(wd_place["lon"], wd_place["lat"]) if wd_place else None
    if wd and len({p["qid"] for p in wd["places"]}) > 1:
        geo["notes"].append("several Wikidata birthplaces")
    if wd_code:
        geo.update(country=wd_code, proxy="birthplace", place=wd_place["label"], lat=wd_place["lat"], lon=wd_place["lon"])
        if ulan_code and ulan_code != wd_code:
            geo.update(evidence="wikidata", geo_confidence="medium")
            geo["notes"].append(f"ULAN birthplace says {ulan_country_name}")
        else:
            geo.update(evidence="wikidata+ulan" if ulan_code else "wikidata", geo_confidence="high")
    elif ulan_code:
        geo.update(country=ulan_code, proxy="birthplace", evidence="ulan", geo_confidence="high", place=ulan_place)
    elif geo["nationality"] and natmap.get(geo["nationality"]):
        geo.update(country=natmap[geo["nationality"]], proxy="nationality", evidence="ulan", geo_confidence="medium")
    elif geo["nationality"]:
        geo["notes"].append(f"nationality '{geo['nationality']}' has no single present-day country")
    return geo


def unanimous_country(candidates, U, countries):
    """Ambiguous person, certain country: every homonym with a known ULAN birthplace was born in the same
    present-day country (at least two known, none unknown)."""
    codes = []
    for sid in candidates:
        _, cname = parse_place_country(U["place"].get(U["bio"].get(sid, {}).get("birth_place")))
        codes.append(countries.code_for_name(cname))
    if len(codes) >= 2 and None not in codes and len(set(codes)) == 1:
        return {"country": codes[0], "proxy": "birthplace", "evidence": "ulan:homonyms_agree", "geo_confidence": "medium",
                "place": None, "lat": None, "lon": None, "nationality": None,
                "notes": [f"{len(codes)} ULAN homonyms, all born in the same present-day country"]}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-wikidata", action="store_true", help="use only cached Wikidata responses")
    args = ap.parse_args()
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    creators = load_creators(db)
    log(f"{len(creators)} person/master creators")
    needed = set()
    for c in creators:
        keys = {c["key"]} | {classify(v)["name_key"] for v in c["variants"]}
        needed |= keys | {base_key(k) for k in keys}
    needed.discard(None)
    U = load_ulan(needed)
    log(f"ULAN loaded: {len(U['preferred'])} subjects, {len(U['index'])} matching name keys")

    matches = {}
    for c in creators:
        matches[c["key"]] = match(c, U)
    matched = [m["sid"] for m in matches.values() if m["status"] == "matched"]
    log(f"matching: {collections.Counter(m['status'] for m in matches.values())}")

    W = wikidata_birthplaces(matched, use_network=not args.no_wikidata)
    log(f"Wikidata: {len(W)} items for {len(set(matched))} ULAN ids")

    countries = Countries()
    natmap = json.load(open(NATIONALITY_MAP, encoding="utf-8"))["map"]
    os.makedirs(OUT, exist_ok=True)
    cols = ["name_key", "display_name", "n_artworks", "status", "match_method", "match_confidence", "ulan_id", "ulan_name",
            "ulan_birth", "ulan_death", "wikidata_qid", "country_code", "country_name", "proxy_type", "evidence_source",
            "geo_confidence", "birth_place", "birth_lat", "birth_lon", "nationality", "notes", "candidates"]
    stats = collections.Counter()
    weighted = collections.Counter()
    unmapped_nat = collections.Counter()
    with open(os.path.join(OUT, "creator_geo.tsv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        for c in creators:
            m = matches[c["key"]]
            geo = {"country": None, "proxy": None, "evidence": None, "geo_confidence": None, "place": None,
                   "lat": None, "lon": None, "nationality": None, "notes": []}
            if m["status"] == "matched":
                geo = attribute(m, U, W, countries, natmap)
                if geo["proxy"] is None and geo["nationality"]:
                    unmapped_nat[geo["nationality"]] += c["n"]
            elif m["status"] == "ambiguous" and m.get("candidates"):
                geo = unanimous_country(m["candidates"], U, countries) or geo
            sid = m.get("sid")
            bucket = geo["proxy"] or ("matched_no_place" if m["status"] == "matched" else m["status"])
            stats[bucket] += 1
            weighted[bucket] += c["n"]
            w.writerow([c["key"], c["name"], c["n"], m["status"], m.get("method"), m.get("confidence"), sid,
                        U["preferred"].get(sid) if sid else None, m.get("birth"), m.get("death"),
                        (W.get(sid) or {}).get("qid") if sid else None, geo["country"],
                        countries.info[geo["country"]]["name"] if geo["country"] else None, geo["proxy"], geo["evidence"],
                        geo["geo_confidence"], geo["place"], geo["lat"], geo["lon"], geo["nationality"],
                        "; ".join(geo["notes"]) or None, " ".join(m.get("candidates", [])) or None])
    total_credits = sum(c["n"] for c in creators)
    summary = {"generated": time.strftime("%Y-%m-%d %H:%M"), "creators": len(creators), "artwork_credits": total_credits,
               "creators_by_outcome": dict(stats),
               "credits_by_outcome": {k: [v, round(100 * v / total_credits, 1)] for k, v in weighted.most_common()},
               "unmapped_nationalities_by_credits": unmapped_nat.most_common(40)}
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1, ensure_ascii=False)
    log(json.dumps(summary["credits_by_outcome"]))


if __name__ == "__main__":
    main()
