# Decisions Log

Newest first. Each entry records what was decided, why, and where it is implemented.

## 2026-11-05 (morning): Hosting, French museums

| # | Decision | Implementation |
|---|---|---|
| D32 | **Wikidata works open as images.** A Wikidata record with a Commons image opens Commons' full-screen viewer (File page plus `#/media/`) from the "View the image" button and the thumbnail; the Wikidata record is a secondary link. | `web/js/app.js` (`commonsViewer`) |
| D31 | **Fame: own renown first, attributions discounted.** Score = 0.40 × (the work has its own evidence) + 0.48 × work fame + 0.12 × highlight + 0.35 × artist fame × medium weight × attribution weight. Before, `max(work, 0.7 × artist)` put 91% of the top 2% there on the artist's name alone (an RKD "school of Rembrandt" sheet sat at the 98th percentile). Attribution qualifiers are normalised across languages (`etl/attribution.py`). RKD qualifiers that ICARUS dropped are restored from the RKD Knowledge Graph (17,216). Artists sharing a Wikidata or ULAN id are merged (2,231 spellings: Raffael, Raphael and RAPHAEL Urbin become Raphael). | `scripts/build_db.py` (`compute_fame`, `merge_same_person`, `apply_attributions`), `scripts/fetch_rkd_attributions.py`, `scripts/fetch_creator_labels.py` |
| D30 | **Joconde, the Musées de France catalogue** (Licence Ouverte 2.0, attribution only). 88,968 paintings, drawings, prints and sculptures whose French subject terms map to themes. The term list is reviewed by hand and scoped by category: a "Christ" inside a biblical scene isn't a devotional image, the eagle of St John isn't an eagle, a winter landscape isn't the personified Winter, and portrait sitters aren't subjects. Records already harvested from Wikidata (P347) are dropped. Artists: an existing name key; else Getty ULAN by name and life dates, which merges French name forms such as "Pierre Paul Rubens" into the existing artist; else the school as a low-confidence nationality proxy. | `scripts/import_joconde.py`, `taxonomy/joconde_terms.json` |
| D29 | **Host: Hetzner VPS** (replaces D28). Flat monthly price, so traffic can't run up per-query costs. Caddy provides HTTPS. The site is password-protected by a password-only sign-in page with a signed 30-day session cookie (no browser username prompt), with a per-client rate limit. | `deploy/`, `docs/deployment.md` |

## 2026-11-05 (night): More sources, layout, launch

| # | Decision | Implementation |
|---|---|---|
| D25 | **Curated Wikidata subjects for themes the Iconclass bridge misses.** Name search plus depicts counts, then a manual review: 96 subjects kept for 59 themes and 41 false matches rejected (e.g. "beer" for Bears, "Hitler" for Wolves, "piano" for Spiders). A painting depicting one inherits the theme's first notation. | `taxonomy/wikidata_subjects.json`, `scripts/find_wikidata_subjects.py` |
| D26 | **Fondazione Zeri** (CC BY-NC 4.0, accepted by the owner: the site is non-commercial). 10,171 artworks with Zeri's own Iconclass links. Artists by ULAN/Wikidata. Attribution is in "About the data". | `scripts/import_zeri.py` |
| D27 | **Art Institute of Chicago** (CC0). Subject terms are mapped to themes through theme names and aliases and the labels of Wikidata subjects with Iconclass. Prints, photographs and film are dropped, and so are works already harvested from Wikidata (P4610). | `scripts/fetch_aic.py` |
| D28 | **Host: Fly.io**, one always-on 1 GB machine, with the database built inside the image. GitHub Pages can't run the API. | `fly.toml`, `docs/deployment.md` |

## 2026-11-05 (later): Fame, "Notable works", teal palette

| # | Decision | Implementation |
|---|---|---|
| D21 | **Fame score.** It is max(work fame, 0.7 × artist fame), plus 0.12 for a museum highlight, halved for documentary photos. Work fame is log Wikipedia editions of the artwork: Wikidata/Met items, plus 1,612 ICARUS works Wikidata knows by RKDimages id or Rijksmuseum inventory number. Artist fame counts only creators with a verified visual-art occupation (P106), so patrons and authors credited as creators (Napoleon, Homer, Dickens) add nothing. | `scripts/fetch_fame.py`, `build_db.compute_fame()` |
| D22b | *Superseded 2026-11-05:* the default view is now **Everything + All collections**. Fame still orders the catalogue ("Iconic first"), and "Notable" is opt-in (`?notable=1`). | `Filters.all`, `#depth-switch` |
| D22 | **"Notable works" is a reversible view, not a deletion.** It is the documented top of the ranking: about 42% of records, because 58% have no measurable fame (anonymous, unlinked, undocumented). "Everything" is one click away, and every count says how many works are hidden. Measured effect: it does **not** reduce Germany's share (33.0% → 33.4%) and it sharpens the 1600s and Rubens. Fame is an ordering tool. Rebalancing comes from the new sources. | `Filters.all`, `#depth-switch` |
| D23 | **"Iconic first" is the default catalogue order**: fame, with at most 3 works per artist before the rest of that artist's works. Insecure links still sort last. | `queries._artworks_iconic()` |
| D24 | **Data colour is teal #138F80** (bars, heatmap, map, treemap, theme bars), with darker #0C6C61 for hover and white-text tiles. Navy stays for headings and gold for selections. | `web/css/app.css` tokens |

