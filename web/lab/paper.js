// Lab: the Atlas view for /lab/paper.html. Charts | Atlas switch; the atlas follows the explorer's filters (it reads
// the same query string) and pins the selection's best-known works at their year, one gold thread per birth region.
const $ = (s) => document.querySelector(s);
const root = document.documentElement;
const REGIONS = ["Italy", "Low Countries", "German lands", "France", "Iberia", "Elsewhere"];
const THREAD_Y = 30;
let data = null, dataKey = null, requestId = 0;

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function seeded(s) { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return ((h >>> 0) % 1000) / 1000; }

function setView(v, remember = true) {
  if (v === "atlas") root.dataset.view = "atlas"; else delete root.dataset.view;
  for (const b of document.querySelectorAll("#view-switch button")) b.setAttribute("aria-checked", String(b.dataset.view === (v || "charts")));
  if (remember) try { localStorage.setItem("dt.view", v); } catch { /* storage unavailable: the choice lasts this visit */ }
  if (v === "atlas") refresh();
}
for (const b of document.querySelectorAll("#view-switch button")) b.addEventListener("click", () => setView(b.dataset.view));

// follow the explorer: every navigation changes the query string through pushState / replaceState / popstate
let refreshTimer = null;
const schedule = () => { clearTimeout(refreshTimer); refreshTimer = setTimeout(refresh, 40); };
for (const k of ["pushState", "replaceState"]) {
  const orig = history[k].bind(history);
  history[k] = (...a) => { const r = orig(...a); schedule(); return r; };
}
addEventListener("popstate", schedule);
let resizeTimer = null;
addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => data && root.dataset.view === "atlas" && draw(), 200); });

async function refresh() {
  if (root.dataset.view !== "atlas") return;
  const key = location.search.replace(/^\?/, "");
  if (key === dataKey && data) return draw();
  const id = ++requestId;
  $("#atlas-board").classList.add("loading");
  try {
    const r = await fetch(`/api/atlas${key ? "?" + key : ""}`);
    if (r.status === 401) return location.reload();
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    const j = await r.json();
    if (id !== requestId) return;
    data = j; dataKey = key;
    draw();
  } catch (e) {
    $("#atlas-board").innerHTML = `<p class="empty">Could not load the atlas: ${esc(e.message)}</p>`;
  } finally {
    if (id === requestId) $("#atlas-board").classList.remove("loading");
  }
}

function heading() {
  if (data.label) return esc(data.label).replace(/^(The |Saint |St )/, (m) => `<em>${m.trim()}</em> `);
  const chips = [...document.querySelectorAll("#chips button, #chips .chip")].map((c) => c.textContent.replace(/[×✕]/g, "").trim()).filter(Boolean);
  return chips.length ? esc(chips.join(" · ")) : "<em>The</em> whole collection";
}

function domain(works) {
  const c = +new URLSearchParams(location.search).get("century");
  if (c) return { y0: c, y1: c + 100, step: 10 };
  const years = works.map((w) => w.year).sort((a, b) => a - b);
  let y0 = Math.max(1000, Math.floor(years[Math.floor(years.length * 0.03)] / 100) * 100);
  let y1 = Math.min(2000, Math.ceil((years[Math.ceil(years.length * 0.97) - 1] + 1) / 100) * 100);
  while (y1 - y0 < 300) { if (y1 < 2000) y1 += 100; else y0 -= 100; }
  return { y0, y1, step: 100 };
}

