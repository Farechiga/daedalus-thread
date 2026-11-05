# Deadalus Thread
**Project Initialization Brief | v0.1**

**Website:** https://deadalus-thread.com  
**Purpose:** Interactive visual exploration of art through subjects, history, geography, and relationships.

## 1. Objective

Build a fast, elegant, single-pane browser for exploring historical artworks through a curated, expandable taxonomy of themes.

Users should be able to select a segment, drill into subjects, filter the underlying artwork collection, and switch between synchronized visualizations without leaving the page.

The flagship segment will be **Christian Art**, followed by Animals, with future expansion to mythology, nature, architecture, and other categories.

The experience should combine genuine research utility with enough visual appeal and simplicity for school-age learners.

## 2. Primary Dataset

**ICARUS: A Dataset for Iconographic Classification and Representation Understanding (2026)**

Source: https://zenodo.org/records/18980670

- 477,569 artwork records
- 1,328,417 Iconclass annotations
- 19 source collections
- Primary input: `data.jsonl` (628.8 MB)
- Exclude the approximately 118 GB image archive from initial scope.

Preserve original identifiers, classifications, and source attribution. Inspect the source schema before committing to assumptions about image URLs, artist identifiers, or field completeness.

## 3. Taxonomy and Segments

Create a configurable taxonomy layer based on the existing Iconclass classifications.

Examples:

**Christian Art**
- Old Testament → David and Goliath, Noah's Ark, Moses
- New Testament → Annunciation, Nativity, Crucifixion
- Saints → Saint George, Saint Francis

**Animals**
- Mammals → Dogs, Horses, Lions
- Birds → Eagles, Doves, Owls
- Other → Fish, Reptiles, Insects

These are illustrative structures, not yet verified Iconclass mappings.

Requirements:

- Preserve the original Iconclass identifiers.
- Maintain a separate, human-readable taxonomy that maps to those identifiers.
- Support multiple classifications per artwork.
- Allow artwork to belong to multiple segments.
- Store the taxonomy in editable JSON or another simple, portable format.
- Permit new segments without restructuring the application.

## 4. Artist and Geographic Enrichment

Enrich the distinct creator records, rather than issuing lookups for every artwork.

**Primary:** Wikidata  
https://www.wikidata.org/

**Secondary:** Getty Union List of Artist Names (ULAN)  
https://www.getty.edu/research/tools/vocabularies/ulan

**Geographic reference:** Getty TGN and Natural Earth.

Apply a consistent attribution hierarchy:

1. Artist birth country, using present-day geographic boundaries.
2. Artist nationality/citizenship when birthplace country is unavailable.
3. Unknown when reliable attribution is not possible.

Store the country value, evidence source, geographic proxy type, match confidence, and authority identifier separately.

Prioritize identifier-based artist matching, followed by cautious name-and-date reconciliation. Flag ambiguous matches for review rather than guessing.

Run enrichment as a reproducible batch process, not as live browser queries. Cache results for reuse and future updates.

## 5. Core Visualizations

All visualizations must share a common filter state, with consistent drill-down behavior.

| Visualization | Function |
|---|---|
| Ranked bar chart | Most common subjects, artists, categories |
| Timeline | Artwork frequency by century or period |
| Country map | Geographic distribution using artist-country attribution |
| Treemap | Hierarchical distribution of subjects |
| Heatmap | Compare subject frequency across centuries or countries |
| Co-occurrence network | Reveal subjects appearing together in artworks |
| Scatterplot / quadrants | Compare rigorously defined numeric measures |

Start with ranked bars, timelines, treemaps, heatmaps, and geographic visualization. Build the network and scatterplot modules once their interaction and axes are validated.

Clicking a chart element should filter the entire page. Provide Back, Reset Filters, and a persistent summary of active filters.

Artworks should be accessible through a results gallery and detail pane, with original source links or image thumbnails where reliably available.

## 6. Missing Data and Statistical Integrity

**Incomplete coverage must never prevent exploration.**

Each visualization should use the maximum eligible subset with the required fields available. Do not globally discard an artwork because it lacks information needed for another chart.

Requirements:

- Display `n` prominently for every visualization.
- Show the number of eligible records and percentage covered.
- Distinguish birth-country matches, fallback proxies, and unknown geography.
- Provide an explicit *Unknown* category where appropriate.
- Show data completeness and methodology in an accessible information panel.
- Never substitute invented values or silently infer missing attributes.
- Distinguish unique artwork counts from annotation counts.
- Handle uncertain historical dates without introducing false precision.
- Label results as distributions within the ICARUS collection, not definitive historical frequencies.

**Illustrative example:**

*Artist birthplace country: n = 568 of 912 eligible artworks (62% coverage).*

If birthplace data is missing, the user may choose to include clearly identified nationality proxies. The interface should communicate that the resulting measure has changed.

Low-coverage charts should remain accessible with a warning where analysis is still meaningful; otherwise show a clear explanation rather than an empty or misleading visualization.

## 7. Technical Architecture

**Prioritize stability, portability, and minimal dependencies.**

| Layer | Preferred approach |
|---|---|
| Frontend | Vanilla HTML5, CSS3, JavaScript ES modules |
| Charts | Native SVG, with Canvas where performance warrants |
| Database | SQLite, indexed for filtering and aggregation |
| Import / ETL | Python standard library |
| API | Small, dependency-light backend serving filtered results |
| Taxonomy | Version-controlled JSON |
| Country boundaries | Local simplified Natural Earth geographic data |
| Hosting | Static frontend with lightweight database/API service |

Avoid React unless interface complexity demonstrably justifies introducing it.

No third-party JavaScript libraries, external CDNs, browser-side model calls, or mandatory live data services in the initial release.

The browser must never load or parse the full 629 MB JSONL file. Import the source once into an indexed database and serve compact aggregated responses.

Maintain a clear separation between source data, enrichment tables, taxonomy configuration, query logic, and visualization components.

Use responsive layout and accessible controls for both desktop and classroom use.

## 8. Initial Development Sequence

**Phase 1 — Dataset profiling**

Download and inspect ICARUS. Document actual field coverage, unique creators, classifications, date quality, image references, and attribution structures.

**Phase 2 — Data foundation**

Build a repeatable JSONL-to-SQLite importer. Implement Iconclass mappings and the first two curated segments: Christian Art and Animals.

**Phase 3 — Enrichment**

Deduplicate and reconcile artist identities. Add geographic attributes, provenance, confidence indicators, and coverage reporting.

**Phase 4 — Single-pane browser**

Implement shared filters, ranked subject charts, timelines, geographic mapping, and artwork drill-down.

**Phase 5 — Advanced exploration**

Add treemaps, heatmaps, co-occurrence networks, and experimental scatterplots. Validate interpretations and statistical measures before publication.

## 9. Definition of Success

The first release should allow someone to:

1. Open deadalus-thread.com and select Christian Art or Animals.
2. Explore a meaningful, clearly labeled hierarchy of subjects.
3. Filter by subject, century, country, artist, and available metadata.
4. Instantly see synchronized visualizations.
5. Understand how many records support each visualization.
6. Drill down to individual artworks and available source information.
7. Explore without installing software, creating an account, or knowing how to code.

The implementation should remain maintainable by a small team or individual, with clear documentation and no dependency on a proprietary visualization service.

**Guiding principle:** Preserve the richness of the artwork collection while making both its patterns and its limitations visible, understandable, and enjoyable to explore.