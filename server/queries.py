"""Query layer: turns a filter state into SQL against data/db/daedalus.sqlite.

All aggregates are computed on the filtered artwork set and report their own n / eligible subset.
Reproductions (date_semantics = 'reproduction') are excluded from date- and creator-based charts
unless filters["repro"] is true (decision log, D3/D4 follow-ups).
"""
import json
import math
import re
import unicodedata

MAX_NODES = 4
CENTURY_RANGE = (1000, 2000)


class BadRequest(ValueError):
    pass


class Filters:
    """Parsed, validated filter state. Built from query parameters."""

    def __init__(self, params, known_nodes, known_types, known_sources):
        get = lambda k: (params.get(k) or [None])[0]  # noqa: E731
        self.nodes = [n for n in params.get("node", []) if n][:MAX_NODES]
        for n in self.nodes:
            if n not in known_nodes:
                raise BadRequest(f"unknown node: {n}")
        self.century = _int(get("century"))
        self.creator = _int(get("creator"))
        self.type = get("type")
        if self.type and self.type not in known_types:
            raise BadRequest(f"unknown type: {self.type}")
        self.source = get("source")
        if self.source and self.source not in known_sources:
            raise BadRequest(f"unknown source: {self.source}")
        self.code = get("code")
        if self.code and not re.fullmatch(r"[0-9A-Z(+).,'& -]{1,80}", self.code):
            raise BadRequest("bad code")
        self.q = (get("q") or "").strip()[:100] or None
        self.repro = get("repro") in ("1", "true")

    def as_dict(self):
        return {k: v for k, v in vars(self).items() if v not in (None, [], False)}

    def where(self, alias="a"):
        """SQL fragment + params restricting artwork alias `a` to the filtered set."""
        clauses, args = [], []
        for nid in self.nodes:
            clauses.append(f"{alias}.rid IN (SELECT artwork_rid FROM artwork_node WHERE node_id = ?)")
            args.append(nid)
        if self.century is not None:
            clauses.append(f"{alias}.century = ?")
            args.append(self.century)
        if self.type:
            clauses.append(f"{alias}.object_type = ?")
            args.append(self.type)
        if self.source:
            clauses.append(f"{alias}.source_id = ?")
            args.append(self.source)
        if self.creator is not None:
            clauses.append(f"{alias}.rid IN (SELECT artwork_rid FROM artwork_creator WHERE creator_id = ?)")
            args.append(self.creator)
        if self.code:
            clauses.append(f"{alias}.rid IN (SELECT xi.artwork_rid FROM iconclass_ancestor xa "
                           f"JOIN artwork_iconclass xi ON xi.notation = xa.notation WHERE xa.ancestor = ?)")
            args.append(self.code)
        if self.q:
            clauses.append(f"{alias}.rid IN (SELECT t.artwork_rid FROM artwork_title t WHERE t.id IN "
                           f"(SELECT rowid FROM title_fts WHERE title_fts MATCH ?))")
            args.append(fts_query(self.q, prefix=False))
        return (" AND ".join(clauses) or "1"), args


def _int(v):
    if v in (None, ""):
        return None
    try:
        return int(v)
    except ValueError:
        raise BadRequest(f"not an integer: {v}")


SYNONYMS = {"st": ("saint", "sankt", "sint", "san"), "saint": ("st", "sankt", "sint"), "sankt": ("saint", "st"),
            "sint": ("saint", "st"), "hl": ("saint", "heilige"), "mt": ("mount", "mont")}


def fts_query(text, prefix=True):
    """Safe FTS5 query: each word quoted; optional prefix match; a few abbreviations expanded (st -> saint)."""
    words = re.findall(r"\w+", text.casefold())[:8]
    if not words:
        return '""'
    star = "*" if prefix else ""
    parts = []
    for i, w in enumerate(words):
        last = i == len(words) - 1
        alts = (w,) + SYNONYMS.get(w, ())
        terms = [f'"{a}"' + (star if (last or a == w) else "") for a in alts]
        parts.append(terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")")
    return " AND ".join(parts)


