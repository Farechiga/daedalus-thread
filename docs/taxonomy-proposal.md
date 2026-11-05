# Taxonomy & Search Proposal (v0.1 draft)

*The draft taxonomy is in `taxonomy/segments.json`. It is validated and measured by `python3 scripts/evaluate_taxonomy.py`
(about 9 s), which writes `data/profile/taxonomy_eval.{json,tsv}` with per-node counts, coverage and a size verdict.
All numbers below are unique artworks.*

## 1. Principles

- **A few rich umbrellas, each with a shallow, recognisable hierarchy:** Segment → Group → Theme, with an optional
  sub-theme ("Story of David" → "David & Goliath").
- **Themes are human-readable names for sets of Iconclass notations.** Matching follows the Iconclass *tree*. A theme
  can combine branches: "Horses & Riders" = `46C1314` + `46C131`; "Dogs" = `34B11` + `43C1147` (hunting dogs).
- **Honest remainders.** Each segment declares `roots`. Artworks inside the roots but in no theme appear as
  *Other …* (e.g. 14,019 "Other Christian Art"), so totals always add up.
- **Overlap is expected.** A St Jerome with a lion belongs to *Saints → Jerome* and *Animals → Lions*. Parent counts
  are unique artworks, never sums of their children.
- **Size rules for display**, from `taxonomy_eval.tsv`:
  - **≥ 300** artworks (`ok`): full theme, all charts.
  - **100–299** (`small`): shown inside its parent with a low-n badge. Timeline by century only.
  - **< 100** (`too_small`): searchable, but folded into its parent's *Other* in charts.
- **Flags:** `decorative` (putti) is shown but not ranked first. `featured` (Daedalus & Icarus) goes on the landing story.

## 2. Recommended umbrellas

Coverage of the whole collection: the 3 core segments reach **226,701 artworks (47.5%)**. Adding both candidates
reaches 262,796 (55%). The remainder is mostly portraits, daily life, city views and ornament, which are good later segments.

| Segment | Status | Artworks | Named creator | Single-century date | Nodes ≥ 300 (of all below segment) |
|---|---|---:|---:|---:|---:|
| **Christian Art** | core | 150,293 | 55.5% | 67.2% | 109 of 122 |
| **Greek & Roman Mythology** | core | 40,090 (33,239 excluding putti-only) | 66.2% | 64.5% | 39 of 56 |
| **Animals** | core | 54,451 | 54.7% | 59.2% | 51 of 52 |
| Allegory & Symbols | candidate | 20,569 | 47.9% | 49.5% | 12 of 14 |
| Landscape & Nature | candidate | 53,353 | 58.0% | 58.2% | 12 of 12 |

**Recommendation:** launch with the three core segments, then add **Allegory & Symbols** as the fourth. It is what Iconclass
uniquely makes possible: Vanitas, the Dance of Death, the Five Senses, the Seasons and Fortune. It also teaches *how to
read a picture*, which suits classroom use. Hold **Landscape & Nature** for later, because its codes mostly describe backgrounds
(mountains behind a Crucifixion) and its themes are less distinctive. Candidates for after that: Music &
Performance (`48C7`, `48C8`, `43C9`), War & Chivalry (`45`), Portraits & Historical Figures (`61B`).

## 3. Segment outlines (counts from the evaluation)

