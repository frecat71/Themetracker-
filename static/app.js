// ─── Theme Tracker — v2 ────────────────────────────────────────────────
// English-only build. Same scoring & history logic. Visual polish.
// ───────────────────────────────────────────────────────────────────────

const TIMEFRAMES      = ["1D", "1W", "1M", "3M", "YTD"];
const ETF_TIMEFRAMES  = ["1D", "1W", "1M", "3M", "YTD"];
const SPARKLINE_ORDER = ["YTD", "3M", "1M", "1W", "1D"];

const STR = {
  notLoaded:    "— not yet loaded —",
  updated:      "Updated: ",
  loading:      "Loading data…",
  noData:       "No data.",
  tabHeatmap:   "Heatmap",
  tabPicks:     "★ Setup Picks",
  tabTop10:     "Top 10",
  tabEtfs:      "📈 ETF Themes",
  heatmapTitle: "Industry Heatmap",
  colIndustry:  "Industry",
  colScore:     "Score",
  colAccel:     "Accel",
  colTrend:     "Trend",
  picksTitle:   "★ Setup Picks — First Flag",
  picksSubtitle:"Industries with positive momentum profile for First Flag breakout trades.",
  picksColReason: "Setup Rationale",
  picksEmpty:   "No industries with First Flag profile found.",
  top10Title:   "Top 10 per Timeframe",
  tagHot:       "HOT",
  tagAccel:     "ACCEL ▲",
  tagFresh:     "FRESH",
  tagInst:      "INST",
  reasonFresh:  (p3m, p1m) => `Weak 3M base (${p3m}%) but 1M strong → first leg confirmed, not extended.`,
  reasonSolid:  ()         => `3M solid, 1W accelerating further → trend intact, momentum building.`,
  reasonSteady: ()         => `Consistently strong across 1W/1M — steady sector momentum.`,
  reasonAccel:  (acc)      => `Strong acceleration (Accel +${acc}) suggests fresh institutional interest.`,
  reasonIntraday: (p1d)    => `Intraday +${p1d}% — breakout already running today.`,
  moversTitle:  "Where is the Puck going?",
  moversSubtitle: "Rank change since the selected period. The bigger the jump, the stronger the momentum.",
  moversRising: "🚀 Rising — Puck heading here",
  moversFading: "🔻 Fading — Puck leaving",
  moversNoData: (period) => `Not enough data for ${period} yet. Wait until enough daily snapshots are collected.`,
  moversCompare:(date) => `vs. ${date}`,
  viewCards:    "📊 Cards",
  viewBars:     "📈 Bar Chart",
  etfTitle:     "Thematic ETF Heatmap",
  etfViewThemes:"🎨 Themes",
  etfViewEtfs:  "📊 Individual ETFs",
  etfColEtfs:   "ETFs (P1)",
  etfNoData:    "ETF data loading or not yet available.",
  infoScore:    "Weighted rank score: 1M×70% + 1W×20% + 3M×10%. Lower = better (rank 1 = strongest industry).",
  infoAccel:    "Accel = 3M rank minus 1W rank. High positive = was weak 3M ago, now strong = first leg, not extended. Ideal for First Flag setups.",
  hintHeatmap:  "Sort by Score: market overview — which industries are currently leading.\nSort by Accel: First Flag search — fresh momentum (weak 3M + strong 1W = first leg, not extended).\nINST filter: shows only institutionally confirmed industries (Top 40 in 1M and 3M).\nClick any column header to sort, click again to reverse.",
  hintPicks:    "Pre-filtered First Flag candidate list: Score Top 40 + positive Accel + 1W > 1% + 1M > 0%.\nSorted by: 60% Accel weight + 40% Score — freshest moves first.\nINST badge = institutional capital confirms the industry = highest confluence.\nClick any industry name to open Finviz screener with matching filters.",
  hintTop10:    "Top 10 performers per timeframe — shows current market leaders.\nCards: compact overview per timeframe.\nBar chart: all industries sorted by 1M and 3M performance.\nINST badge shows institutional interest.",
  hintMovers:   "Rank change since the selected period.\nRising: industries that climbed most in ranking — fresh capital flowing in. Look here!\nFading: industries that lost ranks — capital leaving. Avoid.\nSelect period: 1W / 2W / 1M / 3M (greyed out = not enough data yet).",
  hintEtfs:     "Thematic ETF performance across all timeframes.\nThemes view: aggregated from Priority-1 ETFs per theme. Score = weighted rank (1M×70%+1W×20%+3M×10%).\nETFs view: all individual ETFs, sortable. Priority 1 = core ETF for the theme.\nUsage: themes with strong 1M AND 3M score = institutionally confirmed momentum.",
};