def fold(s):
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def short_label(label):
    """Iconclass labels can run to a paragraph; keep the head for chips and suggestions."""
    if not label:
        return label
    head = re.split(r"; possible attributes|; '|\s~\s", label)[0]
    return head if len(head) <= 90 else head[:87].rstrip() + "…"


class Queries:
    def __init__(self, db):
        self.db = db
        self.nodes = {r[0]: r for r in db.execute(
            "SELECT id, segment_id, parent_id, depth, position, label, description, flags, n_artworks, n_other, note "
            "FROM taxonomy_node")}
        self.children = {}
        for nid, row in sorted(self.nodes.items(), key=lambda kv: (kv[1][4], kv[1][5])):
            self.children.setdefault(row[2], []).append(nid)
        self.types = {r[0]: r for r in db.execute("SELECT id, label, position, records FROM object_type")}
        self.sources = {r[0]: r for r in db.execute("SELECT id, name, country, host, records FROM source")}
        self.meta = {k: json.loads(v) for k, v in db.execute("SELECT key, value FROM meta")}
        self.total = self.meta["records"]

    def filters(self, params):
        return Filters(params, self.nodes, self.types, self.sources)

    # ---------- static-ish ----------
    def meta_payload(self):
        segs = [self._node_json(nid) for nid in self.children.get(None, [])]
        return {
            "total_artworks": self.total, "build": self.meta, "segments": segs,
            "object_types": [{"id": t[0], "label": t[1], "n": t[3]} for t in sorted(self.types.values(), key=lambda t: t[2])],
            "sources": [{"id": s[0], "name": s[1], "country": s[2], "n": s[4]} for s in
                        sorted(self.sources.values(), key=lambda s: -s[4])],
        }

    def _node_json(self, nid, n=None):
        r = self.nodes[nid]
        return {"id": nid, "segment": r[1], "parent": r[2], "depth": r[3], "label": r[5], "description": r[6],
                "flags": json.loads(r[7] or "[]"), "n": r[8] if n is None else n, "n_total": r[8],
                "has_children": bool(self.children.get(nid)), "note": r[10]}

    def path(self, nid):
        out = []
        while nid:
            out.append({"id": nid, "label": self.nodes[nid][5]})
            nid = self.nodes[nid][2]
        return out[::-1]

    # ---------- the main view ----------
    def view(self, f):
        where, args = f.where("a")
        focus = f.nodes[0] if f.nodes else None
        n = self.db.execute(f"SELECT count(*) FROM artwork a WHERE {where}", args).fetchone()[0]
        out = {"filters": f.as_dict(), "n": n, "total": self.total,
               "path": self.path(focus) if focus else [],
               "focus": self._node_json(focus) if focus else None}
        out["tree"] = self.tree(f, focus, where, args)
        out["timeline"] = self.timeline(f, where, args, n)
        out["artists"] = self.artists(f, where, args, n)
        out["types"] = self.group_counts("object_type", where, args, self.types, 1)
        out["sources"] = self.group_counts("source_id", where, args, self.sources, 1)
        out["heatmap"] = self.heatmap(f, focus, where, args)
        out["subjects"] = self.top_subjects(where, args, n)
        out["coverage"] = self.coverage(where, args, n)
        return out

    def tree(self, f, focus, where, args):
        kids = self.children.get(focus, []) if focus else self.children.get(None, [])
        if not kids:
            return {"children": [], "other": None}
        marks = ",".join("?" * len(kids))
        counts = dict(self.db.execute(
            f"SELECT n.node_id, count(*) FROM artwork_node n JOIN artwork a ON a.rid = n.artwork_rid "
            f"WHERE n.node_id IN ({marks}) AND {where} GROUP BY n.node_id", kids + args))
        other = None
        if focus and self.nodes[focus][9] is not None:
            other = self.db.execute(
                f"SELECT count(*) FROM artwork_node n JOIN artwork a ON a.rid = n.artwork_rid "
                f"WHERE n.node_id = ? AND n.is_other = 1 AND {where}", [focus] + args).fetchone()[0]
        children = [self._node_json(k, counts.get(k, 0)) for k in kids]
        if focus:  # keep curated order for segments; rank themes by count
            children.sort(key=lambda c: (-c["n"], c["label"]))
        return {"children": children, "other": other}

    def _object_clause(self, f):
        return "" if f.repro else " AND a.date_semantics = 'object'"

    def timeline(self, f, where, args, n):
        obj = self._object_clause(f)
        rows = self.db.execute(
            f"SELECT a.century, a.century_mid, a.date_start IS NOT NULL OR a.date_end IS NOT NULL, count(*) "
            f"FROM artwork a WHERE {where}{obj} GROUP BY 1, 2, 3", args).fetchall()
        strict, mid_only = {}, {}
        eligible = no_date = spans = 0
        for cent, mid, has_date, k in rows:
            eligible += k
            if cent is not None:
                strict[cent] = strict.get(cent, 0) + k
            elif mid is not None:
                mid_only[mid] = mid_only.get(mid, 0) + k
                spans += k
            elif has_date:
                spans += k
            else:
                no_date += k
        dated = sum(strict.values())
        excluded = n - eligible
        return {"by_century": sorted(strict.items()), "mid_extra": sorted(mid_only.items()),
                "n": dated, "eligible": eligible, "unknown": no_date, "spanning": spans,
                "excluded_reproductions": excluded}

    def artists(self, f, where, args, n, limit=15):
        obj = self._object_clause(f)
        top = self.db.execute(
            f"SELECT c.id, c.display_name, c.kind, c.life_dates, count(DISTINCT a.rid) k FROM artwork a "
            f"JOIN artwork_creator ac ON ac.artwork_rid = a.rid JOIN creator c ON c.id = ac.creator_id "
            f"WHERE {where}{obj} AND c.kind IN ('person', 'master') GROUP BY c.id ORDER BY k DESC LIMIT ?",
            args + [limit]).fetchall()
        stats = self.db.execute(
            f"SELECT count(*), sum(a.n_named_creators > 0), sum(a.n_creators > 0 AND a.n_named_creators = 0) "
            f"FROM artwork a WHERE {where}{obj}", args).fetchone()
        pairs = self.db.execute(
            f"SELECT count(*), count(DISTINCT ac.creator_id) FROM artwork a JOIN artwork_creator ac ON ac.artwork_rid = a.rid "
            f"JOIN creator c ON c.id = ac.creator_id WHERE {where}{obj} AND c.kind IN ('person', 'master')", args).fetchone()
        eligible, named, anon_only = stats[0], stats[1] or 0, stats[2] or 0
        return {"top": [{"id": r[0], "name": r[1], "kind": r[2], "life": r[3], "n": r[4]} for r in top],
                "eligible": eligible, "n": named, "anonymous_only": anon_only,
                "no_creator": eligible - named - anon_only, "creator_links": pairs[0], "distinct_creators": pairs[1],
                "excluded_reproductions": n - eligible}

    def group_counts(self, col, where, args, lookup, label_idx):
        rows = self.db.execute(f"SELECT a.{col}, count(*) FROM artwork a WHERE {where} GROUP BY 1 ORDER BY 2 DESC", args)
        return [{"id": k, "label": lookup[k][label_idx] if k in lookup else k, "n": v} for k, v in rows]

    def heatmap(self, f, focus, where, args):
        kids = self.children.get(focus, []) if focus else self.children.get(None, [])
        if not kids:
            return None
        obj = self._object_clause(f)
        marks = ",".join("?" * len(kids))
        cells = self.db.execute(
            f"SELECT n.node_id, a.century, count(*) FROM artwork_node n JOIN artwork a ON a.rid = n.artwork_rid "
            f"WHERE n.node_id IN ({marks}) AND a.century BETWEEN ? AND ? AND {where}{obj} GROUP BY 1, 2",
            kids + list(CENTURY_RANGE) + args).fetchall()
        return {"rows": [{"id": k, "label": self.nodes[k][5]} for k in kids],
                "cells": cells, "n": sum(c[2] for c in cells)}

    def top_subjects(self, where, args, n, limit=12):
        """Most frequent specific Iconclass codes in the set (unique artworks per code)."""
        if n > 60000:  # full-segment scans are fine but not needed on first paint
            limit = 10
        rows = self.db.execute(
            f"SELECT ai.notation, i.label_en, count(*) k FROM artwork a JOIN artwork_iconclass ai ON ai.artwork_rid = a.rid "
            f"JOIN iconclass i ON i.notation = ai.notation WHERE {where} GROUP BY ai.notation ORDER BY k DESC LIMIT ?",
            args + [limit]).fetchall()
        return [{"code": r[0], "label": short_label(r[1]) or r[0], "n": r[2]} for r in rows]

    def coverage(self, where, args, n):
        r = self.db.execute(
            f"SELECT sum(a.n_named_creators > 0), sum(a.date_start IS NOT NULL OR a.date_end IS NOT NULL), "
            f"sum(a.century IS NOT NULL), sum(a.date_semantics = 'reproduction'), sum(a.source_url IS NOT NULL) "
            f"FROM artwork a WHERE {where}", args).fetchone()
        named, dated, cent, repro, linked = (x or 0 for x in r)
        return {"n": n, "named_creator": named, "dated": dated, "single_century": cent,
                "reproductions": repro, "source_link": linked, "artist_country": None}

    # ---------- results & detail ----------
    def artworks(self, f, offset=0, limit=40, sort="date"):
        where, args = f.where("a")
        order = {"date": "a.date_start IS NULL, a.date_start, a.rid", "title": "a.title IS NULL, a.title COLLATE NOCASE",
                 "random": "(a.rid * 2654435761) % 1000003"}.get(sort, "a.rid")
        rows = self.db.execute(
            f"SELECT a.rid, a.id, a.title, a.date_text, a.date_start, a.date_end, a.century, a.object_type, a.source_id, "
            f"a.source_url, a.date_semantics, (SELECT group_concat(c.display_name, '; ') FROM artwork_creator ac "
            f"JOIN creator c ON c.id = ac.creator_id WHERE ac.artwork_rid = a.rid AND c.kind != 'anonymous') "
            f"FROM artwork a WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        return {"offset": offset, "limit": limit, "items": [{
            "id": r[1], "title": r[2], "date": r[3], "start": r[4], "end": r[5], "century": r[6],
            "type": self.types[r[7]][1] if r[7] in self.types else r[7], "source": self.sources[r[8]][1],
            "url": r[9], "reproduction": r[10] == "reproduction", "creators": r[11]} for r in rows]}

    def artwork(self, aid):
        a = self.db.execute("SELECT * FROM artwork WHERE id = ?", (aid,)).fetchone()
        if not a:
            return None
        cols = [d[0] for d in self.db.execute("SELECT * FROM artwork LIMIT 0").description]
        rec = dict(zip(cols, a))
        rid = rec.pop("rid")
        rec["titles"] = [t for (t,) in self.db.execute(
            "SELECT title FROM artwork_title WHERE artwork_rid = ? ORDER BY position", (rid,))]
        rec["creators"] = [{"raw": r[0], "qualifier": r[1], "id": r[2], "name": r[3], "kind": r[4], "life": r[5]}
                           for r in self.db.execute(
            "SELECT ac.raw_name, ac.qualifier, c.id, c.display_name, c.kind, c.life_dates FROM artwork_creator ac "
            "LEFT JOIN creator c ON c.id = ac.creator_id WHERE ac.artwork_rid = ? ORDER BY ac.position", (rid,))]
        rec["subjects"] = [{"code": r[0], "label": r[1], "label_short": short_label(r[1])} for r in self.db.execute(
            "SELECT ai.notation, i.label_en FROM artwork_iconclass ai LEFT JOIN iconclass i ON i.notation = ai.notation "
            "WHERE ai.artwork_rid = ? ORDER BY ai.notation", (rid,))]
        rec["iconclass_original"] = [c for (c,) in self.db.execute(
            "SELECT notation FROM artwork_iconclass_original WHERE artwork_rid = ?", (rid,))]
        nodes = [r[0] for r in self.db.execute("SELECT node_id FROM artwork_node WHERE artwork_rid = ?", (rid,))]
        leafish = [n for n in nodes if not any(self.nodes[c][2] == n for c in nodes)]
        rec["themes"] = [self.path(n) for n in sorted(leafish, key=lambda n: (self.nodes[n][1], self.nodes[n][3]))]
        rec["source"] = {"id": rec["source_id"], "name": self.sources[rec["source_id"]][1]}
        rec["object_type_label"] = self.types.get(rec["object_type"], (None, None))[1]
        return rec

    # ---------- search ----------
    def suggest(self, q, per_kind=5):
        q = q.strip()[:60]
        if len(q) < 2:
            return {"q": q, "groups": []}
        groups = {}
        order = ["segment", "theme", "subject", "artist", "object_type", "source"]
        sql = ("SELECT s.kind, s.ref, s.label, s.detail, s.weight, s.terms, bm25({t}) FROM {t} JOIN suggest s ON s.id = {t}.rowid "
               "WHERE {t} MATCH ? ORDER BY bm25({t}) LIMIT 400")
        rows = self.db.execute(sql.format(t="suggest_fts"), (fts_query(q),)).fetchall()
        if len(rows) < 5 and len(q) >= 3:
            rows += self.db.execute(sql.format(t="suggest_tri"), ('"' + q.replace('"', "") + '"',)).fetchall()
        qf = fold(q)
        seen = set()
        scored = []
        for kind, ref, label, detail, weight, terms, rank in rows:
            if (kind, ref) in seen or not weight:
                continue
            seen.add((kind, ref))
            names = [fold(t) for t in (terms or label or "").split(" ; ")] if kind != "subject" else [fold(label or "")]
            lab = fold(label or "")
            quality = (4 if lab.startswith(qf) else 3 if any(t.startswith(qf) for t in names)
                       else 2 if any(qf in t for t in names) else 1)
            scored.append((quality, weight, kind, ref, label, detail))
        scored.sort(key=lambda s: -(s[0] + 0.5 * math.log10(s[1] + 1)))  # match quality, then size (log-damped)
        for quality, weight, kind, ref, label, detail in scored:
            g = groups.setdefault(kind, [])
            if len(g) < per_kind:
                item = {"kind": kind, "ref": ref, "label": short_label(label) if kind == "subject" else label,
                        "detail": detail, "n": weight, "_q": quality}
                if kind in ("theme", "segment"):
                    item["path"] = [p["label"] for p in self.path(ref)]
                g.append(item)
        best = {k: max(i["_q"] for i in items) for k, items in groups.items()}
        # curated themes get a one-step boost over raw Iconclass subjects and other kinds
        boost = lambda k: best[k] + (1 if k in ("theme", "segment") and best[k] >= 2 else 0)  # noqa: E731
        ranked = sorted(groups, key=lambda k: (-boost(k), order.index(k)))
        for items in groups.values():
            for i in items:
                del i["_q"]
        return {"q": q, "groups": [{"kind": k, "items": groups[k]} for k in ranked]}