### Christian Art (150,293)
| Group | Artworks | Example themes (artworks) |
|---|---:|---|
| Life of the Virgin | 14,535 | Madonna and Child 8,547 · **Annunciation 2,338** · Joachim, Anna & Mary's Childhood 1,844 · Dormition/Assumption/Coronation 1,613 · Visitation 711 |
| Birth & Childhood of Christ | 9,631 | Nativity & Shepherds 3,101 · **Adoration of the Magi 2,274** · Holy Family 1,812 · Flight into Egypt 1,233 · Presentation 1,200 · Massacre of the Innocents 370 |
| Ministry of Christ | 7,458 | Teaching & Apostles 2,834 · Parables 2,313 · Miracles 1,915 · Baptism of Christ 685 |
| The Passion | 14,862 | **Crucifixion 4,231** · Gethsemane/Arrest/Trial 2,619 · Lamentation & Pietà 1,568 · Flagellation 1,473 · Carrying the Cross 1,300 · Last Supper 1,084 · Entombment 748 · Man of Sorrows 711 · Deposition 701 · Ecce Homo 590 |
| Resurrection & Last Things | 6,874 | Heaven/Hell/Purgatory 1,688 · Resurrection 1,165 · Appearances (Noli me tangere, Emmaus) 1,165 · Last Judgement 1,131 · Ascension & Pentecost 1,115 · Apocalypse 1,034 |
| Old Testament | 20,323 | Moses & Exodus 2,987 · Abraham 1,923 (incl. Sacrifice of Isaac 559) · **Story of David 2,181 (incl. David & Goliath 382, Bathsheba 291)** · Isaac & Jacob 1,210 · Daniel 1,065 (incl. Susanna 462) · Adam & Eve 1,033 · Joseph 996 · Creation 932 · Solomon 883 · Tobias 755 · **Noah 750** · Samson 619 · Judith 504 · Cain & Abel 392 · Esther 386 · Job 312 · Jonah 270 · Babel 239 · Ruth 142 |
| Saints | 33,995 | Apostles & Evangelists 8,528 (Peter 2,093, Paul 1,951) · Holy Men 12,329 (John the Baptist 2,923, Jerome 1,628, **Francis 1,262**, **George 939**, Sebastian 993) · Holy Women 8,171 (Catherine 1,744, Mary Magdalene 1,523, Barbara 866) |
| God, Angels & Demons | 22,255 | Angels 9,216 · Christ (devotional) 9,038 · God the Father 2,539 · Devils & Demons 2,145 |
| Church & Worship | 32,608 | Liturgy & Sacraments 15,203 · Clergy & the Church 13,654 · Prayer & Devotion 7,189 |

*Church & Worship* is large but print-heavy (portraits of clergy, liturgical scenes). It should be shown last in the segment.

### Greek & Roman Mythology (40,090)
| Group | Artworks | Example themes |
|---|---:|---|
| Gods of Olympus | 12,590 | Jupiter 2,724 (Loves of Jupiter 784: Danaë, Leda, Europa, Ganymede) · Venus 2,185 · Mercury 1,742 · Minerva 1,558 · Apollo 1,476 · Bacchus & Bacchanals 1,417 · Diana 1,137 · Mars 696 · Neptune 663 |
| Cupid & Love | 11,954 | Cupid 2,768 · Cupid & Psyche 319 · *Putti & Amoretti 9,111 (decorative)* |
| Nymphs, Satyrs & Sea Gods | 4,257 | Satyrs & Fauns 1,821 · Tritons/Nereids/Galatea 557 · Nymphs 505 · Muses 495 · Medusa 417 |
| Heroes & Heroines | 4,672 | **Hercules 1,526** · Perseus & Andromeda 257 · Argonauts 288 · Orpheus 224 · **Daedalus & Icarus 163 (featured)** · Meleager 158 · Narcissus 105 · *Theseus 53 (too small)* |
| Troy, Odyssey & Aeneid | 2,448 | Trojan War 1,253 · Aeneid 643 · Odyssey 321 · Judgement of Paris 289 |
| Metamorphoses | 1,686 | Io 265 · Actaeon 214 · Apollo & Daphne 110 |
| Legends & History of Antiquity | 7,202 | Roman deities & personifications 1,695 · Founding of Rome 588 · Alexander 417 · Caesar & Cleopatra 368 · Lucretia 230 |

Mythology is the smallest core segment, so many famous stories are 100–300 artworks. They stay visible under their group, with low-n badges.

### Animals (54,451)
| Group | Artworks | Example themes |
|---|---:|---|
| Horses & Farm Animals | 19,160 | **Horses & Riders 10,809** · Cows/Bulls/Oxen 3,366 · Sheep 2,053 · Goats 1,598 · Donkeys 1,369 · Poultry 1,151 · Pigs 700 |
| Wild Mammals | 11,176 | **Lions 3,519** · Deer 1,662 · Hares & Rodents 1,544 · Wolves & Foxes 1,076 · Monkeys 945 · Elephants 784 · Bears 660 |
| Birds | 11,242 | **Eagles 1,843** · Swans & Water Birds 1,291 · Songbirds 1,230 · Peacocks & Parrots 1,065 · Storks 901 · Doves 872 · **Owls 625** |
| Pets & Companions | 7,452 | **Dogs 6,423** · Cats 930 · Caged Birds 318 |
| Reptiles, Fish & Small Creatures | 6,978 | Insects 2,160 (Butterflies 746) · Snakes 1,709 · Fish 1,367 · Shells & Snails 938 |
| Fabulous Creatures | 3,617 | Dragons 894 · Mermaids & Sea Creatures 405 · Griffins 363 · Double-headed Eagle 328 · Unicorns 295 |
| People & Animals | 5,199 | Hunting 4,274 · Animals Attacking People 658 · Taming 380 |

