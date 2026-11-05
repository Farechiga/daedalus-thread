#!/usr/bin/env python3
"""Build web/assets/basemap.json: Natural Earth countries projected (LAEA, Europe) and simplified
for the Europe + Mediterranean map, plus one anchor point per country for proportional symbols.

    python3 scripts/build_basemap.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from etl.geo import NE_DIR, Viewport  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "web", "assets", "basemap.json")
TOLERANCE = 0.7   # px, Douglas-Peucker
MARGIN = 40       # px of geometry kept beyond the frame
ANCHOR_INSET = 18  # px: anchors clamped inside the frame


def simplify(pts, tol):
    if len(pts) < 4:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    # a closed ring starts and ends on the same point: split it at the farthest vertex first
    far = max(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - pts[0][0], pts[i][1] - pts[0][1]))
    keep[far] = True
    stack = [(0, far), (far, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, None
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def main():
    v = Viewport(width=1000)
    feats = json.load(open(os.path.join(NE_DIR, "ne_50m_admin_0_countries.geojson"), encoding="utf-8"))["features"]
    countries, anchors, in_view = [], {}, []
    for f in feats:
        p = f["properties"]
        code = p["ADM0_A3"]
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        parts, visible = [], False
        for poly in polys:
            ring = poly[0]
            if not any(-45 <= lon <= 80 and 15 <= lat <= 85 for lon, lat in ring):
                continue  # far away: skip before projecting (LAEA degenerates near the antipode)
            pts = [v.project(lon, lat) for lon, lat in ring]
            xs, ys = [x for x, _ in pts], [y for _, y in pts]
            if max(xs) < -MARGIN or min(xs) > v.width + MARGIN or max(ys) < -MARGIN or min(ys) > v.height + MARGIN:
                continue
            if max(xs) >= 0 and min(xs) <= v.width and max(ys) >= 0 and min(ys) <= v.height:
                visible = True
            pts = simplify(pts, TOLERANCE)
            if len(pts) < 4:
                continue
            parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        if not parts:
            continue
        countries.append({"code": code, "name": p["NAME"], "d": "".join(parts)})
        if visible:
            in_view.append(code)
            x, y = v.project(p["LABEL_X"], p["LABEL_Y"])
            anchors[code] = [round(min(max(x, ANCHOR_INSET), v.width - ANCHOR_INSET), 1),
                             round(min(max(y, ANCHOR_INSET), v.height - ANCHOR_INSET), 1)]
    out = {"width": v.width, "height": v.height, "projection": "LAEA centred 12°E 50°N",
           "source": "Natural Earth 1:50m admin-0 countries (public domain)",
           "countries": countries, "anchors": anchors, "in_view": sorted(in_view)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(countries)} countries ({len(in_view)} in view) -> {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
