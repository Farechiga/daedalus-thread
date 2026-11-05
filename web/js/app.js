import { artCentres, centuryLabel, choropleth, countryScale, donut, fmt, pct, prism, rankedBars, themeHeatmap, timeline, treemap } from "./charts.js";

const $ = (s) => document.querySelector(s);
const PARAMS = ["node", "century", "creator", "type", "source", "country", "code", "q", "ds", "notable", "repro", "nat"];
const FLAGS = ["repro", "nat", "notable"]; // display preferences that change the measure; kept across fresh searches
const state = { node: [], century: null, creator: null, type: null, source: null, country: null, code: null, q: null, ds: null, notable: false, repro: false, nat: false };
const labels = {}; // remembered display labels for chips: "creator:123" -> "Albrecht Dürer"
let meta = null, view = null, basemap = null, resultsOffset = 0, requestId = 0;
let heatSort = (() => { try { return localStorage.getItem("dt.heatSort") || "size"; } catch { return "size"; } })();
let mapMode = (() => { try { return localStorage.getItem("dt.mapMode") || "countries"; } catch { return "countries"; } })();

// ---------- URL <-> state ----------
function toQuery(s = state) {
  const p = new URLSearchParams();
  for (const n of s.node) p.append("node", n);
  for (const k of PARAMS.slice(1)) {
    if (FLAGS.includes(k)) { if (s[k]) p.set(k, "1"); continue; }
    if (s[k] !== null && s[k] !== undefined && s[k] !== "") p.set(k, s[k]);
  }
  return p.toString();
}
function fromQuery(qs) {
  const p = new URLSearchParams(qs);
  state.node = p.getAll("node");
  for (const k of PARAMS.slice(1)) state[k] = p.get(k);
  for (const k of FLAGS) state[k] = p.get(k) === "1";
  for (const k of ["century", "creator"]) state[k] = state[k] === null ? null : Number(state[k]);
}
function navigate(change, { replace = false } = {}) {
  Object.assign(state, change);
  const qs = toQuery();
  const url = qs ? `/?${qs}` : "/";
  if (replace) history.replaceState(null, "", url); else history.pushState(null, "", url);
  load();
}
let resizeTimer = null;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => view && render(), 200); });
window.addEventListener("popstate", () => { fromQuery(location.search); load(); });

async function api(path, params = "") {
  const r = await fetch(`/api/${path}${params ? "?" + params : ""}`);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}

// ---------- helpers ----------
const segOf = (id) => meta.segments.find((s) => s.id === id);
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined && kid !== false) e.append(kid.nodeType ? kid : String(kid));
  return e;
}
const nline = (n, of, extra = "") => `n = ${fmt.format(n)} of ${fmt.format(of)} (${pct(n, of)}%)${extra}`;

// ---------- load & render ----------
async function load() {
  const id = ++requestId;
  document.body.classList.add("loading");
  try {
    const v = await api("view", toQuery());
    if (id !== requestId) return;
    view = v;
    render();
    resultsOffset = 0;
    loadResults(false);
  } catch (e) {
    $("#summary").textContent = `Could not load: ${e.message}`;
  } finally {
    if (id === requestId) document.body.classList.remove("loading");
  }
}

function render() {
  const seg = view.path?.[0]?.id;  // multi-colour palettes tint bars by segment
  if (seg) document.documentElement.dataset.segment = seg; else delete document.documentElement.dataset.segment;
  renderSegments();
  renderThemes();
  renderTimeline();
  renderArtists();
  renderTreemap();
  renderSubjects();
  renderCountryMix();
  renderTypes();
  renderMediaFilter();
  renderSources();
  renderMap();
  renderStatus();  // after the charts, which register display labels (countries, artists, subjects) for the chips
  $("#repro-toggle").checked = state.repro;
  $("#nat-toggle").checked = state.nat;
  renderDatasetSwitch();
  for (const b of document.querySelectorAll("#depth-switch button")) b.setAttribute("aria-pressed", String(Boolean(b.dataset.notable) === state.notable));
}

function renderSegments() {
  const current = view.path[0]?.id;
  $("#segments").replaceChildren(...meta.segments.map((s) =>
    h("button", { "data-seg": s.id, "aria-current": s.id === current ? "true" : "false", onclick: () => navigate(blank({ node: [s.id] })) },
      s.label, h("small", {}, `${fmt.format(s.n)} artworks`))));
}

function blank(extra = {}) {
  return { node: [], century: null, creator: null, type: null, source: null, country: null, code: null, q: null, ...extra };
}

