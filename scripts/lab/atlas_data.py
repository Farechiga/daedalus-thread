#!/usr/bin/env python3
"""Snapshot for the Mnemosyne Atlas mockup (web/lab/atlas.html): per subject, its best-known works that have an
image, with century, artist and the artist's birth region. Run after build_db.py; writes web/lab/atlas-data.json."""
import json
import os
import re
import sqlite3

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DB = os.path.join(ROOT, "data", "db", "daedalus.sqlite")
PANELS = ["annunciation", "adoration-of-the-magi", "judith", "venus", "st-george", "st-jerome", "lions", "crucifixion"]
REGION = {"ITA": "Italy", "NLD": "Low Countries", "BEL": "Low Countries", "DEU": "German lands", "AUT": "German lands",
          "CHE": "German lands", "FRA": "France", "ESP": "Iberia", "PRT": "Iberia"}


def main():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = []
    for node in PANELS:
        label, desc, n = db.execute("SELECT label, description, n_artworks FROM taxonomy_node WHERE id = ?", (node,)).fetchone()
        rows = db.execute("""
            WITH w AS (
              SELECT a.rid, a.id, a.title, a.date_text, a.date_start, a.date_end, a.century, a.image_url, a.fame_score,
                     a.holding, c.display_name artist, g.country_code cc,
                     ROW_NUMBER() OVER (PARTITION BY COALESCE(a.primary_creator, -a.rid) ORDER BY a.fame_score DESC) rn
              FROM artwork a JOIN artwork_node an ON an.artwork_rid = a.rid AND an.node_id = ?
              LEFT JOIN creator c ON c.id = a.primary_creator
              LEFT JOIN creator_geo g ON g.creator_id = a.primary_creator AND g.proxy = 'birthplace'
              WHERE a.image_url IS NOT NULL AND a.century BETWEEN 1200 AND 1900)
            SELECT id, title, date_text, date_start, date_end, century, image_url, fame_score, holding, artist, cc
            FROM w WHERE rn <= 2 ORDER BY fame_score DESC LIMIT 90""", (node,)).fetchall()
        works = []
        for aid, title, dtext, ds, de, cent, img, fame, holding, artist, cc in rows:
            region = REGION.get(cc, "Elsewhere" if cc else None)
            if not region:
                continue
            m = re.search(r"Special:FilePath/([^?#]+)", img)
            works.append({"id": aid, "title": title, "date": dtext, "year": ds or de, "century": cent, "artist": artist,
                          "region": region, "fame": round(fame or 0, 3), "holding": holding,
                          "img": re.sub(r"\?width=\d+$", "?width=360", img).replace("/full/640,/", "/full/!400,400/"),
                          "view": f"https://commons.wikimedia.org/wiki/File:{m.group(1)}#/media/File:{m.group(1)}" if m else None})
        out.append({"id": node, "label": label, "description": desc, "n": n, "works": works[:60]})
        print(f"{node:24} {n:6} artworks, {len(works[:60])} pinned")
    json.dump({"panels": out}, open(os.path.join(ROOT, "web", "lab", "atlas-data.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
