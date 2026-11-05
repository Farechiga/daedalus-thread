"""Iconclass tree, labels and keywords loaded from the iconclass/data repository.

The hierarchy comes from notations.txt (N = notation, C = children), not from string
prefixes: "11HH" (female saints) is a sibling of "11H" (male saints), not a child.
Codes absent from the tree (free bracketed names such as "11H(JOHN THE BAPTIST)" or
"46C24(SHIP)") attach to their nearest listed ancestor.
"""
import glob
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "iconclass", "data")


class Iconclass:
    def __init__(self, root=ROOT, langs=("en",)):
        self.root = root
        self.parent = {}
        self.children = {}
        self.related = {}
        self.known = set()
        self._candidates = {}
        self._load_tree()
        self._pick_parents()
        self.labels = {lang: self._load_pipe("txt", lang, single=True) for lang in langs}
        self.keywords = {lang: self._load_pipe("kw", lang, single=False) for lang in langs}
        self._resolve_cache = {}

    def _load_tree(self):
        node, field = None, None
        with open(os.path.join(self.root, "notations.txt"), encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line == "$":
                    node, field = None, None
                    continue
                tag, _, value = line.partition(" ")
                if tag == "N":
                    node = value
                    self.known.add(node)
                    field = "N"
                elif tag in ("C", "K", "R", "T"):
                    field = tag
                    if tag == "C":
                        self._add_child(node, value)
                elif tag == ";" and field == "C":
                    self._add_child(node, value)

    def _add_child(self, parent, child):
        self._candidates.setdefault(child, []).append(parent)

    def _pick_parents(self):
        """C lists mix true children with cross-references (4k+ nodes have several "parents").
        The structural parent is the candidate whose notation is the longest prefix of the
        child ("X(...)" counts as a prefix of "X(NAME)"); the rest become `related` links.
        No prefix candidate -> first listed."""
        for child, cands in self._candidates.items():
            prefixed = [c for c in cands if c != child and (
                child.startswith(c) or (c.endswith("(...)") and child.startswith(c[:-4])))]
            parent = max(prefixed, key=len) if prefixed else cands[0]
            self.parent[child] = parent
            self.children.setdefault(parent, []).append(child)
            for c in cands:
                if c != parent:
                    self.related.setdefault(child, []).append(c)
        del self._candidates

    def _load_pipe(self, kind, lang, single):
        out = {}
        for path in sorted(glob.glob(os.path.join(self.root, kind, lang, f"{kind}_{lang}_*.txt"))):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    code, sep, text = line.rstrip("\n").partition("|")
                    if not sep:
                        continue
                    if single:
                        out.setdefault(code, text)
                    else:
                        out.setdefault(code, []).append(text)
        return out

    def resolve(self, code):
        """Nearest notation that exists in the tree (the code itself when listed)."""
        if code in self.known:
            return code
        hit = self._resolve_cache.get(code)
        if hit is not None:
            return hit
        c = code
        result = None
        while c:
            if "(" in c and c.endswith(")"):
                base = c[: c.rindex("(")]
                placeholder = base + "(...)"
                if placeholder in self.known:
                    result = placeholder
                    break
                c = base
            else:
                c = c[:-1]
            if c in self.known:
                result = c
                break
        self._resolve_cache[code] = result
        return result

    def ancestors(self, code):
        """[code, parent, ..., top] using the real tree. An unlisted code is kept as the
        first element, followed by its nearest listed ancestor's chain; [code] if unresolvable."""
        node = self.resolve(code)
        chain = [] if node == code else [code]
        while node is not None:
            chain.append(node)
            node = self.parent.get(node)
        return chain

    def label(self, code, lang="en"):
        labels = self.labels[lang]
        if code in labels:
            return labels[code]
        if "(" in code and ")" in code:  # free bracketed name: "11H(GEORGE)" -> "<11H label>: GEORGE"
            base = code[: code.index("(")]
            name = code[code.index("(") + 1: code.rindex(")")]
            base_label = labels.get(base) or labels.get(base + "(...)", base)
            return f"{base_label}: {name}"
        return None