function renderThemes() {
  const crumbs = $("#crumbs");
  const path = view.path;
  crumbs.replaceChildren(h("button", { onclick: () => navigate(blank()) }, "All segments"),
    ...path.slice(0, -1).flatMap((p) => [h("span", { class: "sep" }, "›"),
      h("button", { onclick: () => navigate({ node: [p.id, ...state.node.slice(1)] }) }, p.label)]));
  const focus = view.focus;
  $("#themes-h").textContent = focus ? focus.label : "Choose a segment";
  $("#focus-desc").textContent = focus?.description || focus?.note || (focus ? "" :
    "Five ways into 477,569 artworks. Pick a segment, then drill into its themes.");
  const kids = view.tree.children;
  const max = Math.max(1, ...kids.map((k) => k.n), view.tree.other || 0);
  const items = kids.map((k) => h("li", {}, h("button", {
      onclick: () => navigate({ node: [k.id, ...state.node.slice(1)] }),
      title: k.n_total !== k.n ? `${fmt.format(k.n)} with current filters (${fmt.format(k.n_total)} in total)` : null },
    h("span", { class: "label" }, k.label, k.has_children ? h("span", { class: "chev" }, " ›") : null,
      k.flags.includes("decorative") ? h("span", { class: "badge" }, "decorative") : null,
      k.flags.includes("featured") ? h("span", { class: "badge gold" }, "featured") : null,
      k.n_total < 300 && k.n_total >= 100 ? h("span", { class: "badge warn", title: "Fewer than 300 artworks" }, "low n") : null,
      k.n_total < 100 ? h("span", { class: "badge warn", title: "Fewer than 100 artworks" }, "very low n") : null),
    h("span", { class: "count" }, fmt.format(k.n)),
    h("span", { class: "bar" }, h("i", { style: `width:${(100 * k.n) / max}%` })))));
  if (view.tree.other) {
    items.push(h("li", { class: "other" }, h("button", { title: "In this theme, but not in any of its sub-themes", disabled: true },
      h("span", { class: "label" }, `Other ${focus.label}`), h("span", { class: "count" }, fmt.format(view.tree.other)),
      h("span", { class: "bar" }, h("i", { style: `width:${(100 * view.tree.other) / max}%` })))));
  }
  if (!items.length && focus) items.push(h("li", { class: "focus-desc" }, "No sub-themes. See the charts and artworks for this theme."));
  $("#theme-list").replaceChildren(...items);
}

function renderStatus() {
  const chips = [];
  const add = (label, change) => chips.push(h("span", { class: "chip" }, label,
    h("button", { "aria-label": `Remove filter ${label}`, onclick: () => navigate(change) }, "×")));
  // the theme focus leads the chain (below the segment level); removing it steps up one level
  if (view.focus && view.path.length > 1) add(view.focus.label,
    { node: [view.path[view.path.length - 2].id, ...state.node.slice(1)] });
  state.node.slice(1).forEach((n, i) => add(`Also: ${labels["node:" + n] || n}`,
    { node: state.node.filter((_, j) => j !== i + 1) }));
  if (state.century !== null) add(`Century: ${centuryLabel(state.century)}`, { century: null });
  if (state.creator !== null) add(`Artist: ${labels["creator:" + state.creator] || "#" + state.creator}`, { creator: null });
  if (state.type) add(`Object: ${meta.object_types.find((t) => t.id === state.type)?.label || state.type}`, { type: null });
  if (state.source) add(`Source: ${meta.sources.find((s) => s.id === state.source)?.name || state.source}`, { source: null });
  if (state.country) add(`Artist born in: ${labels["country:" + state.country] || state.country}${state.nat ? " (or national of)" : ""}`, { country: null });
  if (state.code) add(`Subject: ${labels["code:" + state.code] || state.code}`, { code: null });
  if (state.q) add(`Title contains: “${state.q}”`, { q: null });
  if (state.repro) add("Documentary photos included", { repro: false });
  $("#chips").replaceChildren(...chips);
  $("#chain-n").textContent = `${fmt.format(view.n)} ${view.n === 1 ? "work" : "works"}`;
  $("#chips").lastElementChild?.scrollIntoView?.({ block: "nearest", inline: "end" });
  const c = view.coverage;
  $("#summary").replaceChildren(...[h("strong", {}, fmt.format(view.n)), `artworks`,
    view.focus ? ` in ${view.focus.label}` : " in the collection",
    ` · ${pct(c.dated, view.n)}% dated · ${pct(c.named_creator, view.n)}% with a named artist`,
    state.notable && view.n_everything > view.n ? h("span", { class: "depth-note" },
      ` · notable only (${fmt.format(view.n_everything - view.n)} hidden)`) : null].filter(Boolean));
  $("#reset-btn").disabled = !view.focus && !chips.length;
  $("#summary").title = `${fmt.format(view.n)} artworks match. Use “Everything” to include the lesser-known works.`;
}

const widthOf = (id) => Math.max(300, Math.round($(id).querySelector(".body").clientWidth || 520));
function card(id, nText, content, note) {
  const c = $(id);
  c.querySelector(".n").textContent = nText || "";
  const body = c.querySelector(".body");
  body.replaceChildren(...[content, note ? h("p", { class: "note" + (note.warn ? " warnline" : "") }, note.text) : null].filter(Boolean));
}
const empty = (text) => h("p", { class: "empty" }, text);