const t = (key, ...args) => {
  const val = STR[key];
  return typeof val === "function" ? val(...args) : (val ?? key);
};

function applyStaticText() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    if (key === "colScore") {
      el.innerHTML = t(key) + ` <span class="col-info" title="${t('infoScore')}">i</span>`;
    } else {
      el.textContent = t(key);
    }
  });
  document.querySelectorAll(".section-hint[data-hint-key]").forEach(el => {
    el.setAttribute("data-tip", t(el.dataset.hintKey));
  });
}

// INST helpers
function isInst(row) { return (row.ranks?.["1M"] ?? 999) <= 40 && (row.ranks?.["3M"] ?? 999) <= 40; }
function instTag()   { return `<span class="pick-tag tag-inst">${t("tagInst")}</span>`; }

function finvizUrl(ticker) {
  if (!ticker) return "";
  return `https://finviz.com/screener.ashx?v=211&f=cap_smallover%2Cind_${ticker}%2Csh_avgvol_o500%2Csh_price_o7%2Cta_highlow52w_a70h%2Cta_sma50_pa&ft=4&o=-low52w`;
}

function perfClass(pct) {
  if (pct === null || pct === undefined) return "perf-0";
  if (pct >= 4)    return "perf-5";
  if (pct >= 2)    return "perf-4";
  if (pct >= 1)    return "perf-3";
  if (pct >= 0.25) return "perf-2";
  if (pct > 0)     return "perf-1";
  if (pct === 0)   return "perf-0";
  if (pct > -0.25) return "perf-n1";
  if (pct > -1)    return "perf-n2";
  if (pct > -2)    return "perf-n3";
  if (pct > -4)    return "perf-n4";
  return "perf-n5";
}

function fmtPct(v) {
  if (v === null || v === undefined) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}

function buildSparkline(ranks, maxRank) {
  const W = 90, H = 24, pad = 3;
  const n = SPARKLINE_ORDER.length;
  const points = SPARKLINE_ORDER.map((tf, i) => {
    const x = pad + (i / (n - 1)) * (W - 2 * pad);
    const rank = ranks[tf] ?? maxRank;
    const y = pad + ((rank - 1) / Math.max(maxRank - 1, 1)) * (H - 2 * pad);
    return [x, y];
  });
  const polyline = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const color = "#58a6ff";
  const dots = points.map(([x, y]) =>
    `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="1.8" fill="${color}"/>`
  ).join("");
  return `<svg class="sparkline" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
    <polyline points="${polyline}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
    ${dots}
  </svg>`;
}

// ─── Heatmap ───────────────────────────────────────────────────────────
let _sortState = { col: "score", dir: 1 };
let _instFilter = false;
let _lastIndustries = null;
let _lastPayload = null;

function sortedEntries(industries) {
  const entries = Object.entries(industries);
  const { col, dir } = _sortState;
  return entries.sort(([nameA, a], [nameB, b]) => {
    let va, vb;
    if (col === "score")         { va = a.composite;    vb = b.composite; }
    else if (col === "accel")    { va = a.acceleration; vb = b.acceleration; }
    else if (col === "industry") { return dir * nameA.localeCompare(nameB); }
    else                         { va = a.perfs[col] ?? -Infinity; vb = b.perfs[col] ?? -Infinity; }
    return dir * (va - vb);
  });
}

