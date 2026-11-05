"""Present-day country geometry from Natural Earth: point-in-polygon, name lookup, projection.

Countries are keyed by Natural Earth ADM0_A3 (ISO-like; unlike ISO_A3 it is set for France and Norway).
The map projection is Lambert azimuthal equal-area centred on Europe (like EPSG:3035), so areas,
and therefore densities, are comparable across the map.
"""
import json
import math
import os
import re
import unicodedata

NE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "naturalearth")

PROJ_CENTER = (12.0, 50.0)  # lon, lat

# Names used by ULAN/TGN place strings (or common usage) that differ from Natural Earth's.
NAME_ALIASES = {
    "czech republic": "CZE", "czechia": "CZE", "united states": "USA", "united states of america": "USA",
    "england": "GBR", "scotland": "GBR", "wales": "GBR", "northern ireland": "GBR", "great britain": "GBR",
    "holland": "NLD", "the netherlands": "NLD", "russia": "RUS", "russian federation": "RUS",
    "macedonia": "MKD", "north macedonia": "MKD", "bosnia and herzegovina": "BIH", "bosnia-herzegovina": "BIH",
    "serbia": "SRB", "kosovo": "KOS", "moldova": "MDA", "ivory coast": "CIV", "côte d'ivoire": "CIV",
    "burma": "MMR", "myanmar": "MMR", "south korea": "KOR", "korea, south": "KOR", "north korea": "PRK",
    "vatican city": "VAT", "vatican city state": "VAT", "holy see": "VAT", "türkiye": "TUR", "turkey": "TUR",
    "tanzania": "TZA", "congo, democratic republic of the": "COD", "democratic republic of the congo": "COD",
    "congo": "COG", "republic of the congo": "COG", "syria": "SYR", "iran": "IRN", "laos": "LAO",
    "vietnam": "VNM", "viet nam": "VNM", "taiwan": "TWN", "palestine": "PSX", "west bank": "PSX",
    "east timor": "TLS", "timor-leste": "TLS", "cape verde": "CPV", "swaziland": "SWZ", "eswatini": "SWZ",
    "brunei": "BRN", "bolivia": "BOL", "venezuela": "VEN", "the bahamas": "BHS", "bahamas": "BHS",
    "gambia": "GMB", "the gambia": "GMB", "greenland": "GRL", "faroe islands": "FRO", "puerto rico": "PRI",
    "hong kong": "HKG", "macau": "MAC", "macao": "MAC", "monaco": "MCO", "san marino": "SMR",
    "liechtenstein": "LIE", "andorra": "AND", "malta": "MLT", "luxembourg": "LUX", "slovak republic": "SVK",
}


def fold(s):
    s = unicodedata.normalize("NFKD", s.casefold().strip())
    return "".join(c for c in s if not unicodedata.combining(c))


class Countries:
    def __init__(self, scale="10m"):
        path = os.path.join(NE_DIR, f"ne_{scale}_admin_0_countries.geojson")
        self.features = json.load(open(path, encoding="utf-8"))["features"]
        self.info, self.by_name, self.polys = {}, {}, []
        for f in self.features:
            p = f["properties"]
            code = p["ADM0_A3"]
            self.info[code] = {
                "code": code, "iso2": p.get("ISO_A2_EH") if p.get("ISO_A2_EH") not in (None, "-99") else None,
                "name": p["NAME"], "continent": p["CONTINENT"], "subregion": p.get("SUBREGION"),
                "label_lon": p.get("LABEL_X"), "label_lat": p.get("LABEL_Y"),
            }
            geom = f["geometry"]
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            for poly in polys:
                xs = [pt[0] for pt in poly[0]]
                ys = [pt[1] for pt in poly[0]]
                self.polys.append((min(xs), min(ys), max(xs), max(ys), poly, code))
        # a country's own names win over formal/sort names; sovereignty (e.g. Netherlands -> Sint Maarten) is not used
        for keys in (("NAME", "NAME_LONG", "ADMIN"), ("NAME_EN", "FORMAL_EN", "NAME_SORT")):
            for f in self.features:
                p = f["properties"]
                for key in keys:
                    if p.get(key):
                        self.by_name.setdefault(fold(p[key]), p["ADM0_A3"])
        for name, code in NAME_ALIASES.items():
            if code in self.info:
                self.by_name[fold(name)] = code

    def code_for_name(self, name):
        return self.by_name.get(fold(name)) if name else None

    def locate(self, lon, lat, tolerance=0.25):
        """ADM0_A3 of the country containing the point. Coastal points that fall just offshore
        snap to the nearest polygon within `tolerance` degrees."""
        for x0, y0, x1, y1, poly, code in self.polys:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _in_polygon(lon, lat, poly):
                return code
        best, best_d = None, tolerance
        for x0, y0, x1, y1, poly, code in self.polys:
            if x0 - tolerance <= lon <= x1 + tolerance and y0 - tolerance <= lat <= y1 + tolerance:
                d = _ring_distance(lon, lat, poly[0])
                if d < best_d:
                    best, best_d = code, d
        return best


def _in_polygon(x, y, poly):
    if not _in_ring(x, y, poly[0]):
        return False
    return not any(_in_ring(x, y, hole) for hole in poly[1:])


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def _ring_distance(x, y, ring):
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy + 1e-15)))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def laea(lon, lat, center=PROJ_CENTER):
    """Lambert azimuthal equal-area on the unit sphere -> (x, y), y pointing north."""
    lam, phi = math.radians(lon), math.radians(lat)
    lam0, phi0 = math.radians(center[0]), math.radians(center[1])
    k = math.sqrt(2 / (1 + math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(lam - lam0)))
    x = k * math.cos(phi) * math.sin(lam - lam0)
    y = k * (math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(lam - lam0))
    return x, y


class Viewport:
    """Projects lon/lat into SVG pixel coordinates for Europe and the Mediterranean.

    Edges are set in projected space: west of Ireland and Portugal, east of Anatolia, North Cape, the North African coast."""
    EDGES = {"west": [(-11.0, 52.0), (-10.0, 36.5)], "east": (44.5, 39.0), "north": (12.0, 71.2), "south": (12.0, 29.5)}

    def __init__(self, width=1000):
        self.x0 = min(laea(*pt)[0] for pt in self.EDGES["west"])
        self.x1 = laea(*self.EDGES["east"])[0]
        self.y_top = laea(*self.EDGES["north"])[1]
        self.y_bot = laea(*self.EDGES["south"])[1]
        self.scale = width / (self.x1 - self.x0)
        self.width = width
        self.height = round((self.y_top - self.y_bot) * self.scale)

    def project(self, lon, lat):
        x, y = laea(lon, lat)
        return round((x - self.x0) * self.scale, 1), round((self.y_top - y) * self.scale, 1)

    def contains(self, lon, lat):
        if not (-40 <= lon <= 70 and 20 <= lat <= 80):
            return False
        x, y = self.project(lon, lat)
        return 0 <= x <= self.width and 0 <= y <= self.height


def parse_place_country(place):
    """ULAN brief place 'Antwerp (Antwerpen province, Flanders, Belgium) (inhabited place)' -> 'Belgium'.
    A nation itself ('Italy (nation)') returns its own name. Returns (place_name, country_name)."""
    if not place:
        return None, None
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*\(([^()]*)\)\s*$", place)
    if m:
        return m.group(1).strip(), m.group(2).split(",")[-1].strip()
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", place)
    if m:
        name, kind = m.group(1).strip(), m.group(2).strip()
        if kind in ("nation", "country", "sovereign state", "former nation/state/empire"):
            return name, name
        return name, None
    return place, None
