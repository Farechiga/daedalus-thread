# Decisions Log

Newest first. Each entry records what was decided, why, and where it is implemented.

## 2026-11-04 (night): Artist geography and the map

| # | Decision | Implementation |
|---|---|---|
| D12 | **Artist reconciliation is ULAN-keyed, with Wikidata for birthplaces.** ICARUS has no authority IDs. Names are matched to ULAN offline in four tiers: exact token-set name, then generation markers stripped ("(I)", "d. Ä."), then a one-token spelling variant that must also fit the life dates, then a prominence tie-break among homonyms. Every candidate is checked against the artworks' dates, and ULAN placeholder spans (>110 years) count as undated. Wikidata birthplaces come via ULAN ID (P245 → P19 → P625). Homonyms with no clear winner stay `ambiguous`, unless all of them were born in the same country. | `scripts/enrich_creators.py` → `data/enrichment/creator_geo.tsv` (committed) |
| D13 | **Present-day country by geometry.** Birthplace coordinates are placed in Natural Earth 10m polygons. Without coordinates, ULAN's present-day nation in the place string is used. Nationality is a proxy only, through a conservative map that leaves ambiguous labels such as Netherlandish or Prussian unmapped. It is off by default and shown as a lighter ring when switched on (brief §6). | `etl/geo.py`, `taxonomy/nationality_countries.json` |
| D14 | **Map frame: Europe and the Mediterranean.** 99.3% of located artist credits fall inside it. The rest appear in a "Beyond the map" list. The projection is Lambert azimuthal equal-area centred at 12°E 50°N. | `etl/geo.py: Viewport`, `scripts/build_basemap.py` |
| D15 | **Two map views instead of a shaded map.** (1) *Countries*: a Dorling cartogram, with circle area ∝ artworks, collision-relaxed, and leader lines to the true location. This fixes small-but-huge countries such as the Netherlands and Belgium. (2) *Art centres*: proportional circles at birth cities, auto-framed to the area holding 97% of the selection's artworks. | `web/js/charts.js: cartogram(), artCentres()` |

Coverage after enrichment (artist credits, person and master creators):

- 65.0% located by birthplace
- 5.4% by nationality proxy
- 2.1% ambiguous
- 0.8% matched with no place
- 26.7% unmatched (mostly print publishers and firms, photographers, and rare names)

Of 35,132 creators, 16,249 have a country. In Christian Art, 42% of eligible artworks have a located artist (45% with nationality).

Gaps to close:

- The largest unmatched names, e.g. Jan Sadeler, Chrispyn de Passe, Balthasar Caimox, Raffael Santi/Sanzio.
- 138 Wikidata/ULAN birthplace conflicts to review (`notes` column).
- The nationality map's unmapped labels (`summary.json`).
- Firms that are still classed as persons (e.g. "Riffarth & Co").

## 2026-11-04 (later): Brand, search and catalogue design

| # | Decision | Implementation |
|---|---|---|
| D9 | **A search always starts fresh.** Picking any search suggestion, or pressing Enter for a title search, clears every existing filter. While filters are active, the dropdown says so. Drill-down links in the artwork panel still narrow the current view. | `web/js/app.js: pick()` |
| D10 | **Brand palette from the logo.** Navy `#022e3a` is used for bars, headings and data. Gold `#cf9203` is used only for active and selected states: the current segment tab, selected bars, active filter chips, the featured badge, and the thread rule on artworks. Gold is never used for body text (contrast). Dark mode uses a lighter navy tint for bars. | `web/css/app.css` tokens. Logo master in `assets/`, web sizes in `web/assets/` |
| D11 | **The artwork section is a catalogue set in type alone**, with no boxes or images. Each entry has a number, italic title, small-caps artist, old-style date and tracked object/source line. The detail panel is laid out as a museum label. System serif fonts only (no web fonts or CDNs). | `.result-list`, `.drawer` |

## 2026-11-04: Taxonomy v0.2 and data-handling rules