function renderHeatmap(industries) {
  _lastIndustries = industries;
  const tbody = document.getElementById("heatmap-body");
  let sorted = sortedEntries(industries);
  if (_instFilter) sorted = sorted.filter(([, row]) => isInst(row));

  document.querySelectorAll("#heatmap-table thead th[data-col]").forEach(th => {
    const col = th.dataset.col;
    const isActive = col === _sortState.col;
    th.classList.toggle("sort-active", isActive);
    const labelMap = { industry: "colIndustry", score: "colScore", accel: "colAccel" };
    const label = labelMap[col] ? t(labelMap[col]) : col;
    const arrow = isActive ? (_sortState.dir === 1 ? " ▲" : " ▼") : "";
    const tipKey = col === "score" ? "infoScore" : col === "accel" ? "infoAccel" : null;
    const icon = tipKey ? ` <span class="col-info" title="${t(tipKey)}">i</span>` : "";
    th.innerHTML = label + arrow + icon;
  });

  const maxRank = Object.keys(industries).length;
  const rows = sorted.map(([name, row], idx) => {
    const perfCells = TIMEFRAMES.map(tf => {
      const v = row.perfs[tf];
      return `<td class="${perfClass(v)}">${fmtPct(v)}</td>`;
    }).join("");
    const accelVal = row.acceleration;
    const accelCls = accelVal > 0 ? "accel-pos" : accelVal < 0 ? "accel-neg" : "accel-neu";
    const accelStr = accelVal > 0 ? `+${accelVal}` : `${accelVal}`;
    const url = finvizUrl(row.ticker);
    const nameCell = url
      ? `<a class="pick-link" href="${url}" target="_blank" rel="noopener">${name} <span class="link-arrow">↗</span></a>`
      : name;
    const instMark = isInst(row) ? " " + instTag() : "";
    return `<tr>
      <td class="rank-col">${idx + 1}</td>
      <td class="industry-col" title="${name}">${nameCell}${instMark}</td>
      ${perfCells}
      <td class="score-col">${row.composite.toFixed(2)}</td>
      <td class="${accelCls}">${accelStr}</td>
      <td class="sparkline-cell">${buildSparkline(row.ranks, maxRank)}</td>
    </tr>`;
  });

  tbody.innerHTML = rows.join("") || `<tr><td colspan="10" class="empty-msg">${t("noData")}</td></tr>`;
}

function initInstToggle() {
  const btn = document.getElementById("inst-toggle");
  btn.addEventListener("click", () => {
    _instFilter = !_instFilter;
    btn.classList.toggle("active", _instFilter);
    if (_lastIndustries) renderHeatmap(_lastIndustries);
  });
}

function initSortHeaders() {
  document.querySelectorAll("#heatmap-table thead th[data-col]").forEach(th => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (_sortState.col === col) _sortState.dir *= -1;
      else { _sortState.col = col; _sortState.dir = (col === "score" || col === "industry") ? 1 : -1; }
      if (_lastIndustries) renderHeatmap(_lastIndustries);
    });
  });
}

// ─── Top 10 cards ──────────────────────────────────────────────────────
function renderCards(industries) {
  const container = document.getElementById("cards-row");
  const allEntries = Object.entries(industries);
  const cards = TIMEFRAMES.map(tf => {
    const sorted = allEntries
      .filter(([, row]) => row.perfs[tf] !== null && row.perfs[tf] !== undefined)
      .sort(([, a], [, b]) => b.perfs[tf] - a.perfs[tf])
      .slice(0, 10);
    const rows = sorted.map(([name, row], i) => {
      const v = row.perfs[tf];
      const url = finvizUrl(row.ticker);
      const nameEl = url
        ? `<a class="card-name pick-link" href="${url}" target="_blank" rel="noopener" title="${name}">${name}</a>`
        : `<span class="card-name" title="${name}">${name}</span>`;
      const instMark = isInst(row) ? " " + instTag() : "";
      return `<div class="card-row">
        <span class="card-rank">${i + 1}</span>
        <span class="card-name-wrap">${nameEl}${instMark}</span>
        <span class="badge ${v >= 0 ? "badge-pos" : "badge-neg"}">${fmtPct(v)}</span>
      </div>`;
    }).join("");
    return `<div class="card"><div class="card-header">${tf}</div>${rows}</div>`;
  });
  container.innerHTML = cards.join("");
}

