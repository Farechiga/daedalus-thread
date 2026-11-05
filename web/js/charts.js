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
    const shade = 35 + 65 * (1 - i / Math.max(1, rects.length - 1));
    el("rect", { x: r.x, y: r.y, width: Math.max(0, r.w), height: Math.max(0, r.h),
      fill: `color-mix(in oklab, var(--bar-hi) ${shade}%, var(--bar-muted))` }, g);
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