// The top card: themes across the centuries when the focus has sub-themes, otherwise the century bars.
function renderTimeline() {
  const t = view.timeline;
  const hm = view.heatmap;
  const useHeat = hm && hm.n > 0 && hm.rows.filter((r) => r.n > 0).length >= 2;
  $("#when-h").textContent = useHeat ? "Themes across the centuries" : "When";
  const sortCtl = $("#heat-sort");
  sortCtl.hidden = !useHeat;
  for (const b of sortCtl.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.sort === heatSort));
  const pickCentury = (c) => navigate({ century: state.century === c ? null : c });
  const notes = [];
  if (t.spanning) notes.push(`${fmt.format(t.spanning)} span more than one century (pale when the span is ≤ 50 years)`);
  if (t.unknown) notes.push(`${fmt.format(t.unknown)} undated`);
  if (t.excluded_reproductions) notes.push(`${fmt.format(t.excluded_reproductions)} documentary photographs excluded`);
  const lowCov = t.eligible && t.n / t.eligible < 0.4;
  const nText = t.eligible ? nline(t.n, t.eligible, " dated to a single century") : "";
  if (useHeat) {
    const svg = themeHeatmap(hm.rows, hm.cells, { timeline: t, selected: state.century, sort: heatSort, width: widthOf("#c-timeline"),
      onCol: pickCentury,
      onRow: (r) => navigate({ node: [r.id, ...state.node.slice(1)] }),
      onCell: (d) => navigate({ node: [d.id, ...state.node.slice(1)], century: d.century }) });
    const extra = [];
    if (svg.hiddenRows) extra.push(`${svg.hiddenRows} smaller theme${svg.hiddenRows > 1 ? "s" : ""} not shown`);
    card("#c-timeline", nText, svg, { text: "Each row is shaded relative to its own peak, to show when each theme was most popular. The bars on top count all artworks in the selection, and the column on the right is each theme's size. Click a century to filter, a cell to open that theme in that century, or a name to open the theme. " +
      [...extra, ...notes].join(" · ") + (notes.length || extra.length ? "." : ""), warn: lowCov });
    return;
  }
  card("#c-timeline", nText,
    t.n || t.mid_extra.length ? timeline(t.by_century, { width: widthOf("#c-timeline"), height: widthOf("#c-timeline") < 600 ? 180 : 210, extra: t.mid_extra, selected: state.century,
      onPick: (r) => pickCentury(r.c) }) : empty("No dated artworks in this selection."),
    notes.length ? { text: (lowCov ? "Low date coverage. " : "") + notes.join(" · ") + ".", warn: lowCov } : null);
}
for (const b of document.querySelectorAll("#depth-switch button")) b.addEventListener("click", () => navigate({ notable: Boolean(b.dataset.notable) }));
for (const b of document.querySelectorAll("#heat-sort button")) {
  b.addEventListener("click", () => {
    heatSort = b.dataset.sort;
    try { localStorage.setItem("dt.heatSort", heatSort); } catch { /* private mode */ }
    renderTimeline();
  });
}

function renderArtists() {
  const a = view.artists;
  for (const x of a.top) labels["creator:" + x.id] = x.name;
  const extra = a.creator_links > a.n ? ` · ${fmt.format(a.creator_links)} artist credits (works with several artists count once per artist)` : "";
  card("#c-artists", a.eligible ? nline(a.n, a.eligible, " with a named artist") : "",
    a.top.length ? rankedBars(a.top.map((x) => ({ ...x, label: x.name, sel: x.id === state.creator })), { width: widthOf("#c-artists"), labelWidth: Math.min(190, widthOf("#c-artists") * 0.42),
      onPick: (x) => navigate({ creator: state.creator === x.id ? null : x.id }) }) : empty("No named artists in this selection."),
    { text: `${fmt.format(a.anonymous_only)} anonymous, ${fmt.format(a.no_creator)} with no creator recorded${extra}.` });
}

function renderTreemap() {
  const kids = view.tree.children.filter((k) => k.n > 0);
  const items = kids.map((k) => ({ id: k.id, label: k.label, n: k.n }));
  if (view.tree.other) items.push({ id: null, label: `Other`, n: view.tree.other });
  const sum = items.reduce((s, d) => s + d.n, 0);
  $("#c-treemap").hidden = items.length < 2; // a single tile says nothing: hide the card, the next one moves up
  card("#c-treemap", sum ? `annotation-based · ${fmt.format(sum)} theme memberships (artworks can sit in several)` : "",
    items.length ? treemap(items, { width: widthOf("#c-treemap"), height: 300, onPick: (d) => d.id && navigate({ node: [d.id, ...state.node.slice(1)] }) })
      : empty("No sub-themes at this level."));
}

function renderSubjects() {
  const s = view.subjects;
  for (const x of s) labels["code:" + x.code] = x.label;
  card("#c-subjects", view.n ? `unique artworks per Iconclass code · n = ${fmt.format(view.n)}` : "",
    s.length ? rankedBars(s.map((x) => ({ ...x, label: `${x.label}`, sel: x.code === state.code })), {
      width: widthOf("#c-subjects"), labelWidth: Math.min(230, widthOf("#c-subjects") * 0.45), maxLabel: widthOf("#c-subjects") < 420 ? 22 : 36,
      onPick: (x) => navigate({ code: state.code === x.code ? null : x.code }) }) : empty("No subjects."));
}