let _top10View = "cards";
function renderBarChart(industries) {
  const container = document.getElementById("bars-view");
  const entries = Object.entries(industries);
  const TFS = ["1M", "3M"];
  const panels = TFS.map(tf => {
    const sorted = entries.filter(([, row]) => row.perfs[tf] != null).sort(([, a], [, b]) => b.perfs[tf] - a.perfs[tf]);
    const maxVal = Math.max(...sorted.map(([, r]) => Math.abs(r.perfs[tf])), 0.01);
    const bars = sorted.map(([name, row]) => {
      const v = row.perfs[tf];
      const pct = Math.min(Math.abs(v) / maxVal * 100, 100).toFixed(1);
      const cls = v >= 0 ? "bar-fill-pos" : "bar-fill-neg";
      const url = finvizUrl(row.ticker);
      const nameEl = url
        ? `<a class="pick-link bar-label" href="${url}" target="_blank" rel="noopener">${name}</a>`
        : `<span class="bar-label">${name}</span>`;
      const instMark = isInst(row) ? " " + instTag() : "";
      return `<div class="bar-row">
        <span class="bar-name-wrap">${nameEl}${instMark}</span>
        <div class="bar-track"><div class="bar-fill ${cls}" style="width:${pct}%"></div></div>
        <span class="bar-value ${v >= 0 ? "accel-pos" : "accel-neg"}">${fmtPct(v)}</span>
      </div>`;
    }).join("");
    const months = tf === "1M" ? "1 MONTH" : "3 MONTH";
    return `<div class="barchart-panel">
      <div class="barchart-title">${months} PERFORMANCE</div>
      <div class="barchart-body">${bars}</div>
    </div>`;
  });
  container.innerHTML = panels.join("");
}

function renderTop10(industries) {
  if (_top10View === "bars") {
    document.getElementById("cards-row").classList.add("hidden");
    document.getElementById("bars-view").classList.remove("hidden");
    renderBarChart(industries);
  } else {
    document.getElementById("bars-view").classList.add("hidden");
    document.getElementById("cards-row").classList.remove("hidden");
    renderCards(industries);
  }
}

function initViewToggle() {
  document.querySelectorAll(".view-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".view-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      _top10View = btn.dataset.view;
      if (_lastIndustries) renderTop10(_lastIndustries);
    });
  });
}

// ─── Movers ────────────────────────────────────────────────────────────
let _lastHistory = null;
let _activePeriodDays = 7;

function computeMovers(history, periodDays) {
  if (!history || history.length < 2) return null;
  const today = history[history.length - 1];
  const todayDate = new Date(today.date);
  const cutoff = new Date(todayDate.getTime() - periodDays * 86400000);
  let past = null;
  for (let i = history.length - 2; i >= 0; i--) {
    if (new Date(history[i].date) <= cutoff) { past = history[i]; break; }
  }
  if (!past) return null;

  const rankOf = (scores) => {
    const sorted = Object.entries(scores).sort(([, a], [, b]) => a.c - b.c);
    return Object.fromEntries(sorted.map(([n], i) => [n, i + 1]));
  };
  const todayRanks = rankOf(today.scores);
  const pastRanks  = rankOf(past.scores);

  const deltas = Object.keys(todayRanks).filter(n => pastRanks[n] !== undefined).map(name => ({
    name,
    delta:     pastRanks[name] - todayRanks[name],
    todayRank: todayRanks[name],
    ticker:    today.scores[name]?.t ?? "",
  }));

  return {
    rising:   [...deltas].sort((a, b) => b.delta - a.delta).slice(0, 10),
    fading:   [...deltas].sort((a, b) => a.delta - b.delta).slice(0, 10),
    pastDate: past.date,
  };
}

function moverRow(item) {
  const url = finvizUrl(item.ticker);
  const nameEl = url
    ? `<a class="pick-link mover-name" href="${url}" target="_blank" rel="noopener">${item.name} <span class="link-arrow">↗</span></a>`
    : `<span class="mover-name">${item.name}</span>`;
  const instMark = (_lastIndustries?.[item.name] && isInst(_lastIndustries[item.name])) ? " " + instTag() : "";
  const sign = item.delta > 0 ? "+" : "";
  const cls  = item.delta > 0 ? "mover-delta-pos" : item.delta < 0 ? "mover-delta-neg" : "mover-delta-neu";
  return `<div class="mover-row">
    <span class="mover-rank">#${item.todayRank}</span>
    <span class="mover-name-wrap">${nameEl}${instMark}</span>
    <span class="${cls}">${sign}${item.delta}</span>
  </div>`;
}