| # | Decision | Implementation |
|---|---|---|
| D1 | **All five segments ship:** Christian Art, Greek & Roman Mythology, Animals, Allegory & Symbols, Landscape & Nature. | `taxonomy/segments.json`, all segments `status: core` |
| D2 | **Christian Art gets the heaviest emphasis.** It is the default landing segment, is curated first and is listed first. | `display_order: 1`, `flags: ["primary"]` |
| D3 | **Multi-creator artworks count once per creator** in creator- and country-based charts. Each creator's contribution is included in the reported `n`, and the chart states that one artwork can count in several countries or artists. | Importer: `artwork_creator` is many-to-many. API: country/artist aggregates count (artwork, creator) pairs and also report unique artworks. |
| D4 | **No image archive.** The drill-down links out to the original record (`ref/url`) at the source institution, which shows the image. | Importer stores `source_url`. UI: "View at <source>" link. |
| D5 | **Putti stay inside Mythology** as a theme flagged `decorative`. | `classical-mythology → love-and-desire → putti` |
| D6 | **"Horses and Riding"** is the catch-all title and includes all riding (`46C131`, `46C132`) plus horses (`46C1314`). Donkeys that aren't being ridden keep their own theme. | `animals → horses-farm → horses-and-riding` |
| D7 | **Build now with the known taxonomy gaps** and close them in a later pass (list below). | |
| D8 | **Domain is `daedalus-thread.com`** (Squarespace Domains, registered 2026-11-05 UTC). The brief's spelling "deadalus-thread.com" and the spelling "daedelus-thread.com" are not registered. | DNS steps in `docs/deployment.md`. Waiting on the hosting choice. |

Implementation notes (same night):

- **BCE dates** ("27 v. Chr.", "50 BC") and early ranges starting before year 100 ("1/100") are left unparsed for now (798
  records), not misread as AD. Gap: add proper BCE support.
- **Search ranking:** a match on a theme's own name beats an alias match, curated themes rank above raw Iconclass subjects,
  and size breaks near-ties on a log scale. Guarded by `tests/search_golden.tsv` (26 queries, all passing).
- **Performance:** all 263 unfiltered views are precomputed at server start (about 10 s). Filtered drill-downs take 10–350 ms.
  Whole-segment views with extra filters take about 1 s. Optimise if that matters.

Still open from the profile (defaults applied until decided): reproduction photographs (PAUart, and Rijksmuseum/Bildindex
`photograph`/`Fotografie`) are flagged `date_semantics = reproduction` and left out of the timeline by default, with a toggle.

## Taxonomy gaps to close

From `scripts/evaluate_taxonomy.py`. Re-run it after every edit.

- **Too small (< 100):** Theseus (53). Options: merge into "Other Greek Heroes", or check for codes outside `94M`.
- **Small (100–299), 32 nodes:** mostly famous myths (Perseus, Orpheus, Daedalus & Icarus, Judgement of Paris, Daphne, Actaeon, Io,
  Prometheus, Lucretia) and some saints (Thomas, Stephen, Benedict, Cecilia, Agnes, Elisabeth, Dorothea, Helena, Anne).
  These are fine as low-n themes, but check them for missing codes such as keyed or bracketed variants.
- **Large "Other" remainders worth splitting:** Other Christian Art 14,019 · Other Saints 6,957 (lesser saints) · Other Birds 3,551 ·
  Other Old Testament 2,809 · Other Holy Women 2,287 · Other Animals 2,439 · Other Jupiter 1,940 · Other Insects 1,414 · Other Fabulous Creatures 1,389.
- **Subjects not yet given themes:** Wedding at Cana, Venus & Adonis, Mars & Venus, Lamb of God (in Christ devotional), Rosary/Sacred Heart,
  Pygmalion, Polyphemus, Seven Acts of Mercy (`11V`), Typology (`72`), Sibyls & Prophets (`11I1`).
- **Source-dominated themes** (top source > 50%): Fortune 70% and Vices 58% (Emblematica, which has no dates or creators), Sky & Weather 56% (Emblematica);
  Double-headed Eagle, Griffins, Ideal Landscapes, Boars and Unicorns (Kupferstichkabinett); Meleager and Hagar (RKD).
  Charts need a source-concentration warning.
- **Aliases:** add Polish, French and Latin forms systematically. Build `tests/search_golden.tsv`.
