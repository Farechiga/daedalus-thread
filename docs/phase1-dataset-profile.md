# Phase 1: ICARUS Dataset Profile

*Generated 2026-11-04 from ICARUS v1.0 (Zenodo 18980670). Reproduce with `python3 scripts/profile_icarus.py`
(about 11 s). The machine-readable results are in `data/profile/profile.json`, with detail tables
`iconclass_nodes.tsv` and `creators.tsv`.*

## 1. Summary

| | |
|---|---|
| Artwork records | **477,569**, all with a unique 12-hex `id`. The train/val/test splits (382,057 / 47,756 / 47,756) cover every record exactly once. |
| Source databases | **19**, identified from the `ref/url` host. `meta/collection` is the *holding institution*, which is a different field. |
| Iconclass annotations | **1,328,417** processed (canonical) and 1,537,867 original. 20,596 distinct processed codes, and **every one resolves in the Iconclass tree**. |
| Records with ≥1 processed code | 449,460 (94.1%). The rest only had codes that ICARUS dropped during normalisation, mostly named-portrait codes like `61B2(NAME)`. |
| Codes per artwork | Median 2, mean 2.8, max 79. 35% have exactly one. |
| Named creator (not anonymous) | 258,141 records (54.1%) |
| Usable date | 401,819 records (84.1%). 332,706 (69.7%) fall within a single century. |
| Image in the archive | 437,779 (91.7%). The long side is ≤ 1,200 px, which is fine for thumbnails. |

**Implication:** subject (Iconclass) coverage is excellent. Creator and date coverage are moderate and vary
a lot by source. Every chart therefore has to report its own `n` and eligible subset, as the brief requires.
Artist-country coverage, which depends on creator coverage, will be the weakest dimension. Expect roughly 30–40% of
artworks per theme to be mappable until enrichment is complete.

## 2. Field coverage

| Field (`meta/…`) | Records | % | Notes |
|---|---:|---:|---|
| `title` | 475,142 | 99.5 | 96,107 records have several titles, usually translations (de/nl/en/pl). |
| `iconclass/original` | 477,569 | 100 | 203,285 values carry Iconclass *keys* such as `(+12)`. |
| `iconclass/processed` | 449,460 | 94.1 | Keys are stripped and bracketed names kept. Order is not meaningful, so there is **no "primary subject"**. |
| `collection` | 450,175 | 94.3 | 9,321 distinct strings that need cleanup ("HAB" vs "Herzog August Bibliothek"; "Illinois", "Glasgow"). |
| `time` | 402,473 | 84.3 | Free text in about 1,225 formats (see §5). |
| `instance_of` | 364,433 | 76.3 | 3,089 distinct values in several languages (`print`, `Druckgraphik`, `Druck`, `Print`…), so they need mapping to roughly 12 object types. |
| `creator` | 294,315 | 61.6 | 400,013 values. 75,396 records list several creators (see §4). |
| `genre` | 98,824 | 20.7 | Bildindex only (`Tafelmalerei`, `Zeichenkunst`…). |
| `ref/image/*` | 437,779 | 91.7 | Relative path into the 118 GB archive we didn't download, plus pixel size and bounding boxes. |

## 3. Sources: coverage differs sharply

| Source | Records | Creator named % | Date % | Iconclass % | Image % | Main object types |
|---|---:|---:|---:|---:|---:|---|
| Rijksmuseum | 124,716 | 42.1 | 99.9 | 98.9 | 100 | print, photograph, drawing |
| Bildindex | 99,046 | 68.4 | 76.5 | 82.3 | 100 | Gemälde, Druck, Zeichnung |
| Virtuelles Kupferstichkabinett | 72,642 | 75.7 | 98.7 | 98.9 | 68.5 | Druckgraphik |
| RKD | 38,154 | 100 | 100 | 98.4 | 100 | painting, drawing |
| Emblematica Online | 24,230 | **0** | **0** | 94.6 | 100 | emblems |
| BSB Incunabula | 22,987 | **0** | 100 | 89.4 | 100 | woodcuts in early printed books |
| REALonline | 17,751 | 24.7 | 100 | 98.6 | 100 | altarpieces, wall paintings |
| Bodleian Broadside Ballads | 16,900 | 16.1 | **0** | 94.1 | **0** | ballad woodcuts |
| Städel Museum | 12,629 | 99.1 | 100 | 99.3 | 99.9 | Zeichnung, Gemälde |
| PAUart | 11,618 | 100 ⚠ | 97.9 ⚠ | 99.9 | 99.9 | **photographs of artworks** |
| KB Medieval Manuscripts | 9,408 | **0** | **0** | 93.4 | 100 | illuminations |
| Artemis | 8,022 | 97.8 | 99.8 | 77.2 | 100 | |
| Belvedere | 5,742 | 95.7 | 89.5 | 99.9 | 100 | Gemälde, Zeichnung |
| Heartfield Online | 4,960 | 88.4 | 100 | 100 | 100 | photomontage, posters |
| Corpus Vitrearum | 4,640 | **0** | 98.3 | 97.9 | 100 | stained glass |
| Vitrosearch | 3,844 | 74.1 | 100 | 95.9 | 100 | stained glass |
| Kassel / NGA / Thüringen | 168 / 98 / 14 | 100 / 100 / 57 | 100 | 100 | 100 | |

**Two traps to handle in the importer:**

1. **PAUart dates and creators describe the photograph, not the artwork.** A Pinturicchio fresco appears as
   *creator "Alinari", date "4 ćw. XIX wieku"*. 53% of PAUart dates fall in the 1800s.
   Rijksmuseum (10,307 `photograph`) and Bildindex (`Fotografie`) have the same problem in part.
   → Add a per-source and per-object-type **`date_semantics`** setting (`object` / `reproduction`). Leave reproductions out of the
   timeline and artist charts by default, with a visible toggle.