function renderMovers(history, periodDays) {
  const risingEl = document.getElementById("movers-rising");
  const fadingEl = document.getElementById("movers-fading");
  if (!risingEl || !fadingEl) return;
  const periodLabel = document.querySelector(`.period-btn[data-days="${periodDays}"]`)?.textContent || "";
  const result = computeMovers(history, periodDays);
  if (!result) {
    const msg = `<p class="pick-empty">${t("moversNoData", periodLabel)}</p>`;
    risingEl.innerHTML = msg;
    fadingEl.innerHTML = msg;
    return;
  }
  const compareNote = `<div class="mover-compare">${t("moversCompare", result.pastDate)}</div>`;
  risingEl.innerHTML = compareNote + result.rising.map(moverRow).join("");
  fadingEl.innerHTML = compareNote + result.fading.map(moverRow).join("");
}

function updatePeriodButtons(history) {
  const btns = document.querySelectorAll(".period-btn");
  let lastAvailable = null;
  btns.forEach(btn => {
    const days = parseInt(btn.dataset.days);
    const available = computeMovers(history, days) !== null;
    btn.disabled = !available;
    if (available) lastAvailable = btn;
  });
  const activeBtn = document.querySelector(".period-btn.active");
  if (activeBtn && activeBtn.disabled && lastAvailable) {
    document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
    lastAvailable.classList.add("active");
    _activePeriodDays = parseInt(lastAvailable.dataset.days);
  }
}

function initPeriodSelector() {
  document.querySelectorAll(".period-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      _activePeriodDays = parseInt(btn.dataset.days);
      if (_lastHistory) renderMovers(_lastHistory, _activePeriodDays);
    });
  });
}

// ─── Setup Picks ───────────────────────────────────────────────────────
function buildReason(perfs, accel) {
  const tags = [];
  const lines = [];
  const p1d = perfs["1D"] ?? 0;
  const p1w = perfs["1W"] ?? 0;
  const p1m = perfs["1M"] ?? 0;
  const p3m = perfs["3M"] ?? 0;

  if (p1w >= 3 && p1m >= 5) tags.push(`<span class="pick-tag tag-hot">${t("tagHot")}</span>`);
  if (accel >= 20)           tags.push(`<span class="pick-tag tag-accel">${t("tagAccel")}</span>`);
  if (p3m < 5 && p1w >= 2 && p1m >= 3) tags.push(`<span class="pick-tag tag-fresh">${t("tagFresh")}</span>`);
  if ((perfs._rank1M ?? 999) <= 40 && (perfs._rank3M ?? 999) <= 40)
    tags.push(`<span class="pick-tag tag-inst">${t("tagInst")}</span>`);

  if (p3m < 5 && p1m >= 3)          lines.push(t("reasonFresh", (p3m >= 0 ? "+" : "") + p3m.toFixed(1), p1m.toFixed(1)));
  else if (p3m >= 5 && accel >= 10) lines.push(t("reasonSolid"));
  else                              lines.push(t("reasonSteady"));
  if (accel >= 30) lines.push(t("reasonAccel", accel));
  if (p1d >= 1)    lines.push(t("reasonIntraday", p1d.toFixed(2)));

  return `<div class="reason-tags">${tags.join("")}</div><div class="reason-text">${lines.join(" ")}</div>`;
}

function pickPriority(row, accelRankMap, compRankMap, name) {
  return 0.6 * (accelRankMap[name] ?? 999) + 0.4 * (compRankMap[name] ?? 999);
}

