#!/usr/bin/env python3
"""Golden-query test for autocomplete: python3 tests/test_search.py [db]. Exit code = failures."""
import os
import sqlite3
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "server"))
from queries import Queries  # noqa: E402

db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "db", "daedalus.sqlite")
q = Queries(sqlite3.connect(f"file:{db}?mode=ro", uri=True))
fails = 0
for line in open(os.path.join(ROOT, "tests", "search_golden.tsv"), encoding="utf-8"):
    if not line.strip() or line.startswith("#"):
        continue
    query, kind, want = line.rstrip("\n").split("\t")
    loose = want.startswith("~")
    want = want.lstrip("~")
    groups = q.suggest(query)["groups"]
    candidates = [i for g in (groups[:3] if loose else groups[:1]) for i in (g["items"] if loose else g["items"][:1])]
    ok = any(i["kind"] == kind and want in (i["ref"], i["label"]) for i in candidates)
    fails += not ok
    got = f"{groups[0]['items'][0]['kind']}:{groups[0]['items'][0]['label']}" if groups else "nothing"
    print(f"{'PASS' if ok else 'FAIL'}  {query!r:20} want {kind}:{want}  got {got}")
print(f"{fails} failure(s)")
sys.exit(fails)