// The leading artist countries, each a 100% bar split into the selection's top sub-themes (or subjects) + Other.
function renderCountryMix() {
  const m = view.country_mix;
  const c = $("#c-mix");
  c.hidden = !m;
  if (!m) return;
  c.querySelector("h3").textContent = m.kind === "theme" ? "Sub-themes by country" : "Subjects by country";
  const short = (t) => t.length > 34 ? t.slice(0, 33) + "…" : t;
  const pick = (code, i) => m.kind === "theme"
    ? navigate({ country: code, node: [m.categories[i].id, ...state.node.slice(1)] })
    : navigate({ country: code, code: m.categories[i].id });
  const rows = m.countries.map((row) => {
    const parts = [...row.parts.map((n, i) => ({ n, i, label: m.categories[i].label })), { n: row.other, i: "other", label: m.other_label }];
    const total = parts.reduce((sum, p) => sum + p.n, 0) || 1;
    return h("li", {},
      h("div", { class: "mix-head" },
        h("button", { class: "linkish", onclick: () => navigate({ country: state.country === row.code ? null : row.code }),
          title: `Filter to artists from ${row.name}` }, row.name),
        h("span", { class: "num" }, `${fmt.format(row.n)} works`)),
      h("div", { class: "mix-bar", role: "list" }, parts.filter((p) => p.n).map((p) => {
        const share = `${Math.round((100 * p.n) / total)}%`;
        const tip = `${row.name} · ${p.label}: ${fmt.format(p.n)} (${share})`;
        return p.i === "other" ? h("span", { class: "s-other", role: "listitem", style: `flex-grow:${p.n}`, title: tip })
          : h("button", { class: `s${p.i}`, role: "listitem", style: `flex-grow:${p.n}`, title: tip, "aria-label": tip, onclick: () => pick(row.code, p.i) });
      })));
  });
  const legend = h("ul", { class: "mix-legend" }, [...m.categories.map((cat, i) => h("li", {}, h("i", { class: `s${i}` }), short(cat.label))),
    h("li", {}, h("i", { class: "s-other" }), short(m.other_label))]);
  card("#c-mix", m.include_nationality ? "artist countries by birthplace or nationality" : "artist countries by birthplace",
    h("div", {}, h("ol", { class: "mix" }, rows), legend),
    { text: m.kind === "theme" ? "Each bar is 100% of that country's theme memberships; a work in two sub-themes counts in both. Click a band to open it for that country."
      : "This theme has no sub-themes, so its most frequent Iconclass subjects are shown instead. Click a band to filter." });
}

// Media buttons above the catalogue: the same object-type filter as the "Kinds of object" chart.
function renderMediaFilter() {
  const types = view.types.filter((t) => t.n > 0);
  const total = types.reduce((sum, t) => sum + t.n, 0);
  const btn = (id, label, n) => h("button", { type: "button", "aria-pressed": String((state.type || null) === id),
    onclick: () => navigate({ type: id }) }, label, h("span", { class: "num" }, fmt.format(n)));
  $("#media-filter").replaceChildren(btn(null, "All media", total), ...types.map((t) => btn(t.id, t.label, t.n)));
}

// Thin donut plus a legend that doubles as the click target list (slices are small; rows are easy to hit).
function donutChart(items, { onPick, centre }) {
  const total = items.reduce((sum, d) => sum + d.n, 0);
  const row = (d, i) => [h("i", { class: d.other || i > 8 ? "c-other" : `c${i}`, "aria-hidden": "true" }), h("span", { class: "lab" }, d.label),
    h("span", { class: "num" }, fmt.format(d.n)), h("span", { class: "pc" }, d.n && pct(d.n, total) < 1 ? "<1%" : `${pct(d.n, total)}%`)];
  return h("div", { class: "donut-wrap" }, donut(items, { onPick, centre }),
    h("ol", { class: "donut-legend" }, items.map((d, i) => h("li", {}, d.other ? h("span", { class: "row" }, row(d, i))
      : h("button", { class: "row", "aria-pressed": String(!!d.sel), onclick: () => onPick(d) }, row(d, i))))));
}

function renderTypes() {
  const items = view.types.filter((t) => t.n > 0).map((t) => ({ ...t, sel: t.id === state.type }));
  const sel = items.find((t) => t.sel);
  card("#c-types", view.n ? `n = ${fmt.format(view.n)}` : "",
    items.length ? donutChart(items, { onPick: (t) => navigate({ type: state.type === t.id ? null : t.id }),
      centre: sel ? { value: fmt.format(sel.n), caption: sel.label } : { caption: "artworks" } }) : empty("—"),
    { text: "Object types are normalised from each source's own (multilingual) terms." + (sel ? " Other kinds are shown for comparison." : "") });
}

function renderSources() {
  const top = view.sources[0];
  const dominated = top && view.n >= 50 && top.n / view.n > 0.5;
  const shown = view.sources.slice(0, 9).map((s) => ({ ...s, sel: s.id === state.source }));
  const rest = view.sources.slice(9);
  if (rest.length) shown.push({ label: `${rest.length} other collection${rest.length > 1 ? "s" : ""}`, n: rest.reduce((sum, s) => sum + s.n, 0), other: true });
  const sel = shown.find((s) => s.sel);
  card("#c-sources", view.n ? `n = ${fmt.format(view.n)}` : "",
    shown.length ? donutChart(shown, { onPick: (s) => navigate({ source: state.source === s.id ? null : s.id }),
      centre: sel ? { value: fmt.format(sel.n), caption: sel.label } : { caption: shown.length === 1 ? "one collection" : `${view.sources.length} collections` } }) : empty("—"),
    dominated ? { text: `${pct(top.n, view.n)}% of this selection comes from one source, so patterns may reflect that collection's focus.`, warn: true } : null);
}

