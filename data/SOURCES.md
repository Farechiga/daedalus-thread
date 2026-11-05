# Data Sources

Raw source files live under `data/raw/` and are **never edited in place**. Everything here is
reproducible with `scripts/fetch_sources.sh`. Fetched 2026-11-04.

| Source | Local path | Version / date | License | Role |
|---|---|---|---|---|
| ICARUS (Zenodo 18980670) | `raw/icarus/` | v1.0, published 2026-03-12 | CC BY 4.0 | Primary artwork records and Iconclass annotations |
| Iconclass core data (`iconclass/data`) | `raw/iconclass/data/` | commit in `raw/iconclass/SOURCE_COMMIT.txt` | CC0 1.0 | Notation hierarchy and labels for the taxonomy layer |
| Getty ULAN, relational tables | `raw/getty/ulan/` | `ulan_rel_0126` (Jan 2026 final release) | ODC-By 1.0 | Secondary artist authority: names, life dates, nationality, birth/death places |
| Getty TGN, relational tables | `raw/getty/tgn/` | `tgn_rel_0126` (Jan 2026 final release) | ODC-By 1.0 | Place hierarchy and coordinates for ULAN/Wikidata places |
| Getty AAT, relational tables | `raw/getty/aat/` | `aat_rel_0126` (Jan 2026 final release) | ODC-By 1.0 | Optional: nationality terms (ULAN `NATIONALITY` uses AAT-style codes) and object types |
| Natural Earth admin-0 countries | `raw/naturalearth/` | 5.2.0-pre (GitHub `nvkelso/natural-earth-vector` master) | Public domain | Present-day country boundaries: 10m for point-in-polygon, 50m/110m for the map |

Not downloaded on purpose:

- **ICARUS images** (`images.zip` + `images.z01`–`z04`, ~118 GB): out of initial scope per the brief.
  Records reference them through `ref/image/path`, for example `e0/c1/e0c1afaf0f97.jpg`.
- **Wikidata**: there is no bulk download. A full dump is >100 GB, and only the distinct ICARUS creators are needed.
  Phase 3 queries `https://query.wikidata.org/sparql` in batches and caches responses under `data/cache/wikidata/`.
- **Getty LOD N-Triples dumps** (`vocab.getty.edu/dataset/*/full.zip`): returned HTTP 500 at fetch time.
  Getty has stopped publishing XML and relational releases, so the Jan 2026 relational tables are the last ones.
  Future refreshes will need the monthly N-Triples dumps or the SPARQL endpoint.

## Checksums

ICARUS files are verified against the Zenodo record's MD5s (`raw/icarus/zenodo_record_18980670.json`).

## Format notes (from first inspection, to be confirmed in Phase 1 profiling)

- **ICARUS `data.jsonl`**: one object per line, `{"id": "<12 hex>", "entries": [{"path", "type", "value"|"url"}, ...]}`.
  There are 477,569 records, and the MD5 matches Zenodo. Share of records that have each path:
  `ref/url` 100%, `meta/iconclass/original` 100%, `meta/title` 99.5% (can repeat, one per language),
  `meta/collection` 94.3%, `meta/iconclass/processed` 94.1%, `ref/image/*` 91.7%, `meta/time` 84.5%,
  `meta/instance_of` 76.3%, `meta/creator` 61.7%, `meta/genre` 20.7%.
  `meta/creator` is a **free-text name** such as "Rubens, Pieter Paul", with no authority ID seen yet.
  `meta/time` is free text such as "1611-1612".
- **Getty `*.out`**: tab-delimited, no header row. Column definitions are in `*_rel_dd.pdf` next to each zip.
- **Iconclass `notations.txt`**: `$`-separated records with `N` (notation), `C` (children), and similar fields.
  Labels are in `txt/<lang>/` and keywords in `kw/<lang>/`.
- **Citations**: Iconclass asks for the citation in `raw/iconclass/data/README.md`.
  ICARUS and Getty both require attribution in the UI's methodology panel.
