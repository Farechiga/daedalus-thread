# Daedalus Thread

An interactive atlas of art through its subjects. Pick a segment (Christian Art, Greek & Roman Mythology, Animals,
Allegory & Symbols, Landscape & Nature), drill into themes such as *The Annunciation* or *David & Goliath*, and see
synchronized charts of when, where and by whom these subjects were made.

**Site:** https://daedalus-thread.com (in preparation)

Built on **ICARUS**, 477,569 artworks with 1,328,417 Iconclass annotations from 19 collections
([Zenodo 18980670](https://zenodo.org/records/18980670), CC BY 4.0). Artists are enriched from Wikidata and the Getty ULAN/TGN,
and country boundaries come from Natural Earth.

## Repository layout

| Path | What it is |
|---|---|
| `Deadalus_Thread_Project Overview.md` | Project brief (v0.1) |
| `docs/` | Dataset profile, taxonomy & search proposal, decisions log |
| `taxonomy/segments.json` | The human-readable taxonomy: segments → groups → themes → Iconclass notations |
| `etl/` | Stdlib-only parsers shared by every script (ICARUS records, dates, Iconclass tree) |
| `scripts/` | Fetching, profiling, taxonomy evaluation and formatting |
| `data/SOURCES.md` | Provenance, versions and licenses of every source |
| `data/raw/`, `data/profile/`, `data/db/` | Downloaded and generated data (git-ignored) |

## Getting started

Requires Python 3.11+ and about 6 GB of disk. No third-party packages are needed.

```sh
scripts/fetch_sources.sh               # download ICARUS metadata, Getty ULAN/TGN/AAT, Iconclass, Natural Earth (~5 GB unpacked)
python3 scripts/profile_icarus.py      # dataset profile -> data/profile/profile.json (~11 s)
python3 scripts/evaluate_taxonomy.py   # validate and measure taxonomy/segments.json (~9 s)
python3 scripts/format_taxonomy.py     # normalize segments.json layout after editing
```

## Editing the taxonomy

Each theme maps a readable name to Iconclass notations, for example
`{"id": "annunciation", "label": "The Annunciation", "include": ["73A5"], "aliases": ["Verkündigung", …]}`.
Matching follows the Iconclass tree, so a notation includes all of its descendants. After editing, run
`evaluate_taxonomy.py`. It rejects unknown codes and reports each theme's size and data coverage.

## Data & attribution

- ICARUS, CC BY 4.0
- Iconclass, CC0
- Getty Vocabularies (ULAN, TGN, AAT), ODC-By 1.0
- Natural Earth, public domain

All counts are distributions within the ICARUS collection, not definitive historical frequencies.

## License

Code is under the MIT License (see `LICENSE`). The data sources keep their own licenses, listed above.