function renderPicks(industries) {
  const container = document.getElementById("picks-container");
  const entries = Object.entries(industries);
  const scoreRankMap = Object.fromEntries(
    [...entries].sort(([, a], [, b]) => a.composite - b.composite).map(([n], i) => [n, i + 1])
  );
  const filtered = entries.filter(([name, row]) => {
    const p1w = row.perfs["1W"] ?? 0;
    const p1m = row.perfs["1M"] ?? 0;
    return scoreRankMap[name] <= 40 && row.acceleration > 0 && p1w > 1 && p1m > 0;
  });

  const byAccel = [...filtered].sort(([, a], [, b]) => b.acceleration - a.acceleration);
  const byComp  = [...filtered].sort(([, a], [, b]) => a.composite - b.composite);
  const accelRankMap = Object.fromEntries(byAccel.map(([n], i) => [n, i + 1]));
  const compRankMap  = Object.fromEntries(byComp.map(([n], i)  => [n, i + 1]));

  const candidates = filtered
    .sort(([na, a], [nb, b]) =>
      pickPriority(a, accelRankMap, compRankMap, na) - pickPriority(b, accelRankMap, compRankMap, nb))
    .slice(0, 15);

  if (!candidates.length) {
    container.innerHTML = `<p class="pick-empty">${t("picksEmpty")}</p>`;
    return;
  }

  const cards = candidates.map(([name, row]) => {
    const p = { ...row.perfs, _rank1M: row.ranks["1M"], _rank3M: row.ranks["3M"] };
    const acc = row.acceleration;
    const accelCls = acc > 0 ? "accel-pos" : "accel-neg";
    const accelStr = acc > 0 ? `+${acc}` : `${acc}`;
    const stat = tf => `<div class="pick-stat ${perfClass(p[tf])}"><span class="stat-label">${tf}</span><span class="stat-val">${fmtPct(p[tf])}</span></div>`;
    const url = finvizUrl(row.ticker);
    const nameEl = url
      ? `<a class="pick-name pick-link" href="${url}" target="_blank" rel="noopener">${name} <span class="link-arrow">↗</span></a>`
      : `<div class="pick-name">${name}</div>`;
    return `<div class="pick-card">
      <div class="pick-card-name">${nameEl}</div>
      <div class="pick-card-stats">
        ${stat("1D")}${stat("1W")}${stat("1M")}${stat("3M")}
        <div class="pick-stat ${accelCls}"><span class="stat-label">${t("colAccel")}</span><span class="stat-val">${accelStr}</span></div>
      </div>
      <div class="pick-reason">${buildReason(p, acc)}</div>
    </div>`;
  }).join("");

  container.innerHTML = `<div class="picks-grid">${cards}</div>`;
}

function updateTimestamp(iso) {
  const el = document.getElementById("fetch-time");
  if (!iso) { el.textContent = t("notLoaded"); return; }
  const d = new Date(iso);
  el.textContent = t("updated") + d.toLocaleString("en-US", { dateStyle: "short", timeStyle: "short" });
}

function renderAll(payload) {
  if (!payload || !payload.industries || Object.keys(payload.industries).length === 0) return;
  _lastPayload = payload;
  renderHeatmap(payload.industries);
  renderTop10(payload.industries);
  renderPicks(payload.industries);
  updateTimestamp(payload.fetched_at);
}

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
      btn.classList.add("active");
      document.querySelector(`[data-panel="${btn.dataset.tab}"]`).classList.remove("hidden");
    });
  });
}

// ─── ETF Themes Tab ────────────────────────────────────────────────────
let _etfData       = null;
let _etfView       = "themes";
let _etfThemeSort  = { col: "score", dir: 1 };
let _etfListSort   = { col: "score", dir: 1 };

const THEME_COLORS = {
  "AI & Tech":      { bg: "#0d2240", fg: "#58a6ff" },
  "Semiconductors": { bg: "#1a2a4a", fg: "#79c0ff" },
  "Cybersecurity":  { bg: "#1a0d4a", fg: "#b794f4" },
  "Digital Infra":  { bg: "#0d1a40", fg: "#6fa8dc" },
  "Cloud & SaaS":   { bg: "#0d2830", fg: "#56d3d3" },
  "Nuclear":        { bg: "#2a1a00", fg: "#e3a227" },
  "Clean Energy":   { bg: "#0d2a0d", fg: "#39d353" },
  "Infrastructure": { bg: "#1a2200", fg: "#8bc34a" },
  "Defense":        { bg: "#2a1200", fg: "#ff8c42" },
  "Biotech":        { bg: "#2a0d1a", fg: "#f78ca0" },
  "EV & Mobility":  { bg: "#002a1a", fg: "#26c084" },
  "Fintech":        { bg: "#1a2a0d", fg: "#aed581" },
  "Materials":      { bg: "#2a1a0d", fg: "#ffab40" },
  "Momentum":       { bg: "#0d2a2a", fg: "#4dd0e1" },
  "Crypto":         { bg: "#2a1a00", fg: "#ffd700" },
  "Blockchain":     { bg: "#2a0d1a", fg: "#ff6ec7" },
  "Robotics":       { bg: "#0d1a2a", fg: "#85c1e9" },
};