function renderMap() {
  const g = view.geo;
  for (const b of document.querySelectorAll("#c-map .seg button")) b.setAttribute("aria-pressed", String(b.dataset.mode === mapMode));
  for (const c of g.countries) labels["country:" + c.code] = c.name;
  const measure = g.include_nationality ? "with an artist located by birthplace or nationality" : "with an artist of known birthplace";
  if (!g.n) {
    card("#c-map", g.eligible ? nline(0, g.eligible, ` ${measure}`) : "", empty("No artworks in this selection have a located artist."));
    return;
  }
  const pick = (code) => navigate({ country: state.country === code ? null : code });
  const scale = countryScale(g.countries.filter((c) => c.in_view).map((c) => c.n));
  const opts = { selected: state.country, showProxy: g.include_nationality, scale, onPick: (c) => pick(c.code) };
  const svg = mapMode === "centres" ? artCentres(basemap, g.places, { selected: state.country, onPick: (p) => pick(p.country) })
    : mapMode === "raised" ? prism(basemap, g.countries, opts) : choropleth(basemap, g.countries, opts);
  const range = (c) => c.hi === Infinity ? `${fmt.format(c.lo)}+` : `${fmt.format(c.lo)}–${fmt.format(c.hi - 1)}`;
  const swatches = h("div", { class: "swatches", role: "list", "aria-label": "Artworks per country" },
    scale.classes.map((c) => h("span", { role: "listitem" }, h("i", { style: `background:${c.color}` }), range(c))));
  const inView = g.countries.filter((c) => c.in_view);
  const beyond = g.countries.filter((c) => !c.in_view);
  const list = (rows) => h("ol", {}, rows.map((c) => h("li", {}, h("button", { "aria-pressed": String(c.code === state.country), onclick: () => pick(c.code) },
    h("span", {}, c.name), h("span", { class: "num" }, fmt.format(c.n))))));
  const side = h("div", { class: "map-side" },
    mapMode === "centres"
      ? h("div", { class: "legend" }, h("span", {}, h("i"), "Circle area = artworks by artists born there"))
      : [h("h4", {}, mapMode === "raised" ? "Artworks per country (height and shade)" : "Artworks per country"), swatches,
          g.include_nationality ? h("p", { class: "legend-note" }, "Includes nationality where the birthplace is unknown.") : null],
    mapMode === "centres"
      ? [h("h4", {}, "Leading art centres"), h("ol", {}, g.places.filter((p) => p.in_view).slice(0, 10).map((p) => h("li", {},
          h("button", { onclick: () => pick(p.country), title: `Filter to artists born in ${labels["country:" + p.country] || p.country}` },
            h("span", {}, p.name), h("span", { class: "num" }, fmt.format(p.n))))))]
      : [h("h4", {}, "Countries"), list(inView.slice(0, 12))],
    beyond.length ? [h("h4", {}, "Beyond the map"), list(beyond.slice(0, 8))] : null);
  const notes = [`${fmt.format(g.named_not_located)} by named artists not yet located`, `${fmt.format(g.anonymous_only)} anonymous`,
    `${fmt.format(g.no_creator)} with no creator recorded`];
  if (g.multi_country) notes.push(`${fmt.format(g.multi_country)} have artists from several countries and count once in each`);
  if (g.excluded_reproductions) notes.push(`${fmt.format(g.excluded_reproductions)} documentary photographs excluded`);
  const low = g.n / g.eligible < 0.25;
  card("#c-map", nline(g.n, g.eligible, ` ${measure}`), h("div", { class: "map-wrap" }, svg, side), {
    text: (low ? "Low coverage: read these proportions with care. " : "") + notes.join(" · ") +
      ". Present-day borders; birthplaces from Wikidata and the Getty ULAN.", warn: low });
}

// ---------- results & drawer ----------
async function loadResults(append) {
  const id = requestId;
  const sort = $("#sort").value;
  const data = await api("artworks", `${toQuery()}${toQuery() ? "&" : ""}offset=${resultsOffset}&limit=40&sort=${sort}`);
  if (id !== requestId) return;
  const items = data.items.map((a) => h("li", {}, h("button", { onclick: () => openArtwork(a.id),
      "aria-label": `${a.title || "Untitled"}${a.creators ? ", " + a.creators : ""}${a.date ? ", " + a.date : ""}` },
    h("span", { class: "no", "aria-hidden": "true" }),
    h("span", { class: "t" }, a.title || "Untitled"),
    h("span", { class: "a" + (a.creators ? "" : " unknown") }, a.creators ? a.creators.split("; ").join(" · ") : "Artist unknown"),
    a.date ? h("span", { class: "d" }, a.date) : null,
    h("span", { class: "m" }, a.type, " · ", a.dataset === "wikidata" ? `${a.holding || "collection unknown"} · via Wikidata` : a.source,
      a.reproduction ? h("span", { class: "repro" }, " · documentary photograph") : null))));
  if (append) $("#results").append(...items); else $("#results").replaceChildren(...items);
  if (!append && !items.length) $("#results").replaceChildren(h("li", { class: "empty" }, "No artworks match these filters."));
  $("#results-h").replaceChildren("The Works", h("span", { class: "tally" }, ` ${fmt.format(view.n)}`));
  $("#more-btn").hidden = resultsOffset + data.items.length >= view.n;
}
$("#more-btn").addEventListener("click", () => { resultsOffset += 40; loadResults(true); });
$("#sort").addEventListener("change", () => { resultsOffset = 0; loadResults(false); });