function draw() {
  $("#atlas-h").innerHTML = heading();
  $("#atlas-desc").textContent = data.description || "";
  const board = $("#atlas-board");
  const works = data.works;
  $("#atlas-tally").innerHTML = `<b>${data.n.toLocaleString("en")}</b>works in this selection<br>${works.length} with images, pinned`;
  if (!works.length) { board.innerHTML = `<p class="empty">No dated works with an image and a known birthplace in this selection.</p>`; return; }
  const B = board.clientWidth, LW = Math.round(Math.min(128, Math.max(92, B * 0.12)));
  const W = B - LW - 8;
  const { y0, y1, step } = domain(works);
  const ticks = [];
  for (let y = y0; y < y1; y += step) ticks.push(y);
  const xOf = (y) => LW + ((Math.min(Math.max(y, y0), y1 - 1) - y0) / (y1 - y0)) * W;
  const colW = W / ticks.length;
  const maxS = Math.min(112, Math.max(62, colW * 0.82)), minS = maxS * 0.52;
  const maxFame = Math.max(...works.map((w) => w.fame), 0.01);
  board.style.setProperty("--lw", `${LW - 22}px`);
  board.innerHTML = `<div class="cols">${ticks.map((t) => `<span style="left:${xOf(t)}px">${step === 100 ? t + "s" : t}</span>`).join("")}</div>`;
  const tickHtml = ticks.map((t) => `<i class="tick" style="left:${xOf(t)}px"></i>`).join("");
  let delay = 0;
  for (const region of REGIONS) {
    const mine = works.filter((w) => w.region === region && w.year >= y0 - 10 && w.year < y1 + 10).sort((a, b) => b.fame - a.fame);
    if (!mine.length) continue;
    // two tiers: a card hangs on the thread at its year if there is room, else on a lower tier below the tallest
    // card of the first (its own drop line); a card that fits on neither without leaving the board is left off
    const tiers = [{ spans: [] }, { spans: [] }], placed = [];
    const free = (t, x, s) => tiers[t].spans.every(([a, b]) => x + s + 10 <= a || x >= b + 10);
    for (const w of mine) {
      const size = minS + (maxS - minS) * Math.sqrt(w.fame / maxFame);
      const ideal = Math.min(Math.max(xOf(w.year) - size / 2, LW), LW + W - size);
      let best = null;
      for (const t of [0, 1]) {
        for (let dx = 0; dx <= colW * 0.9; dx += 6) {
          const x = [ideal + dx, ideal - dx].find((x) => x >= LW && x + size <= LW + W && free(t, x, size));
          if (x !== undefined) { if (!best || dx + t * 30 < best.cost) best = { t, x, cost: dx + t * 30 }; break; }
        }
      }
      if (!best) continue;
      tiers[best.t].spans.push([best.x, best.x + size]);
      placed.push({ w, x: best.x, size, tier: best.t });
    }
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `${tickHtml}<div class="tag">${region}<small>${placed.length} on the thread</small></div>`;
    board.appendChild(row);
    const pins = placed.map((c) => c.x + c.size / 2).sort((a, b) => a - b);
    let d = `M${LW - 18},${THREAD_Y - 6}`, px = LW - 18, py = THREAD_Y - 6;
    for (const x of [...pins, LW + W + 6]) {
      const y = x > LW + W ? THREAD_Y - 6 : THREAD_Y, sag = Math.min(24, (x - px) * 0.12);
      d += `Q${((px + x) / 2).toFixed(1)},${(Math.max(py, y) + sag).toFixed(1)} ${x.toFixed(1)},${y}`;
      px = x; py = y;
    }
    row.insertAdjacentHTML("beforeend", `<svg aria-hidden="true"><path class="wire" d="${d}"/>${placed.filter((c) => c.tier)
      .map((c) => `<line class="drop" x1="${c.x + c.size / 2}" y1="${THREAD_Y}" x2="${c.x + c.size / 2}" y2="${THREAD_Y}"/>`).join("")}</svg>`);
    for (const c of [...placed].sort((a, b) => a.x - b.x)) {
      const b = document.createElement("button");
      b.className = "pin";
      b.type = "button";
      const rel = (c.x - LW) / W;  // zoom away from the board's edges
      b.style.cssText = `left:${c.x}px;top:${THREAD_Y}px;width:${c.size}px;--mh:${c.size * 1.32}px;` +
        `--r:${((seeded(c.w.id) - 0.5) * 5).toFixed(2)}deg;--d:${(0.35 + delay).toFixed(2)}s;--o:${rel < 0.15 ? "0 0" : rel > 0.8 ? "100% 0" : "50% 0"}`;
      delay += 0.03;
      b.setAttribute("aria-label", `${c.w.title || "Untitled"}, ${c.w.artist || "artist unknown"}, ${c.w.date || c.w.year}`);
      b.innerHTML = `<img src="${esc(c.w.img)}" alt="" loading="lazy" decoding="async"><span class="cap"><b>${esc(c.w.title || "Untitled")}</b>` +
        `${esc(c.w.artist || "Artist unknown")} · ${esc(c.w.date || c.w.year)}<br>${esc(c.w.holding || "")}</span>`;
      c.el = b;
      const img = b.querySelector("img");
      img.addEventListener("load", () => { c.loaded = true; fit(row, placed); });
      img.addEventListener("error", () => { b.remove(); c.gone = true; fit(row, placed); });
      b.addEventListener("click", () => window.dtOpenArtwork?.(c.w.id));
      row.appendChild(b);
    }
    fit(row, placed);
  }
}

// Rows fit their cards as the images arrive: the lower tier hangs just below the tallest card above it, and the row
// shrinks to its contents (an unloaded card is assumed portrait until its image says otherwise).
function fit(row, placed) {
  const hOf = (c) => (c.gone ? 0 : c.loaded ? c.el.offsetHeight : c.size * 1.32 + 10);
  const tier1 = placed.filter((c) => c.tier && !c.gone);
  const top0 = Math.max(0, ...placed.filter((c) => !c.tier).map(hOf));
  const drop = top0 + 18;
  for (const c of tier1) c.el.style.top = `${THREAD_Y + drop}px`;
  const lines = row.querySelectorAll("line.drop");
  placed.filter((c) => c.tier).forEach((c, i) => {
    lines[i]?.setAttribute("y2", c.gone ? THREAD_Y : THREAD_Y + drop);
  });
  row.style.height = `${THREAD_Y + (tier1.length ? drop + Math.max(...tier1.map(hOf)) : top0) + 24}px`;
}

setView(root.dataset.view === "atlas" ? "atlas" : "charts", false);