function themeBadge(theme) {
  const c = THEME_COLORS[theme] || { bg: "#1a1a2a", fg: "#8b949e" };
  return `<span class="etf-theme-badge" style="background:${c.bg};color:${c.fg}">${theme}</span>`;
}

function priorityDot(p) {
  const colors = { 1: "#39d353", 2: "#e3a227", 3: "#8b949e" };
  return `<span class="etf-prio-dot" style="background:${colors[p] || '#8b949e'}" title="Priority ${p}"></span>`;
}

function etfYahooUrl(ticker) {
  return `https://finance.yahoo.com/quote/${ticker}`;
}

function renderEtfThemes(data) {
  const tbody = document.getElementById("etf-themes-body");
  if (!data || !data.themes) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-msg">${t("etfNoData")}</td></tr>`;
    return;
  }
  document.querySelectorAll("#etf-themes-table thead th[data-etfcol]").forEach(th => {
    const col = th.dataset.etfcol;
    const isActive = col === _etfThemeSort.col;
    th.classList.toggle("sort-active", isActive);
    const arrow = isActive ? (_etfThemeSort.dir === 1 ? " ▲" : " ▼") : "";
    if (col === "score")      th.innerHTML = t("colScore") + arrow;
    else if (col === "theme") th.textContent = "Theme" + arrow;
    else                       th.textContent = col + arrow;
  });

  let entries = Object.entries(data.themes);
  const { col, dir } = _etfThemeSort;
  entries.sort(([na, a], [nb, b]) => {
    if (col === "theme") return dir * na.localeCompare(nb);
    if (col === "score") return dir * (a.score - b.score);
    const va = a.perfs[col] ?? -Infinity;
    const vb = b.perfs[col] ?? -Infinity;
    return dir * (va - vb);
  });

  const rows = entries.map(([theme, row], idx) => {
    const perfCells = ETF_TIMEFRAMES.map(tf =>
      `<td class="${perfClass(row.perfs[tf])}">${fmtPct(row.perfs[tf])}</td>`
    ).join("");
    const etfChips = (row.etfs_p1 || []).map(tk => {
      const url = etfYahooUrl(tk);
      return `<a class="etf-ticker-chip" href="${url}" target="_blank" rel="noopener">${tk}</a>`;
    }).join(" ");
    const c = THEME_COLORS[theme] || { bg: "#1a1a2a", fg: "#8b949e" };
    return `<tr>
      <td class="rank-col">${idx + 1}</td>
      <td class="theme-col"><span class="etf-theme-badge" style="background:${c.bg};color:${c.fg}">${theme}</span></td>
      ${perfCells}
      <td class="score-col">${row.score.toFixed(1)}</td>
      <td class="etfs-col">${etfChips}</td>
    </tr>`;
  });
  tbody.innerHTML = rows.join("") || `<tr><td colspan="9" class="empty-msg">${t("etfNoData")}</td></tr>`;
}

