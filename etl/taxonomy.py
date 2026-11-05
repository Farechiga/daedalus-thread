"""Load taxonomy/segments.json and match artworks to its nodes via the Iconclass tree.

Matching rules (see the file's own `rules`): a node with `include` matches an artwork when any
processed code equals or descends from an included notation and not from an excluded one.
Parents also contain everything their children match, and segments use `roots` as their include.
"""
import collections
import json
import os

PATH = os.path.join(os.path.dirname(__file__), "..", "taxonomy", "segments.json")


class Taxonomy:
    def __init__(self, iconclass, path=PATH):
        self.ic = iconclass
        self.raw = json.load(open(path, encoding="utf-8"))
        self.nodes, self.parent, self.depth, self.segment, self.order = {}, {}, {}, {}, []
        self.children = collections.defaultdict(list)
        self.problems = []
        for seg in self.raw["segments"]:
            self._walk(seg, None, 0, seg["id"], is_segment=True)
        self.inc_map, self.exc_map = collections.defaultdict(set), collections.defaultdict(set)
        for nid, node in self.nodes.items():
            for code in self.include(node):
                self.inc_map[code].add(nid)
            for code in node.get("exclude") or []:
                self.exc_map[code].add(nid)

    def _walk(self, node, parent, depth, segment, is_segment=False):
        nid = node["id"]
        if nid in self.nodes:
            self.problems.append(f"duplicate id: {nid}")
        self.nodes[nid] = node
        self.parent[nid], self.depth[nid], self.segment[nid] = parent, depth, segment
        self.order.append(nid)
        if parent:
            self.children[parent].append(nid)
        for key in ("include", "exclude", "roots"):
            for code in node.get(key) or []:
                if code not in self.ic.known:
                    self.problems.append(f"{nid}: {key} notation not in Iconclass tree: {code}")
        if not self.include(node) and not node.get("children"):
            self.problems.append(f"{nid}: has neither include nor children")
        for child in node.get("children", []):
            self._walk(child, nid, depth + 1, segment)

    @staticmethod
    def include(node):
        return node.get("include") or node.get("roots") or []

    def lineage(self, nid):
        out = []
        while nid:
            out.append(nid)
            nid = self.parent[nid]
        return out

    def match(self, codes):
        """Return (own_hits, matched, ann_hits) for a record's processed codes.

        own_hits: nodes matched directly by their include/exclude rule.
        matched:  own_hits plus all their ancestors (the full membership).
        ann_hits: per node, how many of the record's codes produced the hit.
        """
        own_hits, ann_hits = set(), collections.Counter()
        for code in set(codes):
            chain = self.ic.ancestors(code)
            inc, exc = set(), set()
            for c in chain:
                if c in self.inc_map:
                    inc |= self.inc_map[c]
                if c in self.exc_map:
                    exc |= self.exc_map[c]
            hit = inc - exc
            own_hits |= hit
            for h in hit:
                ann_hits[h] += 1
        matched = set()
        for h in own_hits:
            matched.update(self.lineage(h))
        return own_hits, matched, ann_hits

    def is_other(self, nid, own_hits, matched):
        """True when the artwork sits in `nid` only through nid's own include, in none of its children."""
        return nid in own_hits and bool(self.children[nid]) and not any(c in matched for c in self.children[nid])