async function openArtwork(id) {
  const a = await api("artwork", `id=${encodeURIComponent(id)}`);
  const d = $("#drawer");
  const named = a.creators.filter((c) => c.kind && c.kind !== "anonymous");
  const byline = named.length ? named.map((c, i) => [i ? " · " : "",
    h("button", { class: "linkish", style: "font:inherit", onclick: () => { labels["creator:" + c.id] = c.name; closeDrawer(); navigate({ creator: c.id }); } }, c.name),
    c.qualifier ? h("span", { class: "life" }, ` (${c.qualifier})`) : null,
    c.life ? h("span", { class: "life" }, ` ${c.life}`) : null]) : ["Artist unknown"];
  const roles = a.creators.filter((c) => c.kind === "institution" || c.kind === "qualifier");
  const located = named.filter((c) => c.geo && c.geo.country);
  const geoLines = located.map((c) => h("li", {}, h("span", { class: "alt-title" }, c.name), " — ",
    c.geo.proxy === "birthplace" ? `born ${c.geo.place ? c.geo.place + ", " : ""}${c.geo.country_name}` : `${c.geo.country_name} (by nationality; birthplace unknown)`,
    h("br"), h("code", {}, [c.geo.evidence, c.geo.confidence ? `${c.geo.confidence} confidence` : null].filter(Boolean).join(" · ")), " ",
    c.geo.ulan ? h("a", { href: `https://vocab.getty.edu/page/ulan/${c.geo.ulan}`, target: "_blank", rel: "noopener noreferrer" }, "ULAN") : null,
    c.geo.ulan && c.geo.wikidata ? " · " : null,
    c.geo.wikidata ? h("a", { href: `https://www.wikidata.org/wiki/${c.geo.wikidata}`, target: "_blank", rel: "noopener noreferrer" }, "Wikidata") : null));
  const eyebrow = [a.object_type_label, a.century !== null && a.century !== undefined ? centuryLabel(a.century) : null, a.source.name].filter(Boolean).join(" · ");
  const wd = a.dataset === "wikidata";
  d.querySelector("#drawer-body").replaceChildren(...[
    a.image_url ? h("figure", { class: "thumb" }, h("img", { src: a.image_url, alt: a.title || "Artwork image", loading: "lazy" }),
      h("figcaption", {}, { met: "Image: The Metropolitan Museum of Art (Open Access)", aic: "Image: Art Institute of Chicago (CC0)" }[a.dataset] || "Image: Wikimedia Commons")) : null,
    h("p", { class: "eyebrow" }, eyebrow),
    h("h2", { id: "drawer-title" }, a.title || "Untitled"),
    h("hr", { class: "thread" }),
    h("p", { class: "byline" }, byline),
    h("p", { class: "dateline" }, a.date_text || "Undated", a.date_semantics === "reproduction" ? " (date of the photograph)" : ""),
    a.source_url ? h("a", { class: a.link_https ? "cta" : "cta insecure", href: a.source_url, target: "_blank", rel: "noopener noreferrer",
      "aria-describedby": a.link_https ? null : "link-warning" }, wd ? "View on Wikidata ↗" : a.dataset === "met" ? "View at The Met ↗" : a.dataset === "aic" ? "View at the Art Institute of Chicago ↗" :
      a.dataset === "zeri" ? "View the Zeri catalogue record ↗" : a.dataset === "joconde" ? "View the record on POP (Joconde) ↗" : `View image & record at ${a.source.name} ↗`) : null,
    a.source_url && !a.link_https ? h("p", { class: "link-warning", id: "link-warning", role: "note" }, h("span", { "aria-hidden": "true" }, "⚠"),
      h("span", {}, "Warning: link may not be safe",
        h("small", {}, `${a.source.name} uses an unencrypted http:// address, so your browser may warn you before opening it.`))) : null,
    h("dl", {},
      roles.length ? [h("dt", {}, "Also credited"), h("dd", {}, roles.map((c) => c.raw).join(" · "))] : null,
      h("dt", {}, "Object"), h("dd", {}, a.object_type_label || "—", a.instance_of ? ` · ${a.instance_of}` : ""),
      h("dt", {}, "Held by"), h("dd", {}, a.holding || "—"),
      h("dt", {}, "Source"), h("dd", {}, a.source.name),
      h("dt", {}, { wikidata: "Wikidata", met: "Met object", aic: "AIC object", zeri: "Zeri record", joconde: "Joconde ref." }[a.dataset] || "ICARUS id"),
      h("dd", {}, h("code", {}, a.dataset && a.dataset !== "icarus" ? a.id.slice(a.id.indexOf("-") + 1) : a.id)),
      wd && a.fame !== null ? [h("dt", {}, "Wikipedia"), h("dd", {}, `${a.fame} language edition${a.fame === 1 ? "" : "s"}`)] : null,
      a.fame_pct !== null && a.fame_pct !== undefined ? [h("dt", {}, "Renown"), h("dd", {},
        a.fame_score > 0 ? `top ${Math.max(1, Math.round(100 * (1 - a.fame_pct)))}% by fame` : "little documented",
        h("small", { class: "renown-note" }, " (Wikipedia coverage of the work or its artist)"))] : null),
    geoLines.length ? [h("h3", {}, "Where the artists were born"), h("ul", {}, geoLines)] : null,
    a.titles.length > 1 ? [h("h3", {}, "Also titled"), h("ul", {}, a.titles.slice(1).map((t) => h("li", { class: "alt-title" }, t)))] : null,
    h("h3", {}, "Themes"),
    a.themes.length ? h("ul", {}, a.themes.map((p) => h("li", {}, h("button", { class: "linkish", onclick: () => { closeDrawer(); navigate(blank({ node: [p.at(-1).id] })); } },
      p.map((x) => x.label).join(" › "))))) : h("p", {}, "Not in a curated theme yet."),
    h("h3", {}, "Iconclass subjects"),
    h("ul", {}, a.subjects.map((s) => h("li", {}, h("button", { class: "linkish", title: s.label || s.code,
      onclick: () => { labels["code:" + s.code] = s.label_short; closeDrawer(); navigate({ code: s.code }); } }, s.label_short || s.code), " ", h("code", {}, s.code))))].flat(Infinity).filter(Boolean));
  d.hidden = false;
  d.querySelector("#drawer-close").focus();
}
function closeDrawer() { $("#drawer").hidden = true; }
$("#drawer-close").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#drawer").hidden) closeDrawer(); });

