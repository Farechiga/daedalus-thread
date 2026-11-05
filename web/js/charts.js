// Native SVG charts. Each function returns an <svg> element; clicks call onPick(datum).
const NS = "http://www.w3.org/2000/svg";
export const fmt = new Intl.NumberFormat("en");
export const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function hit(parent, label, onPick, datum) {
  const g = el("g", { class: "hit", tabindex: 0, role: "button", "aria-label": label }, parent);
  el("title", {}, g).textContent = label;
  if (onPick) {
    g.addEventListener("click", () => onPick(datum));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(datum); } });
  }
  return g;
}

function truncate(text, max) {
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

export const centuryLabel = (c) => (c >= 1000 ? `${c}s` : `${c}s`);

/** Horizontal ranked bars. items: [{label, n, sel?}] */
export function rankedBars(items, { onPick, width = 520, labelWidth = 190, rowH = 22, maxLabel } = {}) {
  maxLabel = Math.min(maxLabel || 40, Math.floor(labelWidth / 6.8));
  const max = Math.max(1, ...items.map((d) => d.n));
  const h = items.length * rowH + 4;
  const svg = el("svg", { viewBox: `0 0 ${width} ${h}`, role: "img" });
  const barW = width - labelWidth - 56;
  items.forEach((d, i) => {
    const y = i * rowH;
    const g = hit(svg, `${d.label}: ${fmt.format(d.n)}`, onPick, d);
    el("rect", { x: 0, y, width, height: rowH, fill: "transparent" }, g);
    const t = el("text", { x: labelWidth - 8, y: y + rowH / 2 + 4, "text-anchor": "end" }, g);
    t.textContent = truncate(d.label, maxLabel);
    el("rect", { class: "bar" + (d.sel ? " sel" : "") + (d.soft ? " soft" : ""), x: labelWidth, y: y + 4,
      width: Math.max(1, (barW * d.n) / max), height: rowH - 8, rx: 2 }, g);
    const v = el("text", { x: labelWidth + Math.max(1, (barW * d.n) / max) + 6, y: y + rowH / 2 + 4, class: "muted" }, g);
    v.textContent = fmt.format(d.n);
  });
  return svg;
}

/** Century columns. data: [[century, n]], extra: [[century, n]] (approximate, drawn soft and stacked). */
export function timeline(data, { extra = [], selected, onPick, width = 980, height = 210 } = {}) {
  const all = new Map();
  for (const [c, n] of data) all.set(c, { c, n, x: 0 });
  for (const [c, n] of extra) (all.get(c) || all.set(c, { c, n: 0, x: 0 }).get(c)).x = n;
  let rows = [...all.values()].sort((a, b) => a.c - b.c);
  const early = rows.filter((r) => r.c < 1000);
  rows = rows.filter((r) => r.c >= 1000);
  if (early.length) rows.unshift({ c: 0, n: early.reduce((s, r) => s + r.n, 0), x: early.reduce((s, r) => s + r.x, 0), early: true });
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  if (!rows.length) return svg;
  const pad = { l: 46, r: 8, t: 10, b: 28 };
  const max = Math.max(1, ...rows.map((r) => r.n + r.x));
  const iw = width - pad.l - pad.r, ih = height - pad.t - pad.b;
  const bw = iw / rows.length;
  const grid = el("g", { class: "grid axis" }, svg);
  for (const f of [0, 0.5, 1]) {
    const y = pad.t + ih - ih * f;
    el("line", { x1: pad.l, x2: width - pad.r, y1: y, y2: y }, grid);
    el("text", { x: pad.l - 6, y: y + 4, "text-anchor": "end" }, grid).textContent = fmt.format(Math.round(max * f));
  }
  rows.forEach((r, i) => {
    const x = pad.l + i * bw;
    const label = r.early ? "before 1000" : centuryLabel(r.c);
    const g = hit(svg, `${label}: ${fmt.format(r.n)} artworks${r.x ? ` (+${fmt.format(r.x)} approximate)` : ""}`,
      r.early ? null : onPick, r);
    el("rect", { x, y: pad.t, width: bw, height: ih, fill: "transparent" }, g);
    const hN = (ih * r.n) / max, hX = (ih * r.x) / max;
    el("rect", { class: "bar" + (selected === r.c ? " sel" : ""), x: x + bw * 0.14, y: pad.t + ih - hN, width: bw * 0.72, height: hN, rx: 2 }, g);
    if (r.x) el("rect", { class: "bar soft", x: x + bw * 0.14, y: pad.t + ih - hN - hX, width: bw * 0.72, height: hX, rx: 2 }, g);
    el("text", { x: x + bw / 2, y: height - 9, "text-anchor": "middle", class: "muted" }, g).textContent = r.early ? (bw < 40 ? "<11" : "<1000") : bw < 40 ? String(r.c / 100 + 1).padStart(2) : centuryLabel(r.c);
  });
  return svg;
}

/** Rows (themes) x columns (centuries) heatmap. rows: [{id,label}], cells: [[rowId, century, n]] */
export function heatmap(rows, cells, { onPick, width = 980 } = {}) {
  const cents = [...new Set(cells.map((c) => c[1]))].sort((a, b) => a - b);
  const byRow = new Map(rows.map((r) => [r.id, 0]));
  for (const [r, , n] of cells) byRow.set(r, (byRow.get(r) || 0) + n);
  const shown = rows.filter((r) => byRow.get(r.id) > 0).sort((a, b) => byRow.get(b.id) - byRow.get(a.id)).slice(0, 14);
  const labelW = Math.min(230, width * 0.34), cellH = 22, headH = 22;
  const svg = el("svg", { viewBox: `0 0 ${width} ${headH + shown.length * cellH + 4}`, role: "img" });
  if (!shown.length || !cents.length) return svg;
  const cw = (width - labelW) / cents.length;
  const lookup = new Map(cells.map(([r, c, n]) => [`${r}|${c}`, n]));
  // Each row is normalised to its own maximum, so the chart shows *when* each theme peaks.
  cents.forEach((c, j) => {
    el("text", { x: labelW + j * cw + cw / 2, y: 14, "text-anchor": "middle", class: "muted" }, svg).textContent = cw < 40 ? String(c / 100 + 1) : centuryLabel(c);
  });
  shown.forEach((r, i) => {
    const y = headH + i * cellH;
    const rowMax = Math.max(1, ...cents.map((c) => lookup.get(`${r.id}|${c}`) || 0));
    el("text", { x: labelW - 8, y: y + cellH / 2 + 4, "text-anchor": "end" }, svg).textContent = truncate(r.label, Math.floor(labelW / 7));
    const g = el("g", { class: "heat" }, svg);
    cents.forEach((c, j) => {
      const n = lookup.get(`${r.id}|${c}`) || 0;
      const cell = hit(g, `${r.label}, ${centuryLabel(c)}: ${fmt.format(n)}`, n ? onPick : null, { id: r.id, century: c });
      el("rect", { x: labelW + j * cw, y, width: cw, height: cellH, fill: mix(n / rowMax) }, cell);
    });
  });
  return svg;
}

function mix(t) {
  if (t <= 0) return "var(--heat-0)";
  const a = Math.round(15 + 85 * Math.sqrt(t));
  return `color-mix(in oklab, var(--heat-1) ${a}%, var(--heat-0))`;
}

/** Squarified treemap of items [{id,label,n}] */
export function treemap(items, { onPick, width = 520, height = 300 } = {}) {
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  const data = items.filter((d) => d.n > 0).sort((a, b) => b.n - a.n);
  const total = data.reduce((s, d) => s + d.n, 0);
  if (!total) return svg;
  const rects = squarify(data.map((d) => ({ ...d, area: (d.n / total) * width * height })), 0, 0, width, height);
  rects.forEach((r, i) => {
    const g = hit(svg, `${r.label}: ${fmt.format(r.n)}`, onPick, r);
    g.classList.add("tm");
    const shade = 62 + 38 * (1 - i / Math.max(1, rects.length - 1));
    el("rect", { x: r.x, y: r.y, width: Math.max(0, r.w), height: Math.max(0, r.h),
      fill: `color-mix(in oklab, var(--bar) ${shade}%, var(--bar-muted))` }, g);
    if (r.w > 60 && r.h > 26) {
      const t = el("text", { x: r.x + 6, y: r.y + 16 }, g);
      t.textContent = truncate(r.label, Math.floor(r.w / 7));
      if (r.h > 42) el("text", { x: r.x + 6, y: r.y + 31 }, g).textContent = fmt.format(r.n);
    }
  });
  return svg;
}

function squarify(items, x, y, w, h) {
  const out = [];
  let row = [], rest = items.slice();
  const worst = (row, side) => {
    const s = row.reduce((a, d) => a + d.area, 0);
    const max = Math.max(...row.map((d) => d.area)), min = Math.min(...row.map((d) => d.area));
    return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
  };
  while (rest.length) {
    const side = Math.min(w, h);
    const next = rest[0];
    if (!row.length || worst(row.concat(next), side) <= worst(row, side)) {
      row.push(next); rest.shift();
      if (rest.length) continue;
    }
    const s = row.reduce((a, d) => a + d.area, 0);
    if (w >= h) {
      const rw = s / h; let yy = y;
      for (const d of row) { const rh = d.area / rw; out.push({ ...d, x, y: yy, w: rw, h: rh }); yy += rh; }
      x += rw; w -= rw;
    } else {
      const rh = s / w; let xx = x;
      for (const d of row) { const rw = d.area / rh; out.push({ ...d, x: xx, y, w: rw, h: rh }); xx += rw; }
      y += rh; h -= rh;
    }
    row = [];
  }
  return out;
}

// ---------------------------------------------------------------- maps
// basemap: {width, height, countries:[{code, name, d}]} in projected pixel space (LAEA, Europe).
function base(basemap, selected) {
  const svg = el("svg", { viewBox: `0 0 ${basemap.width} ${basemap.height}`, role: "img", class: "map" });
  el("rect", { x: 0, y: 0, width: basemap.width, height: basemap.height, class: "sea" }, svg);
  const land = el("g", { class: "land" }, svg);
  for (const c of basemap.countries) el("path", { d: c.d, class: c.code === selected ? "sel" : null }, land);
  return svg;
}

/** Classed log scale for country counts: decade classes (1–9, 10–99, …) so a 60:1 spread still reads.
 *  Returns { classes: [{lo, hi, color}], color(n) }. */
export function countryScale(values) {
  const max = Math.max(1, ...values);
  // decades (1, 10, 100, ...); half-decades (3, 30, ...) only when the range is too narrow for 4 classes
  const decades = [];
  for (let p = 1; p <= max; p *= 10) decades.push(p);
  let edges = decades;
  if (decades.length < 4) {
    edges = [];
    for (const p of decades) edges.push(p, p * 3);
    edges = edges.filter((b) => b <= max);
  }
  const classes = edges.map((lo, i) => {
    const hi = i + 1 < edges.length ? edges[i + 1] : Infinity;
    const t = edges.length === 1 ? 1 : 0.18 + 0.82 * (i / (edges.length - 1));
    return { lo, hi, color: `color-mix(in oklab, var(--heat-1) ${Math.round(t * 100)}%, var(--heat-0))` };
  });
  return { classes, color: (n) => (n > 0 ? classes.findLast((c) => n >= c.lo).color : null) };
}

let uid = 0;
const ringCache = new WeakMap();
/** Parse the basemap's "Mx,yLx,y...Z" paths into rings of points (cached per basemap). */
function ringsOf(basemap) {
  if (!ringCache.has(basemap)) {
    const map = new Map();
    for (const c of basemap.countries) {
      map.set(c.code, c.d.split("Z").filter(Boolean).map((part) =>
        part.replace(/^M/, "").split("L").map((pt) => pt.split(",").map(Number))));
    }
    ringCache.set(basemap, map);
  }
  return ringCache.get(basemap);
}

function countryLabel(n, d, showProxy) {
  const proxy = d.n - (d.n_birthplace ?? d.n);
  return `${d.name}: ${fmt.format(d.n)} artworks` +
    (showProxy && proxy ? ` (${fmt.format(d.n_birthplace)} by birthplace, +${fmt.format(proxy)} by nationality)` : "");
}

/** Choropleth: national areas filled by classed intensity. items: [{code, name, n, n_birthplace}] */
export function choropleth(basemap, items, { selected, onPick, scale, showProxy = false } = {}) {
  const svg = base(basemap, null);
  const byCode = new Map(items.map((d) => [d.code, d]));
  const g = el("g", { class: "choro" }, svg);
  for (const c of basemap.countries) {
    const d = byCode.get(c.code);
    if (!d || !d.n) continue;
    const node = hit(g, countryLabel(c, d, showProxy), onPick, d);
    if (c.code === selected) node.classList.add("sel");
    el("path", { d: c.d, style: `fill:${scale.color(d.n)}` }, node);
  }
  return svg;
}

/** Prism map: the same filled countries, raised in proportion to artworks on a tilted map.
 *  Side walls are drawn back-to-front (painter's algorithm), so nearer prisms hide those behind. */
export function prism(basemap, items, { selected, onPick, scale, showProxy = false, tilt = 0.55, maxH = 64, labels = 6 } = {}) {
  const rings = ringsOf(basemap);
  const top = maxH + 24;
  const W = basemap.width, H = Math.round(basemap.height * tilt + top + 8);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", class: "map raised" });
  el("rect", { x: 0, y: 0, width: W, height: H, class: "sea" }, svg);
  const byCode = new Map(items.map((d) => [d.code, d]));
  const max = Math.max(1, ...items.filter((d) => d.ax !== null).map((d) => d.n));
  const sy = (y) => y * tilt + top;
  const flat = el("g", { class: "land" }, svg);
  const shapes = [];
  for (const c of basemap.countries) {
    const d = byCode.get(c.code);
    const pts = rings.get(c.code).map((r) => r.map(([x, y]) => [x, sy(y)]));
    const h = d && d.n ? Math.max(1.5, (maxH * d.n) / max) : 0;
    if (!h) { el("path", { d: pts.map((r) => "M" + r.map((p) => p.join(",")).join("L") + "Z").join("") }, flat); continue; }
    shapes.push({ c, d, pts, h, south: Math.max(...pts.flat().map((p) => p[1])) });
  }
  shapes.sort((a, b) => a.south - b.south); // north (far) first
  const defs = el("defs", {}, svg);
  const g = el("g", { class: "prisms" }, svg);
  for (const s of shapes) {
    const node = hit(g, countryLabel(s.c, s.d, showProxy), onPick, s.d);
    if (s.c.code === selected) node.classList.add("sel");
    const color = scale.color(s.d.n);
    // Walls facing the viewer (south) only; the top face hides the rest. One smooth vertical gradient per
    // country (lit near the top, darker at the base) reads as solid volume without striping on jagged coasts.
    let walls = "";
    for (const r of s.pts) {
      let area = 0;
      for (let i = 0; i < r.length - 1; i++) area += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
      const sign = area > 0 ? 1 : -1;
      for (let i = 0; i < r.length - 1; i++) {
        const [x1, y1] = r[i], [x2, y2] = r[i + 1];
        const dx = x2 - x1;
        if (!dx && y1 === y2) continue;
        if ((dx * sign) < 0) continue; // outward normal points north: hidden
        walls += `M${x1},${y1}L${x2},${y2}L${x2},${y2 - s.h}L${x1},${y1 - s.h}Z`;
      }
    }
    if (walls) {
      const id = `wall-${s.c.code}-${uid++}`;
      const grad = el("linearGradient", { id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
      el("stop", { offset: "0%", style: `stop-color:color-mix(in oklab, ${color} 80%, #000)` }, grad);
      el("stop", { offset: "100%", style: `stop-color:color-mix(in oklab, ${color} 45%, #000)` }, grad);
      el("path", { d: walls, class: "wall", fill: `url(#${id})` }, node);
    }
    el("path", { d: s.pts.map((r) => "M" + r.map(([x, y]) => `${x},${y - s.h}`).join("L") + "Z").join(""), class: "top", style: `fill:${color}` }, node);
  }
  // labels above the tallest prisms
  const lg = el("g", { class: "prism-labels" }, svg);
  const placed = [];
  for (const s of [...shapes].sort((a, b) => b.d.n - a.d.n)) {
    if (placed.length >= labels) break;
    if (s.d.ax === null) continue;
    const x = s.d.ax, y = sy(s.d.ay) - s.h - 6;
    const w = Math.max(s.d.name.length * 7.2, 40), box = { x: x - w / 2, y: y - 13, w, h: 28 };
    if (placed.some((b) => box.x < b.x + b.w && b.x < box.x + box.w && box.y < b.y + b.h && b.y < box.y + box.h)) continue;
    placed.push(box);
    el("text", { x, y, "text-anchor": "middle", class: "pn" }, lg).textContent = s.d.name;
    el("text", { x, y: y + 13, "text-anchor": "middle", class: "pv" }, lg).textContent = fmt.format(s.d.n);
  }
  return svg;
}

/** Art centres: proportional circles at artists' birthplaces. places: [{id, name, country, x, y, n}] */
export function artCentres(basemap, places, { selected, onPick, maxR = 30, labels = 14 } = {}) {
  const svg = base(basemap, selected);
  const data = places.filter((p) => p.in_view && p.n > 0);
  if (!data.length) return svg;
  const frame = autoFrame(basemap, data);
  svg.setAttribute("viewBox", `${frame.x} ${frame.y} ${frame.w} ${frame.h}`);
  const zoom = frame.w / basemap.width;           // < 1 when zoomed in: keep circles and labels a constant size
  const max = Math.max(...data.map((p) => p.n));
  const g = el("g", { class: "centres" }, svg);
  const sized = data.map((p) => ({ ...p, r: Math.max(1.6, maxR * Math.sqrt(p.n / max)) * zoom })).sort((a, b) => b.r - a.r);
  for (const p of sized) {
    const node = hit(g, `${p.name}: ${fmt.format(p.n)} artworks by artists born here`, onPick, p);
    if (p.country === selected) node.classList.add("sel");
    el("circle", { cx: p.x, cy: p.y, r: p.r }, node);
  }
  // labels for the largest centres, skipping any that would collide
  const placed = [];
  const lg = el("g", { class: "centre-labels" }, svg);
  for (const p of sized.slice(0, labels * 2)) {
    if (placed.length >= labels) break;
    const w = (p.name.length * 6.6 + 8) * zoom, h = 15 * zoom;
    const box = { x: p.x + p.r + 3 * zoom, y: p.y - h / 2, w, h };
    if (box.x + w > frame.x + frame.w) box.x = p.x - p.r - 3 * zoom - w;
    if (placed.some((b) => box.x < b.x + b.w && b.x < box.x + box.w && box.y < b.y + b.h && b.y < box.y + box.h)) continue;
    placed.push(box);
    el("text", { x: box.x + 2 * zoom, y: box.y + 11.5 * zoom, class: "pl", style: `font-size:${13 * zoom}px;stroke-width:${3 * zoom}px` }, lg).textContent = p.name;
  }
  return svg;
}

/** Smallest frame (basemap aspect ratio) holding 97% of the artworks, padded; never tighter than 35% of the map. */
function autoFrame(basemap, data) {
  const total = data.reduce((s, p) => s + p.n, 0);
  const byN = [...data].sort((a, b) => b.n - a.n);
  const kept = [];
  let acc = 0;
  for (const p of byN) { kept.push(p); acc += p.n; if (acc >= total * 0.97) break; }
  let x0 = Math.min(...kept.map((p) => p.x)), x1 = Math.max(...kept.map((p) => p.x));
  let y0 = Math.min(...kept.map((p) => p.y)), y1 = Math.max(...kept.map((p) => p.y));
  const aspect = basemap.height / basemap.width;
  let w = Math.max(x1 - x0, (y1 - y0) / aspect, basemap.width * 0.35) * 1.22;
  w = Math.min(w, basemap.width);
  const h = w * aspect;
  let x = (x0 + x1) / 2 - w / 2, y = (y0 + y1) / 2 - h / 2;
  x = Math.max(0, Math.min(x, basemap.width - w));
  y = Math.max(0, Math.min(y, basemap.height - h));
  return { x, y, w, h };
}