function renderEtfList(data) {
  const tbody = document.getElementById("etf-list-body");
  if (!data || !data.etfs) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-msg">${t("etfNoData")}</td></tr>`;
    return;
  }
  document.querySelectorAll("#etf-list-table thead th[data-etflistcol]").forEach(th => {
    const col = th.dataset.etflistcol;
    const isActive = col === _etfListSort.col;
    th.classList.toggle("sort-active", isActive);
    const arrow = isActive ? (_etfListSort.dir === 1 ? " ▲" : " ▼") : "";
    const labelMap = { ticker: "Ticker", name: "Name", theme: "Theme", score: t("colScore") };
    const label = labelMap[col] ?? col;
    th.innerHTML = label + arrow;
  });

  let entries = Object.entries(data.etfs);
  const { col, dir } = _etfListSort;
  entries.sort(([ta, a], [tb, b]) => {
    if (col === "ticker") return dir * ta.localeCompare(tb);
    if (col === "name")   return dir * a.name.localeCompare(b.name);
    if (col === "theme")  return dir * a.theme.localeCompare(b.theme);
    if (col === "score")  return dir * (a.score - b.score);
    const va = a.perfs[col] ?? -Infinity;
    const vb = b.perfs[col] ?? -Infinity;
    return dir * (va - vb);
  });

  const rows = entries.map(([ticker, row], idx) => {
    const perfCells = ETF_TIMEFRAMES.map(tf =>
      `<td class="${perfClass(row.perfs[tf])}">${fmtPct(row.perfs[tf])}</td>`
    ).join("");
    const url = etfYahooUrl(ticker);
    return `<tr>
      <td class="rank-col">${idx + 1}</td>
      <td class="ticker-col">${priorityDot(row.priority)}<a class="pick-link" href="${url}" target="_blank" rel="noopener">${ticker}</a></td>
      <td class="name-col" title="${row.name}">${row.name}</td>
      <td class="theme-col">${themeBadge(row.theme)}</td>
      ${perfCells}
      <td class="score-col">${row.score.toFixed(1)}</td>
    </tr>`;
  });
  tbody.innerHTML = rows.join("") || `<tr><td colspan="10" class="empty-msg">${t("etfNoData")}</td></tr>`;
}

function renderEtfTab() {
  if (!_etfData) return;
  if (_etfView === "themes") {
    document.getElementById("etf-themes-view").classList.remove("hidden");
    document.getElementById("etf-etfs-view").classList.add("hidden");
    renderEtfThemes(_etfData);
  } else {
    document.getElementById("etf-themes-view").classList.add("hidden");
    document.getElementById("etf-etfs-view").classList.remove("hidden");
    renderEtfList(_etfData);
  }
}

function initEtfViewToggle() {
  document.querySelectorAll(".etf-view-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".etf-view-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      _etfView = btn.dataset.etfview;
      renderEtfTab();
    });
  });
}

function initEtfSortHeaders() {
  document.querySelectorAll("#etf-themes-table thead th[data-etfcol]").forEach(th => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const col = th.dataset.etfcol;
      if (_etfThemeSort.col === col) _etfThemeSort.dir *= -1;
      else { _etfThemeSort.col = col; _etfThemeSort.dir = (col === "score" || col === "theme") ? 1 : -1; }
      renderEtfThemes(_etfData);
    });
  });
  document.querySelectorAll("#etf-list-table thead th[data-etflistcol]").forEach(th => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const col = th.dataset.etflistcol;
      if (_etfListSort.col === col) _etfListSort.dir *= -1;
      else { _etfListSort.col = col; _etfListSort.dir = (col === "score" || col === "ticker" || col === "name" || col === "theme") ? 1 : -1; }
      renderEtfList(_etfData);
    });
  });
}

// ─── Boot ──────────────────────────────────────────────────────────────
applyStaticText();
initTabs();
initSortHeaders();
initInstToggle();
initPeriodSelector();
initViewToggle();
initEtfViewToggle();
initEtfSortHeaders();

(async () => {
  const loading = document.getElementById("loading");
  const errorEl = document.getElementById("error-msg");
  try {
    const [dataRes, histRes, etfRes] = await Promise.all([
      fetch("data.json"),
      fetch("history.json"),
      fetch("etf_data.json"),
    ]);
    if (!dataRes.ok) throw new Error(`data.json: HTTP ${dataRes.status}`);
    const payload = await dataRes.json();
    loading.classList.add("hidden");
    renderAll(payload);

    if (histRes.ok) {
      _lastHistory = await histRes.json();
      updatePeriodButtons(_lastHistory);
      renderMovers(_lastHistory, _activePeriodDays);
    }
    if (etfRes.ok) {
      _etfData = await etfRes.json();
      document.getElementById("etf-loading").classList.add("hidden");
      renderEtfTab();
    } else {
      document.getElementById("etf-loading").classList.add("hidden");
      document.getElementById("etf-error").textContent = t("etfNoData");
      document.getElementById("etf-error").classList.remove("hidden");
    }
  } catch (err) {
    loading.classList.add("hidden");
    errorEl.textContent = "Error loading data: " + err.message;
    errorEl.classList.remove("hidden");
  }
})();