2. **Prints list designer, engraver and publisher as undifferentiated creators.** 56% of Kupferstichkabinett records
   and 37% of Rijksmuseum records have multiple creators, and ICARUS has no role field. About 10.5k creator values are
   institutions or rulers acting as publishers or privilege holders ("Staten van Holland", "Lodewijk XIV",
   "Pauselijk hof", "… Verlag, Druck"). The Städel splits qualifiers into separate values ("Schule", "alternativ").

## 4. Creators

- 40,046 distinct named strings. Merging names that use the same words in a different order brings this to **≈35,500**:
  "Peter Paul Rubens" / "Rubens, Peter Paul", "Dürer, Albrecht" / "Albrecht Dürer" / "Dürer Albrecht (1471-1528)".
- The tail is very long: 20,156 names occur once, 1,319 creators have more than 50 works and 69 have more than 500.
- Anonymous-type values number 36,273 ("unbekannt", "anonymous", "anoniem", "nieokreślony", "unknown"), and they must be shown
  as *Unknown*, not as an artist. A further 4,800 are monogrammists or named masters ("Monogrammist HS (1530)",
  "Meister des Schottenaltars"). These are real but have no birthplace, so they become *Unknown geography*. 1,957 records
  carry qualified attributions ("Werkstatt", "Umkreis", "Schule", "nach").
- **No authority IDs.** Some names embed dates, "Campbell, Thomas, 1777-1844" (5,451 records), which helps
  name-and-date reconciliation.

**Phase 3 consequences:** reconcile about 35k name keys, not 400k values, prioritising the roughly 5k creators that cover
most artworks. ULAN `TERM.out` provides variant names. Decide how multi-creator works count on the map (see the open decisions in the
taxonomy proposal).

## 5. Dates

`etl/dates.py` parses German, Dutch, Polish, English and Latin forms conservatively. It returns an inclusive
`[start, end]` and leaves the bound open for "vor 1310" or "after 1626". It never narrows a century to a year.

| Outcome (per record) | Records | % |
|---|---:|---:|
| Bounded range or year | 393,544 | 82.4 |
| One open bound (before/after) | 8,275 | 1.7 |
| Unparsed | 654 | 0.1 |
| No date | 75,096 | 15.7 |

- Precision (per record): 189,096 give an exact year, 156.5k a span of 1–50 years, 44.5k a span of 51–100 years, and 3.5k more than 100.
  63,170 values are marked approximate ("c.", "um", "około", "?").
- **Century bucketing:** 332,706 records (69.7%) fall entirely within one century. Allowing midpoint assignment for spans of
  ≤ 50 years raises this to 345,630 (72.4%). The UI should label the second option as approximate.
- What's left unparsed is mostly style periods ("spätromanisch", 608) and BCE dates ("27 v. Chr./14"). BCE support is a small
  addition if antiquity becomes a focus.
- Distribution (single-century): 1400s 33k · 1500s 51k · **1600s 74k** · 1700s 52k · **1800s 76k** · 1900s 38k.
  It's print-heavy, so this shows the collections' shape, not art history's.

## 6. Iconclass

- All 20,596 processed codes resolve in the Iconclass tree (40,712 nodes, commit `737ce36`). Matching works on the
  *tree*: `11HH` (female saints) is a child of `11H`, and 4,462 nodes are also listed under other parents as
  cross-references, which `etl/iconclass.py` keeps as `related`.
- Bracketed names are rich: 134,897 annotations, such as `11H(GEORGE)`, `25F23(LION)` and `98B(ALEXANDER THE GREAT)`.
- Unique artworks per top-level division:

| Division | Artworks | % |
|---|---:|---:|
| 4 Society, Civilization, Culture | 265,674 | 55.6 |
| 2 Nature | 118,607 | 24.8 |
| 1 Religion and Magic | 100,834 | 21.1 |
| 3 Human Being | 96,012 | 20.1 |
| 7 Bible | 66,563 | 13.9 |
| 9 Classical Mythology & Ancient History | 40,090 | 8.4 |
| 5 Abstract Ideas | 26,216 | 5.5 |
| 6 History | 16,514 | 3.5 |
| 8 Literature | 3,159 | 0.7 |
| 0 Abstract Art | 1,890 | 0.4 |

- **Codes describe what is visible, including background details.** `25F23(LION)` (3,519) includes St Jerome's and St Mark's
  lions, and `25H11` mountains appear behind crucifixions. Labels should say "artworks in which X appears",
  not "artworks about X".
- One heavy outlier: `92D1916` *putti* is on 9,111 artworks, mostly ornamental prints, which is 23% of all mythology.

## 7. Recommendations for Phase 2 (importer)

1. Use `iconclass_processed` as the canonical subject set and keep `original`, with its keys, in a side table.
2. Derive `source_id` from the URL host (`etl/icarus.py: SOURCES`). Keep `collection` as *holding institution*.
3. Store the date as `date_text`, `date_start`, `date_end`, `date_kind`, `date_approx`, `century` (strict) and
   `century_mid` (span ≤ 50), plus `date_semantics` (object/reproduction).
4. Store creators as a many-to-many `artwork_creator(artwork_id, position, raw_name, name_key, is_anonymous,
   qualifier)`. Use `name_key` (token-set) as the reconciliation unit.
5. Normalise `instance_of` into about 12 object types (painting, print, drawing, photograph, manuscript illumination,
   stained glass, sculpture, book illustration, poster, emblem, broadside, other) through an editable mapping file.
6. Never drop a record for a missing field. Each chart filters to its own eligible subset.
