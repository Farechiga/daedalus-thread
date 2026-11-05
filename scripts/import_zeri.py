#!/usr/bin/env python3
"""Import the Fondazione Federico Zeri photo-archive catalogue (RDF dump, CC BY-NC 4.0).

    python3 scripts/import_zeri.py        # expects data/raw/zeri/zeri.zip (amsacta.unibo.it eprint 5497)

About 19,000 artworks, mostly Italian paintings of the 15th-16th centuries. Zeri subject terms come with
Iconclass links (subjects_iconclass.rdf); artists carry ULAN and Wikidata ids (owl:sameAs).
Output: data/sources/zeri_objects.jsonl.gz, data/enrichment/zeri_creators.tsv. Non-commercial use only,
with attribution to the Fondazione Federico Zeri (shown in "About the data").
"""
import collections
import csv
import gzip
import importlib.util
import json
import os
import re
import sys
import urllib.parse
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from etl.dates import parse_time  # noqa: E402
from etl.geo import Countries  # noqa: E402
from etl.iconclass import Iconclass  # noqa: E402
from etl.normalize import classify  # noqa: E402
from etl.taxonomy import Taxonomy  # noqa: E402

_spec = importlib.util.spec_from_file_location("wdh", os.path.join(os.path.dirname(__file__), "fetch_wikidata_artworks.py"))
wdh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wdh)

ZIP = os.path.join(ROOT, "data", "raw", "zeri", "zeri.zip")
OUT = os.path.join(ROOT, "data", "sources", "zeri_objects.jsonl.gz")
OUT_CRE = os.path.join(ROOT, "data", "enrichment", "zeri_creators.tsv")
NS = "https://w3id.org/zericatalog/"


def iconclass_index(ic):
    """Zeri writes names without spaces ('11H(JOHNTHEBAPTIST)'): index known notations by their space-free form."""
    return {k.replace(" ", "").upper(): k for k in ic.known}


def resolve_codes(uri, ic, idx):
    raw = urllib.parse.unquote(uri.rsplit("iconclass.org/", 1)[-1]).strip()
    out = []
    for part in raw.split(":"):
        code = re.sub(r"\(\+[^)]*\)", "", part).strip()  # drop Iconclass keys like (+3)
        code = idx.get(code.replace(" ", "").upper(), code)
        if ic.resolve(code):
            out.append(code)
    return out


