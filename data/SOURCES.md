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

Derived and committed:

| Output | Built by | Inputs | License note |
|---|---|---|---|
| `enrichment/creator_geo.tsv` | `scripts/enrich_creators.py` (batch, about 5 min on first run, cached afterwards) | ICARUS creators, Getty ULAN (Jan 2026), Wikidata SPARQL (CC0; responses cached in `cache/wikidata/`), Natural Earth | ULAN-derived fields: ODC-By, so attribute Getty |
| `sources/wikidata_paintings.jsonl.gz` | `scripts/fetch_wikidata_artworks.py` (about 1 h first run, cached in `raw/wikidata/`) | Wikidata SPARQL: paintings that depict or have as main subject one of about 1,400 subject items carrying an Iconclass notation (P1256) | CC0 |
| `enrichment/wikidata_creators.tsv` | same script | Wikidata creators of those paintings: birthplace coordinates, life dates, ULAN id. Present-day country from Natural Earth | CC0 |
| `sources/joconde_objects.jsonl.gz`, `enrichment/joconde_creators.tsv` | `scripts/import_joconde.py` (about 3 min; ULAN and Wikidata cached) | Joconde, Musées de France (`raw/joconde/joconde.csv`, 1.25 GB, https://ministere-culture.s3.sbg.io.cloud.ovh.net/POP/joconde.csv, data.gouv.fr dataset 5b448216a3a729752eb11d6f), subject terms mapped by `taxonomy/joconde_terms.json` | Licence Ouverte 2.0: attribute "Ministère de la Culture, base Joconde (POP)" |
| `enrichment/rkd_attributions.tsv` | `scripts/fetch_rkd_attributions.py` (about 4 min, cached in `raw/rkd/`) | RKD Knowledge Graph SPARQL (api.rkd.triply.cc): attribution qualifiers of ICARUS's RKDimages records, RKD artist ids mapped to Wikidata by P650 | RKD open data (CC BY 4.0 or more permissive per RKD); Wikidata CC0 |
| `enrichment/creator_labels.tsv` | `scripts/fetch_creator_labels.py` | Wikidata English labels for artists with several spellings | CC0 |
| `../web/assets/basemap.json` | `scripts/build_basemap.py` | Natural Earth 1:50m | Public domain |

Not downloaded on purpose:

- **ICARUS images** (`images.zip` + `images.z01`–`z04`, ~118 GB): out of initial scope per the brief.
  Records reference them through `ref/image/path`, for example `e0/c1/e0c1afaf0f97.jpg`.
- **Wikidata**: there is no bulk download. A full dump is >100 GB, and only the distinct ICARUS creators are needed.
  `scripts/enrich_creators.py` queries `https://query.wikidata.org/sparql` in batches of 200 ULAN ids. Responses are cached
  per id in `data/cache/wikidata/ulan_birthplaces.json`.
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