Measured rebalancing from 67,266 Wikidata paintings (share of located artworks):

- Germany 34.1% → 29.8% overall, Italy 13.4% → 16.3%.
- Christian Art: Italy now leads, 28.1% against Germany's 20.4%.
- Annunciation: Italy 45%.
- Paintings only: Italy 20.0%, Germany 18.1%.

## 2026-11-05: Second source and catalogue media filter

| # | Decision | Implementation |
|---|---|---|
| D17 | **Wikidata paintings as a counterweight to ICARUS's Northern-European print bias.** Paintings (P31 Q3305213) that depict (P180) or have as main subject (P921) a Wikidata subject carrying an Iconclass notation (P1256) inherit that notation, so the taxonomy, charts, map and search work unchanged. Wikidata's own Iconclass-tagged artworks (P1257, about 64k) were *not* used: they come from the same Dutch and Austrian collections. | `scripts/fetch_wikidata_artworks.py`, `build_db.py` (`artwork.dataset`) |
| D18 | **No double counting.** A painting is dropped when its RKDimages id (P350) matches an ICARUS RKD record, or when its collection is one ICARUS harvests (Rijksmuseum, Belvedere, Städel, NGA, Kassel). Wikidata artists merge with ICARUS artists through the Wikidata ids found during ULAN reconciliation. | same |
| D19 | **Source switch, default "All".** The Collections switch (All, ICARUS, Wikidata paintings) is a persistent preference that survives fresh searches. Copy says "within the collections shown". Wikidata records link out over https and show Commons thumbnails in the detail panel. | `web/js/app.js` |
| D20 | **Media buttons above the catalogue** use the shared object-type filter (brief: one filter state). Their counts ignore the media filter, so every medium stays selectable. | `renderMediaFilter()`, `queries.view()` |

Gaps to close:

- About 56 themes have no Wikidata subject with an Iconclass code yet (e.g. Owls). Add curated QIDs per theme (`wikidata` field) in a later taxonomy version.
- "depicts" tags are uneven by museum (Met 81%, Prado 54%, National Gallery London 34%, Capodimonte 12%).
- Generic subjects (tree, man, horse) pull in many landscape and portrait paintings. That's correct, but they weight Landscape & Nature.

## 2026-11-04 (night): Artist geography and the map

| # | Decision | Implementation |
|---|---|---|
| D12 | **Artist reconciliation is ULAN-keyed, with Wikidata for birthplaces.** ICARUS has no authority IDs. Names are matched to ULAN offline in four tiers: exact token-set name, then generation markers stripped ("(I)", "d. Ä."), then a one-token spelling variant that must also fit the life dates, then a prominence tie-break among homonyms. Every candidate is checked against the artworks' dates, and ULAN placeholder spans (>110 years) count as undated. Wikidata birthplaces come via ULAN ID (P245 → P19 → P625). Homonyms with no clear winner stay `ambiguous`, unless all of them were born in the same country. | `scripts/enrich_creators.py` → `data/enrichment/creator_geo.tsv` (committed) |
| D13 | **Present-day country by geometry.** Birthplace coordinates are placed in Natural Earth 10m polygons. Without coordinates, ULAN's present-day nation in the place string is used. Nationality is a proxy only, through a conservative map that leaves ambiguous labels such as Netherlandish or Prussian unmapped. It is off by default and shown as a lighter ring when switched on (brief §6). | `etl/geo.py`, `taxonomy/nationality_countries.json` |
| D14 | **Map frame: Europe and the Mediterranean.** 99.3% of located artist credits fall inside it. The rest appear in a "Beyond the map" list. The projection is Lambert azimuthal equal-area centred at 12°E 50°N. | `etl/geo.py: Viewport`, `scripts/build_basemap.py` |
| D15 | **Three map views.** *Countries*: national areas filled with a classed log scale, in decade classes (1–9, 10–99, …) so a 60:1 spread still reads. *Raised*: the same filled countries extruded into prisms with height ∝ artworks (linear, so the comparison stays honest), drawn back-to-front on a tilted map, with only viewer-facing walls in a per-country gradient. *Art centres*: proportional circles at birth cities, auto-framed to the area holding 97% of the selection's artworks. The Dorling cartogram was tried first and then replaced at the owner's request. | `web/js/charts.js: countryScale(), choropleth(), prism(), artCentres()` |

| D16 | **The top chart is "Themes across the centuries"** whenever the current level has sub-themes, and becomes the century bars for a single theme. Row-relative shading answers *when* each theme peaked, so margins keep the volume: a top histogram of all artworks per century (clickable to filter) and each row's size on the right. The chart ignores its own century filter and outlines the selected century in gold instead, so the context stays visible. Rows can be sorted by size or by peak century. | `web/js/charts.js: themeHeatmap()`, `server/queries.py: view()` |

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
