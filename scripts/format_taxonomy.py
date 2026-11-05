#!/usr/bin/env python3
"""Rewrite taxonomy/segments.json in a stable, hand-editable layout: one line per leaf theme."""
import json
import os
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "taxonomy", "segments.json")


def dump(node, ind):
    pad = "  " * ind
    if "children" not in node:
        return pad + json.dumps(node, ensure_ascii=False)
    head = {k: v for k, v in node.items() if k != "children"}
    lines = [pad + "{"]
    for k, v in head.items():
        lines.append(f"{pad}  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
    kids = ",\n".join(dump(c, ind + 2) for c in node["children"])
    lines.append(f'{pad}  "children": [\n{kids}\n{pad}  ]')
    lines.append(pad + "}")
    return "\n".join(lines)


tax = json.load(open(PATH, encoding="utf-8"))
head = {k: v for k, v in tax.items() if k != "segments"}
out = ["{"] + [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False, indent=2).replace(chr(10), chr(10) + '  ')}," for k, v in head.items()]
out.append('  "segments": [\n' + ",\n".join(dump(s, 2) for s in tax["segments"]) + "\n  ]\n}\n")
text = "\n".join(out)
assert json.loads(text) == tax, "formatting changed content"
open(PATH, "w", encoding="utf-8").write(text)
print(f"formatted {PATH}: {text.count(chr(10))} lines")