// ---------- search ----------
const input = $("#q"), box = $("#suggest");
let sugTimer = null, sugItems = [], sugIndex = -1;
const KIND_LABEL = { segment: "Segments", theme: "Themes", subject: "Iconclass subjects", artist: "Artists", country: "Artists born in", object_type: "Kinds of object", source: "Source collections" };
input.addEventListener("input", () => { clearTimeout(sugTimer); sugTimer = setTimeout(suggest, 120); });
input.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (!sugItems.length) return;
    sugIndex = (sugIndex + (e.key === "ArrowDown" ? 1 : -1) + sugItems.length) % sugItems.length;
    sugItems.forEach((o, i) => o.el.setAttribute("aria-selected", i === sugIndex));
    sugItems[sugIndex].el.scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (sugIndex >= 0) pick(sugItems[sugIndex].item); else if (input.value.trim()) pick({ kind: "title", ref: input.value.trim() });
  } else if (e.key === "Escape") hideSuggest();
});
input.addEventListener("blur", () => setTimeout(hideSuggest, 150));

async function suggest() {
  const q = input.value.trim();
  if (q.length < 2) return hideSuggest();
  const data = await api("suggest", `q=${encodeURIComponent(q)}`);
  if (input.value.trim() !== q) return;
  sugItems = []; sugIndex = -1;
  const nodes = [];
  for (const g of data.groups) {
    nodes.push(h("div", { class: "group" }, KIND_LABEL[g.kind] || g.kind));
    for (const item of g.items) {
      const sub = item.kind === "theme" ? item.path.slice(0, -1).join(" › ") : item.kind === "subject" ? item.ref : item.detail;
      const el = h("div", { role: "option", "aria-selected": "false", onmousedown: (e) => { e.preventDefault(); pick(item); } },
        h("span", {}, item.label, sub ? h("small", {}, sub) : null), h("span", { class: "count" }, fmt.format(item.n)));
      sugItems.push({ el, item }); nodes.push(el);
    }
  }
  const titleOpt = h("div", { role: "option", "aria-selected": "false", onmousedown: (e) => { e.preventDefault(); pick({ kind: "title", ref: q }); } },
    h("span", {}, `Search titles for “${q}”`), h("span", { class: "count" }, "↵"));
  sugItems.push({ el: titleOpt, item: { kind: "title", ref: q } });
  nodes.push(h("div", { class: "group" }, "Full text"), titleOpt);
  if (hasFilters()) nodes.push(h("div", { class: "hint" }, "Choosing a result starts a fresh search and clears the current filters."));
  box.replaceChildren(...nodes);
  box.hidden = false; input.setAttribute("aria-expanded", "true");
}
function hideSuggest() { box.hidden = true; input.setAttribute("aria-expanded", "false"); sugIndex = -1; }
function hasFilters() {
  return state.node.length > 1 || [state.century, state.creator, state.type, state.source, state.country, state.code, state.q].some((v) => v !== null && v !== undefined && v !== "");
}
// A search always starts over: every pick replaces the whole filter state (decision D9).
function pick(item) {
  hideSuggest(); input.value = ""; input.blur();
  if (item.kind === "segment" || item.kind === "theme") navigate(blank({ node: [item.ref] }));
  else if (item.kind === "subject") { labels["code:" + item.ref] = item.label; navigate(blank({ code: item.ref })); }
  else if (item.kind === "artist") { labels["creator:" + item.ref] = item.label; navigate(blank({ creator: Number(item.ref) })); }
  else if (item.kind === "object_type") navigate(blank({ type: item.ref }));
  else if (item.kind === "source") navigate(blank({ source: item.ref }));
  else if (item.kind === "country") { labels["country:" + item.ref] = item.label; navigate(blank({ country: item.ref })); }
  else if (item.kind === "title") navigate(blank({ q: item.ref }));
}

// ---------- controls & info ----------
// ---------- colour palette (a per-viewer preference, remembered in this browser) ----------
const PALETTES = ["teal", "fresco", "enamel"];
function setPalette(name, rerender = true) {
  if (!PALETTES.includes(name)) name = "teal";
  if (name === "teal") delete document.documentElement.dataset.palette; else document.documentElement.dataset.palette = name;
  for (const b of document.querySelectorAll("#palette-switch button")) b.setAttribute("aria-checked", String(b.dataset.palette === name));
  try { localStorage.setItem("dt.palette", name); } catch { /* storage unavailable: the choice lasts this visit */ }
  if (rerender && view) render();  // SVG colours that are computed in JS pick up the new variables
}
for (const b of document.querySelectorAll("#palette-switch button")) b.addEventListener("click", () => setPalette(b.dataset.palette));
setPalette(document.documentElement.dataset.palette || "teal", false);

