#!/usr/bin/env bash
# Fetch the raw source data for Daedalus Thread into data/raw/.
# Re-runnable: curl resumes partial downloads (-C -) and checksums are verified.
# Excludes the ~118 GB ICARUS image archive (images.zip, images.z01-z04).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/data/raw"
fetch() { curl -sSL --retry 5 -C - -o "$2" "$1"; }

# --- ICARUS (Zenodo 18980670, CC BY 4.0) ---
ZEN="https://zenodo.org/api/records/18980670"
mkdir -p "$RAW/icarus"
cd "$RAW/icarus"
curl -sSL -o zenodo_record_18980670.json "$ZEN"
for f in data.jsonl train.txt val.txt test.txt; do
  fetch "$ZEN/files/$f/content" "$f"
done
python3 - <<'PY'
import hashlib, json, sys
rec = json.load(open("zenodo_record_18980670.json"))
want = {f["key"]: f["checksum"].split(":", 1)[1] for f in rec["files"]}
bad = 0
for name in ("data.jsonl", "train.txt", "val.txt", "test.txt"):
    h = hashlib.md5()
    with open(name, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    ok = h.hexdigest() == want[name]
    bad += not ok
    print(f"{'OK  ' if ok else 'FAIL'} {name} {h.hexdigest()}")
sys.exit(bad)
PY

# --- Getty ULAN / TGN / AAT final relational tables (Jan 2026, ODC-By 1.0) ---
for v in ulan tgn aat; do
  mkdir -p "$RAW/getty/$v"
  cd "$RAW/getty/$v"
  fetch "http://${v}downloads.getty.edu/VocabData/${v}_rel_0126.zip" "${v}_rel_0126.zip"
  fetch "http://www.getty.edu/research/tools/vocabularies/${v}/${v}_rel_dd.pdf" "${v}_rel_dd.pdf"
  unzip -o -q "${v}_rel_0126.zip" -d rel
done

# --- Iconclass core data (GitHub iconclass/data, CC0) ---
mkdir -p "$RAW/iconclass"
if [ -d "$RAW/iconclass/data/.git" ]; then
  git -C "$RAW/iconclass/data" pull -q --ff-only
else
  git clone -q --depth 1 https://github.com/iconclass/data.git "$RAW/iconclass/data"
fi
git -C "$RAW/iconclass/data" log -1 --format='%H %cI' > "$RAW/iconclass/SOURCE_COMMIT.txt"

# --- Natural Earth admin-0 countries (public domain) ---
NE="https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master"
mkdir -p "$RAW/naturalearth"
cd "$RAW/naturalearth"
for s in 10m 50m 110m; do
  fetch "$NE/geojson/ne_${s}_admin_0_countries.geojson" "ne_${s}_admin_0_countries.geojson"
done
curl -sSL -o VERSION.txt "$NE/VERSION"

echo "Done. See data/SOURCES.md for provenance and licenses."