Iconclass spreads animals across five branches (`25F` nature, `34` man & animal, `46C` riding, `47I` livestock,
`43C11` hunting). The theme layer gathers them into familiar groups.

## 4. Known data caveats per theme (from the evaluation)

- **Source-dominated themes:** Fortune (70% from one source), Vices (58%) and Vanitas (47%) come mostly from Emblematica Online,
  which has no creators or dates. Their timeline and map would be near-empty, so they should show the coverage warning.
- **Low creator coverage:** Heaven & Hell (28%), Devils (35%) and Argonauts (29%) are dominated by incunabula, manuscripts and emblems.
- **Chart readiness** means named creator *and* single-century date. It is typically 35–55% per theme. The map will be lower still
  until Phase 3 enrichment lands.

## 5. Search & autocomplete design

**Goal:** typing "verk", "st geo", "durer", "löwe" or "icarus" gives instant, grouped suggestions with counts. Picking
one *applies a filter*, so every number on the page stays meaningful. Everything runs on SQLite FTS5 with no extra
dependencies (FTS5, `unicode61 remove_diacritics 2`, prefix indexes and the trigram tokenizer were verified on SQLite 3.53).

**One `suggest` table, built at import:**

| Entity | Search terms come from | Example |
|---|---|---|
| Theme / group / segment | `label` + curated multilingual `aliases` in `segments.json` | "Verkündigung", "Boodschap aan Maria" → *The Annunciation (2,338)* |
| Iconclass subject | Labels in de/en/fr/it/nl/pl (all 13 languages are available) + Iconclass keywords (`kw/`), for the 20,596 codes in ICARUS and their ancestors | "pelican" → *25F36(PELICAN) (194)*, also pointing to its theme |
| Bracketed names | Name parsed from `11H(GEORGE)`, `98B(ALEXANDER THE GREAT)` | "george" → *Saint George & the Dragon* |
| Artist | Canonical name, all raw variants and swapped "First Last" order, later ULAN/Wikidata alternate names | "rubens" → *Peter Paul Rubens (2,739)* |
| Holding institution, object type, source | Cleaned display names | "rijks" → *Rijksmuseum* |
| Title words | Separate FTS5 index over all 600k title strings | Fallback: *Search titles for "…"* |

**Query path** (`/api/suggest?q=`, debounced about 120 ms):
1. A prefix match on the FTS5 `unicode61` index (accent-folded) gives the main results.
2. If there are fewer than 5 hits, fall back to the **trigram** index for matches in the middle of a word and near-misses ("unciat", "lowe").
3. Rank by match quality (label prefix > alias > keyword), then by log(artwork count). Return at most about 5 per group:
   **Themes · Subjects · Artists · Places/Collections**, each with its count.
4. Selecting a suggestion adds a filter chip. A free-text Enter runs the title search as its own clearly labelled filter.

**Quality guardrails:** keep a `tests/search_golden.tsv` of about 50 queries with expected top hits
("annunciation", "verkündigung", "pieta", "noah", "st george", "durer", "lion", "owl", "putti", "icarus") and run it in CI.
No stemming across languages. Curated aliases cover plurals and synonyms.

## 6. Decisions needed

1. **4th segment:** Allegory & Symbols (recommended) or Landscape & Nature, or launch with 3.
2. **Multi-creator prints on the map:** count an artwork in *each* creator's country (the total exceeds n, which needs explaining),
   or only the *first-listed* creator (simpler, but often the publisher)? Recommendation: each creator, with the
   chart labelled "artworks with at least one creator from …".
3. **Reproduction photographs** (PAUart, part of Rijksmuseum and Bildindex): leave them out of the timeline and artist charts by default, with a toggle?
4. **Putti:** keep them inside Mythology as a decorative theme (current draft), or leave them out of segment totals entirely?
5. **Horses & Riders** includes all riders (`46C131`), on the assumption that a rider implies a mount. Is that acceptable?