def main():
    ic = Iconclass()
    tax = Taxonomy(ic)
    idx = iconclass_index(ic)
    z = zipfile.ZipFile(ZIP)
    names = z.namelist()

    subj = {}
    xml = z.read("dump-complete/subjects_iconclass.rdf").decode("utf-8")
    for slug, body in re.findall(r'<fabio:SubjectTerm rdf:about="https://w3id\.org/zericatalog/subject/([^"]+)"\s*(?:/>|>(.*?)</fabio:SubjectTerm>)', xml, re.S):
        codes = [c for u in re.findall(r'rdf:resource="(http://iconclass\.org/[^"]+)"', body or "") for c in resolve_codes(u, ic, idx)]
        if codes:
            subj[slug] = codes
    wdh.log(f"{len(subj)} Zeri subject terms with Iconclass")

    artists = {}
    for n in names:
        if not re.search(r"/artist\d+\.rdf$", n):
            continue
        x = z.read(n).decode("utf-8", "replace")
        m = re.search(r'rdf:about="https://w3id\.org/zericatalog/person/\d+/([^"/]+)"', x)  # keyed by name slug
        if not m:
            continue
        # the person's own label: "Torrigiani Pietro, sculptor" (the first labels in the file are naming metadata)
        label = re.search(r'zericatalog/person/\d+/[^"]+"[^>]*>\s*(?:<[^>]+>\s*)*?<rdfs:label xml:lang="en">([^<,]+)', x)
        born = re.search(r"zericatalog/birth/[^\"]+\".*?zericatalog/date/(\d{3,4})", x, re.S)
        died = re.search(r"zericatalog/death/[^\"]+\".*?zericatalog/date/(\d{3,4})", x, re.S)
        artists[m.group(1)] = {
            "name": label.group(1).strip() if label else m.group(1).replace("-", " ").title(),
            "wikidata": (re.search(r"wikidata\.org/entity/(Q\d+)", x) or [None, None])[1],
            "ulan": (re.search(r"vocab\.getty\.edu/ulan/(\d+)", x) or [None, None])[1],
            "birth": int(born.group(1)) if born else None, "death": int(died.group(1)) if died else None}
    wdh.log(f"{len(artists)} Zeri artists ({sum(1 for a in artists.values() if a['wikidata'])} with Wikidata ids)")

    known = {}
    for f in ("creator_geo.tsv", "wikidata_creators.tsv", "met_creators.tsv", "aic_creators.tsv"):
        p = os.path.join(ROOT, "data", "enrichment", f)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
                if r.get("wikidata_qid"):
                    known.setdefault(r["wikidata_qid"], r["name_key"])
                if r.get("ulan_id") and r.get("status") == "matched":
                    known.setdefault("ulan:" + r["ulan_id"], r["name_key"])

    kept, dropped = [], collections.Counter()
    for n in names:
        if not re.search(r"/OA\d+\.rdf$", n):
            continue
        x = z.read(n).decode("utf-8", "replace")
        aid = re.search(r'zericatalog/artwork/(\d+)"', x)
        if not aid:
            continue
        aid = aid.group(1)
        title = re.search(r'<crm:E35_Title[^>]*>\s*<rdfs:label xml:lang="it">([^<]+)</rdfs:label>', x)
        title = title.group(1).strip() if title else None
        if title and " , " in title:  # "Bonaccorsi Pietro , Sacra Famiglia con san Giovannino" -> the subject part
            title = title.split(" , ", 1)[1].strip()
        slugs = set(re.findall(r'zericatalog/subject/([^"]+)"', x))
        codes = sorted({c for s in slugs for c in subj.get(s, [])})
        if not codes or not any(tax.match([c])[0] for c in codes):
            dropped["no_mapped_subject"] += 1
            continue
        dt = re.search(r'zericatalog/artwork/\d+/creation".*?zericatalog/date/([^"]+)"', x, re.S)
        date_text = urllib.parse.unquote(dt.group(1)) if dt else None
        p = parse_time(date_text.replace("sec-", "sec. ").upper().replace("SEC. ", "") + " w." if date_text and date_text.startswith("sec-") else date_text) if date_text else None
        date = [p["start"], p["end"], p["kind"]] if p and p["kind"] != "unparsed" and p["start"] and p["end"] else None
        kind = re.search(r'zericatalog/artwork/\d+".*?<rdfs:label xml:lang="en">(painting|drawing|sculpture|fresco|[a-z ]{3,30})</rdfs:label>', x, re.S)
        authors = list(dict.fromkeys(re.findall(r'zericatalog/artwork/\d+/authorship/([^"/]+)"', x)))
        cre = []
        for slug in authors[:3]:
            a = artists.get(slug)
            if not a:
                continue
            q = a["wikidata"]
            key = known.get(q) or known.get(f"ulan:{a['ulan']}") or (f"wd:{q}" if q else classify(a["name"])["name_key"])
            cre.append({"qid": q, "name": a["name"], "key": key})
        kept.append({
            "id": f"zeri-{aid}", "dataset": "zeri", "source_id": "zeri",
            "source_url": f"https://catalogo.fondazionezeri.unibo.it/scheda/opera/{aid}/", "qid": None, "title": title,
            "links": None, "creators": cre, "date": date, "date_text": date_text, "approx": False,
            "holding": "Fototeca Zeri (photographic record)", "object_type": "painting" if not kind else
            {"painting": "painting", "drawing": "drawing", "sculpture": "sculpture", "fresco": "wall-painting"}.get(kind.group(1), "painting"),
            "instance_of": kind.group(1) if kind else None, "image": None, "subjects": sorted(slugs), "iconclass": codes})
    wdh.log(f"kept {len(kept)} Zeri artworks; dropped {dict(dropped)}")

    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        for r in kept:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    new_q = {c["qid"] for r in kept for c in r["creators"] if c["qid"] and c["qid"] not in known}
    creators = wdh.creator_details(new_q) if new_q else {}
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
    wdh.log(f"wrote {len(kept)} -> {OUT}; {len(creators)} new creators -> {OUT_CRE}")


if __name__ == "__main__":
    main()