$("#back-btn").addEventListener("click", () => history.back());
$("#reset-btn").addEventListener("click", () => navigate(blank({ node: view.path.length ? [view.path[0].id] : [] })));
$("#repro-toggle").addEventListener("change", (e) => navigate({ repro: e.target.checked }, { replace: true }));
$("#nat-toggle").addEventListener("change", (e) => navigate({ nat: e.target.checked }, { replace: true }));
const DATASET_LABEL = { icarus: "ICARUS", wikidata: "Wikidata", met: "The Met", aic: "Chicago", zeri: "Zeri", joconde: "Joconde" };
function renderDatasetSwitch() {
  const el = $("#ds-switch");
  const sets = Object.entries(meta.datasets || {}).sort((a, b) => b[1] - a[1]);
  el.hidden = sets.length < 2;
  const btn = (id, label, n) => h("button", { type: "button", "aria-pressed": String((state.ds || null) === id),
    title: id ? `Only ${label} (${fmt.format(n)} artworks)` : `All collections (${fmt.format(n)} artworks)`, onclick: () => navigate({ ds: id }) }, label);
  el.replaceChildren(btn(null, "All", sets.reduce((s, x) => s + x[1], 0)),
    ...sets.map(([id, n]) => btn(id, DATASET_LABEL[id] || id, n)));
}
for (const b of document.querySelectorAll("#c-map .seg button")) {
  b.addEventListener("click", () => {
    mapMode = b.dataset.mode;
    try { localStorage.setItem("dt.mapMode", mapMode); } catch { /* private mode */ }
    renderMap();
  });
}
$("#info-btn").addEventListener("click", () => { renderInfo(); $("#info").showModal(); });

function renderInfo() {
  const rows = meta.sources.map((s) => h("tr", {}, h("td", {}, s.name), h("td", {}, s.country || ""), h("td", { class: "num" }, fmt.format(s.n))));
  $("#info-body").replaceChildren(
    h("p", {}, `Daedalus Thread explores ${fmt.format(meta.total_artworks)} artworks from the ICARUS dataset (2026), described with `,
      h("a", { href: "https://iconclass.org/" }, "Iconclass"), " subject codes. Every chart works on the artworks that have the fields it needs, and states that number as n."),
    h("h3", {}, "How to read the numbers"),
    h("ul", {},
      h("li", {}, "Counts are unique artworks. An artwork can belong to several themes and segments, so sub-theme counts can add up to more than their parent."),
      h("li", {}, "Iconclass codes describe what is visible, including details. A lion in a St Jerome counts under Lions."),
      h("li", {}, "Dates come from each source's own text. Only dates that fall in a single century are placed on the timeline. Wider spans of 50 years or less are shown pale, as approximate."),
      h("li", {}, "Works with several artists (e.g. designer, engraver, publisher) count once for each artist."),
      h("li", {}, "Artist geography uses present-day borders. Each artist's birthplace comes from Wikidata (via the Getty ULAN identifier) or the ULAN itself, and is placed in today's country, so Rubens, born in Siegen, counts under Germany. Nationality is used only if you switch it on, and is shown as a lighter ring. Names were matched to ULAN by name and life dates. Doubtful matches are left unlocated rather than guessed."),
      h("li", {}, "The map covers Europe and the Mediterranean, where over 99% of located artists were born. The rest are listed as “Beyond the map”."),
      h("li", {}, "PAUart records are photographs of artworks. Their dates and creators describe the photograph, so they are left out of the date and artist charts unless you include them."),
      h("li", {}, "The catalogue lists the most renowned works first, and “Notable” narrows every chart to the better-known part of the collection. Each work is ranked by how widely Wikipedia covers it, or its artist (counted only for visual artists, so a patron like Napoleon adds nothing), plus museum highlights. Switch to “Everything” to see every record. Fame changes which works are shown and their order, never how a work is counted."),
      h("li", {}, "Some collections still use unencrypted http:// links. Artworks with those links are listed after the others, and their detail panel shows a warning."),
      h("li", {}, "A second source adds paintings from Wikidata (CC0), from museums worldwide, to balance ICARUS's strength in Northern European prints. A painting's subjects come from what Wikidata says it depicts, mapped to Iconclass through subject entries that carry Iconclass codes. Use the Collections switch to view either source alone."),
      h("li", {}, "Further sources: the Art Institute of Chicago (CC0), whose subject terms are mapped to themes through their names and Wikidata's Iconclass links; and the Fondazione Federico Zeri photo-archive catalogue of mostly Italian Renaissance art, whose subjects come linked to Iconclass by the Fondazione. Zeri data © Fondazione Federico Zeri, Università di Bologna, CC BY-NC 4.0, non-commercial use."),
      h("li", {}, "Joconde, the national catalogue of the Musées de France, adds paintings, drawings, prints and sculpture from French museums, which hold much Italian, Flemish and Spanish art as well as French. Its French subject terms (“scène biblique (Annonciation)”) are mapped to themes by a reviewed term list. Data: Ministère de la Culture, base Joconde (POP), Licence Ouverte 2.0."),
      h("li", {}, "These are distributions within the collections shown, not definitive histories of art.")),
    h("h3", {}, "Sources"),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Collection"), h("th", {}, "Country"), h("th", { class: "num" }, "Artworks"))), h("tbody", {}, rows)),
    h("p", {}, `Build ${meta.build.built_at} · taxonomy v${meta.build.taxonomy_version} · Iconclass ${String(meta.build.iconclass_commit).slice(0, 7)}`));
}

// ---------- boot ----------
(async function boot() {
  [meta, basemap] = await Promise.all([api("meta"), fetch("/assets/basemap.json").then((r) => r.json())]);
  for (const s of meta.segments) labels["node:" + s.id] = s.label;
  fromQuery(location.search);
  if (!location.search) {
    const primary = meta.segments.find((s) => s.flags.includes("primary")) || meta.segments[0];
    navigate(blank({ node: [primary.id] }), { replace: true });
  } else load();
})();
