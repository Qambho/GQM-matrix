/** GQM Astro-Quant — dashboard client */

const PAGE_META = {
  dashboard: {
    title: "Command Dashboard",
    subtitle: "Real-time liquidation telemetry and momentum metrics",
  },
  confluence: {
    title: "Astro Confluence",
    subtitle: "Cosmic ingestion and quantitative overlap analysis",
  },
  feed: {
    title: "Live Feed",
    subtitle: "Live transaction and liquidation matrix stream",
  },
  matrix: {
    title: "GQM Matrix",
    subtitle: "Godzilla V4 MW vector lattice — Ashtottari Dasa price grid",
  },
  docs: {
    title: "Documentation",
    subtitle: "Formulas, lattice math, and reversal radar reference",
  },
};

const metrics = { totalLiqVolume: 0, longsLiquidated: 0, shortsLiquidated: 0, whaleVolume: 0 };
let rollingLiquidationHistory = [];
let rollingWhaleHistory = [];
let ws = null;
let audioArmed = false;
let lastAlarmTime = 0;
let currentPage = "dashboard";
let matrixScanInFlight = false;
let matrixFetchActive = false;
let matrixFetchTimer = null;
let matrixFetchConfigKey = null;
const MATRIX_FETCH_INTERVAL_MS = 1000;
const MATRIX_CHART_INTERVAL_MS = 5 * 60 * 1000;
let matrixChartRefreshTimer = null;
let matrixChartLastRefresh = 0;
let matrixLastPayload = null;
let wsMatrix = null;
let matrixWsUrl = null;
let matrixViewConfig = { symbol: "BTCUSDT", ppd: "200", leverage: "50" };
let matrixConfluenceState = null;
let markerAnimFrame = null;

const matrixChartState = { bounds: null, lastData: null };
const matrixMarkerManager = {
  markers: [],
  add(marker) {
    if (!marker?.id || this.markers.some((m) => m.id === marker.id)) return;
    marker._bornAt = performance.now();
    this.markers.push(marker);
    if (this.markers.length > 500) this.markers = this.markers.slice(-500);
  },
  loadHistory(list) {
    const now = performance.now();
    (list || []).forEach((m) => {
      if (!this.markers.some((x) => x.id === m.id)) {
        m._bornAt = now - 800;
        this.markers.push(m);
      }
    });
  },
  count() {
    return this.markers.length;
  },
};

const CASCADE_THRESHOLD = 300000;

const el = (id) => document.getElementById(id);

function switchPage(pageId) {
  currentPage = pageId;

  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageId);
  });

  document.querySelectorAll(".page").forEach((page) => {
    const active = page.id === `page-${pageId}`;
    page.classList.toggle("active", active);
    page.hidden = !active;
  });

  const meta = PAGE_META[pageId];
  if (meta) {
    el("page-title").textContent = meta.title;
    el("page-subtitle").textContent = meta.subtitle;
  }

  if (pageId === "matrix") {
    startMarkerAnimation();
  } else {
    stopMatrixFetch();
    disconnectMatrixWebSocket();
    stopMarkerAnimation();
  }

  if (pageId === "docs" && typeof loadDocumentationPage === "function") {
    loadDocumentationPage();
  }
}

function updateMacroStats() {
  el("stat-total-liq").textContent = `$${metrics.totalLiqVolume.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
  el("stat-longs-wiped").textContent = `$${Math.round(metrics.longsLiquidated).toLocaleString()}`;
  el("stat-shorts-wiped").textContent = `$${Math.round(metrics.shortsLiquidated).toLocaleString()}`;
  el("stat-whale-vol").textContent = `$${metrics.whaleVolume.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

  const total = metrics.longsLiquidated + metrics.shortsLiquidated;
  if (total <= 0) return;

  const longPct = (metrics.longsLiquidated / total) * 100;
  const shortPct = (metrics.shortsLiquidated / total) * 100;
  el("bar-longs").style.width = `${longPct}%`;
  el("bar-shorts").style.width = `${shortPct}%`;

  const ratio = el("stat-ratio-text");
  if (Math.abs(longPct - shortPct) < 10) {
    ratio.textContent = "NEUTRAL MIX";
    ratio.className = "stat-value muted";
  } else if (longPct > shortPct) {
    ratio.textContent = "LONGS BLEEDING";
    ratio.className = "stat-value rose";
  } else {
    ratio.textContent = "SHORTS SQUEEZING";
    ratio.className = "stat-value emerald";
  }
}

function updateMomentum() {
  const now = Date.now();
  rollingLiquidationHistory = rollingLiquidationHistory.filter((i) => now - i.timestamp <= 60000);
  rollingWhaleHistory = rollingWhaleHistory.filter((i) => now - i.timestamp <= 60000);

  const liqSum = rollingLiquidationHistory.reduce((s, i) => s + i.amount, 0);
  const whaleSum = rollingWhaleHistory.reduce((s, i) => s + i.amount, 0);
  const score = Math.round(Math.min((whaleSum / 12000000) * 50, 50) + Math.min((liqSum / 400000) * 50, 50));

  el("stat-gauge-score").textContent = `${score}%`;
  el("bar-gauge").style.width = `${score}%`;

  const banner = el("godzilla-cascade-banner");
  const badge = el("gauge-score-badge");
  const gaugeCard = el("gauge-card");

  if (score >= 85) {
    badge.textContent = "CRITICAL OVERFLOW";
    banner.className = "cascade-banner active";
    gaugeCard.classList.add("critical");
    el("cascade-alert-content").innerHTML = `
      <h3 class="rose" style="margin:0 0 8px;font-weight:800;">GODZILLA CASCADE DETECTED</h3>
      <p class="muted" style="margin:0;">Momentum at <strong class="rose">${score}%</strong></p>`;
    playAlert();
  } else if (score >= 45) {
    badge.textContent = "VOLATILITY BUILDING";
    banner.className = "cascade-banner";
    gaugeCard.classList.remove("critical");
    const pct = Math.min((liqSum / CASCADE_THRESHOLD) * 100, 100);
    el("cascade-alert-content").innerHTML = `
      <p class="muted" style="margin:0;font-family:var(--mono);font-size:0.8rem;">
        Cascade pressure: <span class="amber">${Math.round(liqSum).toLocaleString()}</span> / ${CASCADE_THRESHOLD.toLocaleString()}
        <div class="momentum-bar" style="margin-top:8px;"><div class="momentum-fill" style="width:${pct}%"></div></div>
      </p>`;
  } else {
    badge.textContent = "STABLE COMPRESSION";
    banner.className = "cascade-banner hidden";
    gaugeCard.classList.remove("critical");
  }
}

function playAlert() {
  if (!audioArmed) return;
  const now = Date.now();
  if (now - lastAlarmTime < 6000) return;
  lastAlarmTime = now;
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(90, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(350, ctx.currentTime + 0.4);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.5);
  } catch {
    /* audio unavailable */
  }
}

function processCosmicVerdict() {
  const dasaText = el("astro-dasa-input").value;
  const kpText = el("astro-kp-input").value;

  if (!dasaText && !kpText) {
    alert("Paste Jagannatha Hora or KP data first.");
    return;
  }

  const astroMap = {
    merc: { name: "Mercury", weight: 10, log: "High-velocity exchange window active" },
    ju: { name: "Jupiter", weight: 15, log: "Systemic expansion window" },
    ra: { name: "Rahu", weight: 15, log: "Speculative dilation potential" },
    ve: { name: "Venus", weight: 8, log: "Accumulation inflows detected" },
    su: { name: "Sun", weight: 5, log: "Macro trend confirmation" },
    sat: { name: "Saturn", weight: -12, log: "Structural contraction" },
    ma: { name: "Mars", weight: -10, log: "Aggressive liquidations" },
    ke: { name: "Ketu", weight: -15, log: "Flash-crash indicators" },
  };

  let cosmicScore = 50;
  const narrative = [];
  const cleanDasa = dasaText.toLowerCase();
  const cleanKp = kpText.toLowerCase();

  for (const [key, data] of Object.entries(astroMap)) {
    if (new RegExp(`\\b${key}`, "g").test(cleanDasa)) {
      cosmicScore += data.weight;
      narrative.push(`Dasa [${data.name}]: ${data.log}`);
    }
  }

  let gains = 0;
  let losses = 0;
  if (cleanKp.includes("11th") || cleanKp.includes("11 ")) gains += 2;
  if (cleanKp.includes("2nd") || cleanKp.includes("2 ")) gains += 2;
  if (cleanKp.includes("6th") || cleanKp.includes("6 ")) gains += 1;
  if (cleanKp.includes("10th") || cleanKp.includes("10 ")) gains += 1;
  if (cleanKp.includes("12th") || cleanKp.includes("12 ")) losses += 3;
  if (cleanKp.includes("8th") || cleanKp.includes("8 ")) losses += 3;
  if (cleanKp.includes("5th") || cleanKp.includes("5 ")) losses += 1;

  if (gains > losses) {
    cosmicScore += 12;
    narrative.push("KP: accumulation vectors dominant");
  } else if (losses > gains) {
    cosmicScore -= 15;
    narrative.push("KP: clearing-event risk elevated");
  }

  const quantScore = parseInt(el("stat-gauge-score").textContent, 10) || 0;
  const finalScore = Math.min(Math.max(Math.round((cosmicScore + quantScore) / 2), 0), 100);

  const panel = el("verdict-display-panel");
  panel.classList.add("glow");

  el("v-quant-state").textContent =
    quantScore > 75 ? "High velocity inflow" : quantScore > 40 ? "Moderate setup" : "Compressed inflow";
  el("v-astro-state").textContent =
    cosmicScore > 65 ? "Auspicious horizon" : cosmicScore < 40 ? "High risk alignment" : "Stable alignment";

  const badge = el("verdict-badge");
  const bias = el("v-bias-state");
  const narrativeEl = el("verdict-narrative-text");

  if (finalScore >= 65) {
    badge.textContent = "SUPREME EXPANSION";
    bias.textContent = "ACCUMULATION PUMP";
    bias.className = "verdict-bias emerald";
    narrativeEl.textContent = `[CONFIRMED] ${narrative.join(". ")}. Upward trend likely.`;
  } else if (finalScore <= 40) {
    badge.textContent = "CASCADE IMMINENT";
    bias.textContent = "VOLATILITY DUMP";
    bias.className = "verdict-bias rose";
    narrativeEl.textContent = `[RISK] ${narrative.join(". ")}. Consider risk controls.`;
  } else {
    badge.textContent = "COMPRESSION HOLD";
    bias.textContent = "SIDEWAYS CHOP";
    bias.className = "verdict-bias amber";
    narrativeEl.textContent = `[BALANCED] ${narrative.length ? narrative.join(". ") : "Baseline equilibrium"}.`;
  }
}

function handleFeedMessage(data) {
  const feed = el("feed-container");
  if (feed.querySelector(".feed-empty")) feed.innerHTML = "";

  const item = document.createElement("div");
  item.className = "feed-item";

  if (data.source === "binance_futures") {
    item.classList.add("liquidation");
    metrics.totalLiqVolume += data.usd_value;
    if (data.side === "SELL") metrics.longsLiquidated += data.usd_value;
    else metrics.shortsLiquidated += data.usd_value;
    rollingLiquidationHistory.push({ timestamp: Date.now(), amount: data.usd_value });

    item.innerHTML = `
      <div><span class="feed-tag rose">LIQ</span><strong>${data.symbol}</strong></div>
      <div class="feed-detail">
        <div class="muted" style="font-size:0.7rem;">${data.side === "BUY" ? "SHORT WIPE" : "LONG WIPE"}</div>
        <div class="rose">$${Number(data.usd_value).toLocaleString()}</div>
      </div>`;
  } else {
    item.classList.add("whale");
    metrics.whaleVolume += data.usd_value;
    rollingWhaleHistory.push({ timestamp: Date.now(), amount: data.usd_value });

    item.innerHTML = `
      <div><span class="feed-tag cyan">WHALE</span><strong>${data.from}</strong>
        <div class="muted" style="font-size:0.75rem;">${data.to}</div></div>
      <div class="feed-detail">
        <div class="cyan">${data.token}</div>
        <div>$${Number(data.usd_value).toLocaleString()}</div>
      </div>`;
  }

  feed.insertBefore(item, feed.firstChild);
  if (feed.children.length > 40) feed.removeChild(feed.lastChild);

  updateMacroStats();
  updateMomentum();
}

function setConnectionState(online) {
  const dot = el("status-indicator");
  const status = el("engine-status-text");
  dot.className = `status-dot ${online ? "online" : "offline"}`;
  status.textContent = online ? "ONLINE" : "OFFLINE";
  status.className = online ? "status-value emerald" : "status-value rose";
}

function fmtMoney(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function matrixKv(label, value) {
  return `<div class="matrix-kv"><span>${label}</span><span>${value}</span></div>`;
}

function renderConfluenceModal(confluence) {
  const body = el("aspect-modal-body");
  if (!body || !confluence) return;

  const tags = [];
  for (const aspect of confluence.pairwise_aspects || []) {
    tags.push(
      `${aspect.aspect_symbol} ${aspect.aspect_name} · ${aspect.planet_a}–${aspect.planet_b}`,
    );
  }
  if (confluence.sum_harmonic) {
    tags.push(`${confluence.sum_harmonic.aspect_symbol} ${confluence.sum_harmonic.aspect_name}`);
  }

  const tagHtml = tags.length
    ? `<div class="aspect-modal-tags">${tags.map((t) => `<span class="aspect-tag">${t}</span>`).join("")}</div>`
    : "";

  body.innerHTML = `
    ${tagHtml}
    ${(confluence.reasoning_steps || [])
      .map((step) => `<div class="aspect-modal-step">${step}</div>`)
      .join("")}`;
}

function openAspectModal() {
  if (!matrixConfluenceState) return;
  const modal = el("aspect-modal");
  if (!modal) return;
  renderConfluenceModal(matrixConfluenceState);
  modal.hidden = false;
}

function closeAspectModal() {
  const modal = el("aspect-modal");
  if (modal) modal.hidden = true;
}

function renderMatrixChartSection(data) {
  const anchor = data.anchor || {};
  const frozenPrimary = anchor.primary_vector_support ?? data.grid.primary_vector_support;
  const frozenUpper = anchor.upper_lattice_node ?? data.grid.upper_lattice_node;
  const frozenLower = anchor.lower_lattice_node ?? data.grid.lower_lattice_node;
  const livePrice = data.market.live_price ?? data.market.price;

  const levels = [
    { label: "Lower Lattice", value: frozenLower },
    { label: "Primary Vector", value: frozenPrimary },
    { label: "Spot Price (live)", value: livePrice },
    { label: "Upper Lattice", value: frozenUpper },
    { label: "Sun Anchor (5m swing)", value: anchor.sun_anchor_price ?? anchor.anchor_price ?? frozenPrimary },
  ];

  el("mx-lattice-panel").classList.remove("muted");
  el("mx-lattice-panel").innerHTML = levels
    .map((level) => {
      const near = Math.abs(level.value - data.market.price) <= data.market.atr_tolerance;
      return `<div class="matrix-level-row${near ? " highlight" : ""}">
        <span>${level.label}</span>
        <span>${fmtMoney(level.value)}</span>
      </div>`;
    })
    .join("");

  el("mx-lattice-panel").innerHTML += `
    <div class="matrix-kv"><span>Dynamic PPD</span><span>${fmtMoney(data.grid.price_per_degree)} · ${data.grid.ppd_source ?? "—"}</span></div>
    <div class="matrix-kv"><span>PPD Fallback</span><span>${fmtMoney(data.grid.fallback_ppd ?? data.grid.price_per_degree)}</span></div>
    <div class="matrix-kv"><span>Static Anchor</span><span>${fmtMoney(anchor.static_anchor ?? data.grid.static_anchor)}</span></div>
    <div class="matrix-kv"><span>Anchor Pivot</span><span>${anchor.pivot_type ?? "—"} · ${anchor.anchor_timestamp ? new Date(anchor.anchor_timestamp).toLocaleString() : "—"}</span></div>
    <div class="matrix-kv"><span>Dist. to Primary</span><span>${fmtMoney(data.distances.to_primary)}</span></div>
    <div class="matrix-kv"><span>Dist. to Upper</span><span>${fmtMoney(data.distances.to_upper)}</span></div>
    <div class="matrix-kv matrix-chart-refresh-row"><span>Grid refresh</span><span id="mx-chart-next-refresh">—</span></div>`;

  drawMatrixChart(data);
  matrixChartLastRefresh = Date.now();
  updateMatrixChartRefreshLabel();
}

function updateMatrixChartRefreshLabel() {
  const label = el("mx-chart-next-refresh");
  if (!label || !matrixChartLastRefresh) return;
  const nextAt = matrixChartLastRefresh + MATRIX_CHART_INTERVAL_MS;
  const remainingMs = Math.max(0, nextAt - Date.now());
  const minutes = Math.floor(remainingMs / (60 * 1000));
  const seconds = Math.floor((remainingMs % (60 * 1000)) / 1000);
  label.textContent =
    remainingMs <= 0 ? "due now" : `in ${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

function shouldRefreshMatrixChart() {
  return matrixChartLastRefresh === 0 || Date.now() - matrixChartLastRefresh >= MATRIX_CHART_INTERVAL_MS;
}

function renderMatrixLiveData(data) {
  const badge = el("matrix-fetch-badge");
  const banner = el("matrix-signal-banner");

  el("mx-price").textContent = fmtMoney(data.market.live_price ?? data.market.price);
  el("mx-atr").textContent = `ATR ${fmtMoney(data.market.atr)} · Tol ${fmtMoney(data.market.atr_tolerance)}`;
  el("mx-moon").textContent = `${data.celestial.moon_degree}°`;
  el("mx-aspect").textContent = data.celestial.high_volume_aspect
    ? "High-volume Moon–Mars aspect ACTIVE"
    : `${data.celestial.moon_sign || "Sidereal"} · No Moon–Mars window`;

  el("mx-mars").textContent = `${data.celestial.mars_degree}°`;
  el("mx-mercury").textContent = `${data.celestial.mercury_degree}°`;
  el("mx-mars-sign").textContent = data.celestial.mars_sign || "—";
  el("mx-mercury-sign").textContent = data.celestial.mercury_sign || "—";

  const confluence = data.celestial.confluence;
  matrixConfluenceState = confluence;
  const infoBtn = el("aspect-info-btn");
  const sumEl = el("mx-sum");
  const aspectEl = el("mx-confluence-aspect");

  if (confluence) {
    sumEl.textContent = `${confluence.longitude_sum_mod360}°`;
    aspectEl.textContent = confluence.summary;
    aspectEl.classList.toggle("emerald", confluence.has_active_aspect);
    if (infoBtn) infoBtn.hidden = false;
  } else {
    sumEl.textContent = "—";
    aspectEl.textContent = "Click Fetch for aspect geometry";
    aspectEl.classList.remove("emerald");
    if (infoBtn) infoBtn.hidden = true;
  }

  el("mx-nakshatra").textContent = data.grid.nakshatra_active;
  el("mx-lord").textContent = `Dasa Lord: ${data.grid.dasa_lord}`;
  el("mx-balance").textContent = fmtMoney(data.account.balance);
  el("mx-risk").textContent = `${data.account.risk_per_trade_pct}% risk · ${data.account.leverage}x leverage`;

  const status = data.signal.status;
  if (badge && !matrixFetchActive) {
    badge.textContent = status.replace(/_/g, " ");
  }
  banner.className = "matrix-signal-banner";
  banner.textContent = data.signal.message;

  if (status === "LONG_CONFLUENCE") banner.classList.add("long");
  else if (status === "SHORT_CONFLUENCE") banner.classList.add("short");
  else if (status === "IN_TRADE") banner.classList.add("trade");
  else banner.classList.add("hidden");

  const tradePanel = el("mx-trade-panel");
  if (data.active_trade) {
    const t = data.active_trade;
    tradePanel.classList.remove("muted");
    tradePanel.innerHTML = [
      matrixKv("Bias", t.bias),
      matrixKv("Entry", fmtMoney(t.entry)),
      matrixKv("Stop Loss", fmtMoney(t.sl)),
      matrixKv("Effective SL", fmtMoney(t.effective_sl)),
      matrixKv("Liquidation", fmtMoney(t.liq_price)),
      matrixKv("Take Profit", fmtMoney(t.tp)),
      matrixKv("Size", t.position_size.toFixed(6)),
      matrixKv("Status", t.status),
    ].join("");
  } else {
    tradePanel.classList.add("muted");
    tradePanel.innerHTML = `<span class="muted-block">No open position. Scanner monitoring lattice nodes.</span>`;
  }

  const historyPanel = el("mx-history-panel");
  if (data.trade_history.length) {
    historyPanel.classList.remove("muted");
    historyPanel.innerHTML = data.trade_history
      .map((t) => {
        const pnlClass = (t.pnl_amount ?? 0) >= 0 ? "emerald" : "rose";
        return `<div class="matrix-history-item">
          <div class="history-head">
            <span class="${t.bias === "LONG" ? "emerald" : "rose"}">${t.bias}</span>
            <span class="${pnlClass}">${fmtMoney(t.pnl_amount)}</span>
          </div>
          <div class="muted-block">${t.status} · Entry ${fmtMoney(t.entry)} → Exit ${fmtMoney(t.exit_price)}</div>
        </div>`;
      })
      .join("");
  } else {
    historyPanel.classList.add("muted");
    historyPanel.innerHTML = `<span class="muted-block">No closed trades yet.</span>`;
  }

  updateMatrixChartRefreshLabel();
}

function renderMatrixData(data) {
  matrixLastPayload = data;
  renderMatrixLiveData(data);
  if (shouldRefreshMatrixChart()) {
    renderMatrixChartSection(data);
  } else if (matrixFetchActive && matrixChartState.bounds) {
    drawMatrixChart(data);
  }
}

function digitalRoot(value) {
  let n = Math.abs(Math.round(value));
  if (n === 0) return 0;
  while (n > 9) {
    n = String(n).split("").reduce((s, d) => s + Number(d), 0);
  }
  return n;
}

function priceToZodiacDegree(price, anchor, ppd) {
  return ((price - anchor) / ppd + 360) % 360;
}

function degreeToPrice(deg, anchor, ppd) {
  return anchor + deg * ppd;
}

function angularDegreeDistance(a, b) {
  const diff = Math.abs(a - b) % 360;
  return diff > 180 ? 360 - diff : diff;
}

const CARDINAL_DEGREES = [0, 90, 180, 270];
const HARMONIC_REVERSAL_TOLERANCE = 5;
const CARDINAL_DEGREE_TOLERANCE = 2;

function livePriceToZodiacDegree(livePrice) {
  return ((livePrice % 360) + 360) % 360;
}

function buildHarmonicNodes(primaryVector, upperLattice, lowerLattice) {
  const upperSpan = upperLattice - primaryVector;
  const lowerSpan = primaryVector - lowerLattice;
  if (upperSpan <= 0 || lowerSpan <= 0) return [];

  return [
    { price: primaryVector + upperSpan / 3, side: "upper", pct: 33 },
    { price: primaryVector + (upperSpan * 2) / 3, side: "upper", pct: 66 },
    { price: primaryVector - lowerSpan / 3, side: "lower", pct: 33 },
    { price: primaryVector - (lowerSpan * 2) / 3, side: "lower", pct: 66 },
  ];
}

function isNearHarmonicNode(livePrice, nodes, tolerance = HARMONIC_REVERSAL_TOLERANCE) {
  return nodes.some((node) => Math.abs(livePrice - node.price) <= tolerance);
}

function nearCardinalDegree(deg, tolerance = CARDINAL_DEGREE_TOLERANCE) {
  for (const cardinal of CARDINAL_DEGREES) {
    if (angularDegreeDistance(deg, cardinal) <= tolerance) {
      return cardinal;
    }
  }
  return null;
}

function drawHarmonicNodes(ctx, nodes, toY, pad, plotW) {
  if (!nodes.length) return;

  ctx.save();
  ctx.setLineDash([5, 5]);
  ctx.lineWidth = 1;
  for (const node of nodes) {
    const y = toY(node.price);
    ctx.strokeStyle =
      node.side === "upper" ? "rgba(192, 132, 252, 0.32)" : "rgba(52, 211, 153, 0.32)";
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(pad.l + plotW, y);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.restore();
}

function buildMwChartModel(data) {
  const anchorBlock = data.anchor || {};
  const mw = data.mw_structure || {};
  const verticesMeta = mw.vertices || {};
  const livePrice = data.market.live_price ?? data.market.price;
  const anchorPrice = anchorBlock.sun_anchor_price ?? anchorBlock.anchor_price ?? null;
  const staticAnchor = anchorBlock.static_anchor ?? data.grid.static_anchor;
  const ppd = data.grid.price_per_degree;

  const A = verticesMeta.A || {
    label: "A",
    degree: mw.entry_degree ?? data.celestial.moon_degree,
    price: data.grid.upper_lattice_node,
  };
  const B = verticesMeta.B || {
    label: "B",
    degree: mw.entry_degree ?? data.celestial.moon_degree,
    price: data.grid.lower_lattice_node,
  };
  const C = verticesMeta.C || {
    label: "C",
    degree: mw.exit_degree ?? data.celestial.mars_degree,
    price: data.grid.upper_lattice_node,
  };
  const D = verticesMeta.D || {
    label: "D",
    degree: mw.exit_degree ?? data.celestial.mars_degree,
    price: data.grid.lower_lattice_node,
  };
  const sunCross = verticesMeta.sun_crossing || {
    label: "Sun",
    degree: anchorBlock.sun_degree_at_pivot ?? 180,
    price: anchorBlock.sun_anchor_price ?? anchorBlock.sun_crossing_price ?? anchorPrice,
    anchor_price: anchorBlock.sun_anchor_price ?? anchorPrice,
    source: "5m_last_swing",
  };

  return {
    livePrice,
    anchorPrice,
    staticAnchor,
    ppd,
    vertices: { A, B, C, D, sun_crossing: sunCross },
    lookbackHigh: anchorBlock.lookback_high,
    lookbackLow: anchorBlock.lookback_low,
    pivotType: anchorBlock.pivot_type,
    anchorTimestamp: anchorBlock.anchor_timestamp,
    moonDegreeLive: data.celestial.moon_degree,
    marsDegreeLive: data.celestial.mars_degree,
  };
}

function validateMwStructure(model, data) {
  const warnings = data.anchor_validation ? [...data.anchor_validation] : [];
  const lo = model.lookbackLow;
  const hi = model.lookbackHigh;

  console.group("[MW Validation]");
  console.log("anchor_price (frozen swing):", model.anchorPrice, "| live_price (spot):", model.livePrice);
  console.log("pivot_type:", model.pivotType, "| calibrated:", model.anchorTimestamp);
  console.log("lookback range:", lo, "–", hi);

  const audit = [
    { name: "Sun anchor (5m swing)", price: model.vertices.sun_crossing.anchor_price ?? model.vertices.sun_crossing.price, source: model.vertices.sun_crossing.source || "5m_last_swing" },
    { name: "Anchor pivot", price: model.anchorPrice, source: "5m_last_swing" },
    { name: "Live spot", price: model.livePrice, source: "live_5m_feed" },
  ];

  for (const item of audit) {
    console.log(`[MW] ${item.name} raw price=${item.price} source=${item.source}`);
    if (lo != null && hi != null && (item.price < lo * 0.85 || item.price > hi * 1.15)) {
      if (item.source !== "live_5m_feed") {
        const msg = `${item.name} price ${item.price} outside expected range [${lo}, ${hi}]`;
        warnings.push(msg);
        console.warn(msg);
      }
    }
  }

  if (Math.abs(model.anchorPrice - model.livePrice) > (hi - lo || model.livePrice * 0.05)) {
    console.warn(
      "[MW] Grid divergence: anchor_price vs live_price gap =",
      Math.abs(model.anchorPrice - model.livePrice).toFixed(2),
    );
  }

  if (warnings.length) console.warn("Validation warnings:", warnings);
  else console.log("All anchor sources validated.");
  console.groupEnd();
  return warnings;
}

function lerpDegree(from, to, t) {
  const diff = ((to - from + 540) % 360) - 180;
  return (from + diff * t + 360) % 360;
}

function buildMwWaveGeometry(vertices) {
  const { A, B, C, D, sun_crossing: sunMeta } = vertices;
  const entryUpper = A.price;
  const entryLower = B.price;
  const exitUpper = C.price;
  const exitLower = D.price;
  const primary = sunMeta.anchor_price ?? sunMeta.price;
  const band = (entryUpper - entryLower) / 4;

  const entryDeg = A.degree;
  const exitDeg = C.degree;
  const centerDeg = lerpDegree(entryDeg, exitDeg, 0.5);
  const diamondDeg = sunMeta.degree;

  const legStub = band * 0.58;

  // Curve anchors sit ON the entry/exit verticals at peak/trough prices.
  // Stub starts (A/B/C/D) extend beyond the anchor: below peaks (M), above troughs (W).
  const pts = {
    M3: { label: "M3", degree: exitDeg, price: exitUpper, role: "exit_peak_anchor" },
    C: { label: "C", degree: exitDeg, price: exitUpper - legStub, role: "exit_m_start" },
    M1: { label: "M1", degree: entryDeg, price: entryUpper, role: "entry_peak_anchor" },
    A: { label: "A", degree: entryDeg, price: entryUpper - legStub, role: "entry_m_start" },
    W3: { label: "W3", degree: exitDeg, price: exitLower, role: "exit_trough_anchor" },
    D: { label: "D", degree: exitDeg, price: exitLower + legStub, role: "exit_w_start" },
    W1: { label: "W1", degree: entryDeg, price: entryLower, role: "entry_trough_anchor" },
    B: { label: "B", degree: entryDeg, price: entryLower + legStub, role: "entry_w_start" },
    M2: { label: "M2", degree: centerDeg, price: primary, role: "m_valley" },
    W2: { label: "W2", degree: centerDeg, price: primary, role: "w_peak" },
    sun_crossing: { ...sunMeta, degree: diamondDeg, price: primary },
  };

  const mKeys = ["C", "M3", "M2", "M1", "A"];
  const wKeys = ["D", "W3", "W2", "W1", "B"];

  return {
    pts,
    mPath: mKeys,
    wPath: wKeys,
    entryDeg,
    exitDeg,
    centerDeg,
    diamondDeg,
    primary,
    band,
  };
}

function measureLabelBox(ctx, title, lines, titleSize = 10, bodySize = 9) {
  ctx.font = `bold ${titleSize}px JetBrains Mono, monospace`;
  let maxW = title ? ctx.measureText(title).width : 0;
  ctx.font = `${bodySize}px JetBrains Mono, monospace`;
  for (const line of lines) {
    maxW = Math.max(maxW, ctx.measureText(line).width);
  }
  const padX = 8;
  const padY = 6;
  const titleH = title ? 14 : 0;
  const bodyH = lines.length * 12;
  return {
    width: maxW + padX * 2,
    height: titleH + bodyH + padY * 2,
    padX,
    padY,
    titleH,
  };
}

function drawLabelBox(ctx, anchorX, anchorY, title, lines, opts = {}) {
  const {
    accent = "#8b9cb8",
    bg = "rgba(10, 16, 30, 0.92)",
    border = "rgba(255,255,255,0.12)",
    position = "right-top",
  } = opts;

  const box = measureLabelBox(ctx, title, lines);
  let bx = anchorX;
  let by = anchorY;

  switch (position) {
    case "right-top":
      bx = anchorX + 12;
      by = anchorY - box.height - 8;
      break;
    case "right-bottom":
      bx = anchorX + 12;
      by = anchorY + 12;
      break;
    case "left-top":
      bx = anchorX - box.width - 12;
      by = anchorY - box.height - 8;
      break;
    case "left-bottom":
      bx = anchorX - box.width - 12;
      by = anchorY + 12;
      break;
    case "center-above":
      bx = anchorX - box.width / 2;
      by = anchorY - box.height - 14;
      break;
    default:
      break;
  }

  ctx.fillStyle = bg;
  ctx.strokeStyle = border;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(bx, by, box.width, box.height, 6);
  ctx.fill();
  ctx.stroke();

  let ty = by + box.padY;
  if (title) {
    ctx.fillStyle = accent;
    ctx.font = "bold 10px JetBrains Mono, monospace";
    ctx.fillText(title, bx + box.padX, ty + 10);
    ty += box.titleH;
  }

  ctx.fillStyle = "#8b9cb8";
  ctx.font = "9px JetBrains Mono, monospace";
  lines.forEach((line, i) => {
    ctx.fillText(line, bx + box.padX, ty + box.padY + i * 12 + 8);
  });

  return { x: bx, y: by, width: box.width, height: box.height };
}

function drawChartLabel(ctx, x, y, lines, opts = {}) {
  const {
    dx = 10,
    dy = -10,
    align = "left",
    color = "#8b9cb8",
    title = null,
    titleColor = "#e8eefc",
    lineHeight = 11,
  } = opts;

  if (title) {
    ctx.fillStyle = titleColor;
    ctx.font = "bold 10px JetBrains Mono, monospace";
    const titleX = align === "right" ? x - dx - ctx.measureText(title).width : x + dx;
    ctx.fillText(title, titleX, y + dy);
  }

  ctx.fillStyle = color;
  ctx.font = "9px JetBrains Mono, monospace";
  const baseY = y + dy + (title ? lineHeight : 0);
  lines.forEach((line, i) => {
    const textW = ctx.measureText(line).width;
    const lx = align === "right" ? x - dx - textW : x + dx;
    ctx.fillText(line, lx, baseY + i * lineHeight);
  });
}

function projectMwPoint(key, pts, toX, toY) {
  const p = pts[key];
  return { x: toX(p.degree), y: toY(p.price), meta: p, key };
}

function syncMatrixCanvasSize() {
  const canvas = el("mx-lattice-chart");
  const overlay = el("mx-markers-canvas");
  const stack = canvas?.parentElement;
  if (!canvas || !stack) return;

  const width = Math.max(640, stack.clientWidth || 640);
  const height = Math.round(width * (9 / 16));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
    if (overlay) {
      overlay.width = width;
      overlay.height = height;
    }
  }
}

function drawMWMatrixChart(data) {
  const canvas = el("mx-lattice-chart");
  const legend = el("mx-chart-legend");
  if (!canvas) return;

  syncMatrixCanvasSize();

  const model = buildMwChartModel(data);
  validateMwStructure(model, data);

  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const pad = { l: 62, r: 28, t: 36, b: 48 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;

  const { livePrice, staticAnchor, ppd, vertices } = model;
  const tol = data.market.atr_tolerance || livePrice * 0.002;
  const wave = buildMwWaveGeometry(vertices);

  const anchorBlock = data.anchor || {};
  const primaryVector = anchorBlock.primary_vector_support ?? data.grid.primary_vector_support;
  const upperLattice = anchorBlock.upper_lattice_node ?? data.grid.upper_lattice_node;
  const lowerLattice = anchorBlock.lower_lattice_node ?? data.grid.lower_lattice_node;
  const harmonicNodes = buildHarmonicNodes(primaryVector, upperLattice, lowerLattice);
  const spotDeg = livePriceToZodiacDegree(livePrice);
  const spotNearHarmonic = isNearHarmonicNode(livePrice, harmonicNodes);
  const activeCardinal = nearCardinalDegree(spotDeg);

  const allPrices = Object.values(wave.pts)
    .filter((p) => p && typeof p.price === "number")
    .map((p) => p.price)
    .concat(harmonicNodes.map((n) => n.price))
    .concat([livePrice]);
  model._yMin = Math.min(...allPrices) - tol * 2;
  model._yMax = Math.max(...allPrices) + tol * 2;
  model._yRange = model._yMax - model._yMin || 1;

  const toX = (deg360) => pad.l + (deg360 / 360) * plotW;
  const toY = (price) => pad.t + plotH - ((price - model._yMin) / model._yRange) * plotH;

  const px = {};
  for (const key of Object.keys(wave.pts)) {
    if (wave.pts[key]?.price != null) px[key] = projectMwPoint(key, wave.pts, toX, toY);
  }

  const A = px.A;
  const B = px.B;
  const C = px.C;
  const D = px.D;
  const M1 = px.M1;
  const M2 = px.M2;
  const M3 = px.M3;
  const W1 = px.W1;
  const W2 = px.W2;
  const W3 = px.W3;
  const sunMeta = wave.pts.sun_crossing;
  const diamond = {
    x: toX(wave.diamondDeg),
    y: toY(wave.primary),
    meta: sunMeta,
  };

  const vertexPoints = [A, B, C, D, M1, M2, M3, W1, W2, W3, diamond];
  const entryX = A.x;
  const exitX = C.x;
  const entryOnRight = entryX > exitX;

  const mKeys = exitX < entryX ? ["C", "M3", "M2", "M1", "A"] : ["A", "M1", "M2", "M3", "C"];
  const wKeys = exitX < entryX ? ["D", "W3", "W2", "W1", "B"] : ["B", "W1", "W2", "W3", "D"];
  wave.mPath = mKeys;
  wave.wPath = wKeys;

  const drawPath = (keys, color, width) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    keys.forEach((key, i) => {
      const pt = px[key];
      if (!pt) return;
      if (i === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.stroke();
  };

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#070b14";
  ctx.fillRect(0, 0, W, H);

  if (entryOnRight) {
    ctx.fillStyle = "rgba(52, 211, 153, 0.04)";
    ctx.fillRect(entryX - plotW * 0.02, pad.t, W - pad.r - entryX + plotW * 0.02, plotH);
    ctx.fillStyle = "rgba(251, 113, 133, 0.04)";
    ctx.fillRect(pad.l, pad.t, exitX - pad.l + plotW * 0.02, plotH);
  } else {
    ctx.fillStyle = "rgba(52, 211, 153, 0.04)";
    ctx.fillRect(pad.l, pad.t, entryX - pad.l + plotW * 0.02, plotH);
    ctx.fillStyle = "rgba(251, 113, 133, 0.04)";
    ctx.fillRect(exitX - plotW * 0.02, pad.t, W - pad.r - exitX + plotW * 0.02, plotH);
  }

  ctx.strokeStyle = "rgba(255,255,255,0.06)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 8; i++) {
    const deg = (i / 8) * 360;
    const normalizedDeg = deg >= 360 ? 0 : deg;
    const x = pad.l + (i / 8) * plotW;
    const goldHighlight =
      activeCardinal != null && angularDegreeDistance(normalizedDeg, activeCardinal) < 0.01;
    ctx.strokeStyle = goldHighlight ? "rgba(251, 191, 36, 0.85)" : "rgba(255,255,255,0.06)";
    ctx.lineWidth = goldHighlight ? 2 : 1;
    ctx.beginPath();
    ctx.moveTo(x, pad.t);
    ctx.lineTo(x, pad.t + plotH);
    ctx.stroke();
  }
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const price = model._yMin + (i / 5) * model._yRange;
    const y = toY(price);
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(pad.l + plotW, y);
    ctx.stroke();
  }

  drawHarmonicNodes(ctx, harmonicNodes, toY, pad, plotW);

  const dSize = 14;
  ctx.fillStyle = "rgba(251, 191, 36, 0.2)";
  ctx.strokeStyle = "rgba(251, 191, 36, 0.85)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(diamond.x, diamond.y - dSize);
  ctx.lineTo(diamond.x + dSize, diamond.y);
  ctx.lineTo(diamond.x, diamond.y + dSize);
  ctx.lineTo(diamond.x - dSize, diamond.y);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();

  // Entry / exit vertical legs (stub → curve anchor → stub)
  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(A.x, A.y);
  ctx.lineTo(M1.x, M1.y);
  ctx.lineTo(W1.x, W1.y);
  ctx.lineTo(B.x, B.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(C.x, C.y);
  ctx.lineTo(M3.x, M3.y);
  ctx.lineTo(W3.x, W3.y);
  ctx.lineTo(D.x, D.y);
  ctx.stroke();

  // M line (upper wave) — purple
  drawPath(wave.mPath, "#c084fc", 2.5);

  // W line (lower wave) — green
  drawPath(wave.wPath, "#34d399", 2.5);

  // Diamond between M and W (diagonal rails)
  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(M1.x, M1.y);
  ctx.lineTo(W2.x, W2.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(W1.x, W1.y);
  ctx.lineTo(M2.x, M2.y);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(M2.x, M2.y);
  ctx.lineTo(W2.x, W2.y);
  ctx.stroke();
  ctx.setLineDash([]);

  const moonRawPrice = degreeToPrice(model.moonDegreeLive, staticAnchor, ppd);
  const marsRawPrice = degreeToPrice(model.marsDegreeLive, staticAnchor, ppd);
  const moonAtEntry = angularDegreeDistance(model.moonDegreeLive, wave.entryDeg) < 4;
  const marsAtExit = angularDegreeDistance(model.marsDegreeLive, wave.exitDeg) < 4;

  const labelNode = (pt, color, boxPosition, titleOverride) => {
    if (!pt) return;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2);
    ctx.fill();
    drawLabelBox(ctx, pt.x, pt.y, titleOverride || pt.meta.label, [fmtMoney(pt.meta.price), `${pt.meta.degree.toFixed(1)}°`], {
      accent: color,
      position: boxPosition,
    });
  };

  labelNode(M3, "#c084fc", "right-top", marsAtExit ? "M3 · ♂ Mars" : "M3");
  labelNode(W3, "#34d399", "right-bottom");
  labelNode(M1, "#c084fc", "left-top", moonAtEntry ? "M1 · ☽ Moon" : "M1");
  labelNode(W1, "#34d399", "left-bottom");

  ctx.fillStyle = "rgba(255,255,255,0.35)";
  ctx.font = "bold 9px JetBrains Mono, monospace";
  for (const stub of [A, B, C, D]) {
    ctx.fillStyle = stub.meta.role.includes("_m_") ? "rgba(192,132,252,0.5)" : "rgba(52,211,153,0.5)";
    ctx.beginPath();
    ctx.arc(stub.x, stub.y, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.35)";
    ctx.fillText(stub.meta.label, stub.x + (stub.x > (entryX + exitX) / 2 ? -14 : 6), stub.y + 4);
  }

  drawLabelBox(
    ctx,
    diamond.x,
    diamond.y,
    "☉ Sun",
    [fmtMoney(sunMeta.anchor_price ?? sunMeta.price), `${sunMeta.degree.toFixed(1)}°`, "5m swing"],
    { accent: "#fbbf24", position: "center-above" },
  );

  ctx.strokeStyle = "rgba(52, 211, 153, 0.55)";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(entryX, pad.t);
  ctx.lineTo(entryX, pad.t + plotH);
  ctx.stroke();
  ctx.strokeStyle = "rgba(251, 113, 133, 0.55)";
  ctx.beginPath();
  ctx.moveTo(exitX, pad.t);
  ctx.lineTo(exitX, pad.t + plotH);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = "rgba(52, 211, 153, 0.7)";
  ctx.font = "600 10px Inter, sans-serif";
  ctx.fillText("ENTRY", entryX + 6, pad.t + 12);
  ctx.fillStyle = "rgba(251, 113, 133, 0.7)";
  ctx.fillText("EXIT", exitX + 6, pad.t + 12);

  const plotPlanetMarker = (deg, price, color, title, skipWhenAtLeg) => {
    if (skipWhenAtLeg) return;
    const x = toX(deg);
    const y = toY(price);

    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 4]);
    ctx.globalAlpha = 0.45;
    ctx.beginPath();
    ctx.moveTo(x, pad.t);
    ctx.lineTo(x, pad.t + plotH);
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.arc(x, y, 2, 0, Math.PI * 2);
    ctx.fill();

    const position =
      x > (entryX + exitX) / 2
        ? y < pad.t + plotH * 0.45
          ? "left-bottom"
          : "left-top"
        : y < pad.t + plotH * 0.45
          ? "right-bottom"
          : "right-top";
    drawLabelBox(ctx, x, y, title, [fmtMoney(price), `${deg.toFixed(1)}°`], {
      accent: color,
      position,
    });
  };

  plotPlanetMarker(model.moonDegreeLive, moonRawPrice, "#c084fc", "☽ Moon", moonAtEntry);
  plotPlanetMarker(model.marsDegreeLive, marsRawPrice, "#fb7185", "♂ Mars", marsAtExit);
  const spotColor = spotNearHarmonic ? "#ef4444" : "#22d3ee";
  const spotTitle = spotNearHarmonic ? "Spot · Reversal" : "Spot";
  plotPlanetMarker(spotDeg, livePrice, spotColor, spotTitle, false);

  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t + plotH);
  ctx.lineTo(pad.l + plotW, pad.t + plotH);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + plotH);
  ctx.stroke();

  ctx.fillStyle = "#8b9cb8";
  ctx.font = "11px JetBrains Mono, monospace";
  ctx.fillText("x → 360° Zodiac", pad.l + plotW / 2 - 48, H - 10);
  ctx.save();
  ctx.translate(16, pad.t + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("y Price", -22, 0);
  ctx.restore();

  ctx.font = "9px JetBrains Mono, monospace";
  for (let d = 0; d <= 360; d += 90) {
    ctx.fillText(`${d}°`, toX(d) - 10, pad.t + plotH + 16);
  }
  for (let i = 0; i <= 5; i++) {
    const price = model._yMin + (i / 5) * model._yRange;
    ctx.fillText(`$${Math.round(price).toLocaleString()}`, 4, toY(price) + 3);
  }

  if (legend) {
    legend.classList.remove("muted");
    const reversalTag = spotNearHarmonic
      ? `<span class="legend-item"><span class="legend-dot" style="background:#ef4444"></span>Reversal zone (±$${HARMONIC_REVERSAL_TOLERANCE})</span>`
      : "";
    const cardinalTag = activeCardinal != null
      ? `<span class="legend-item"><span class="legend-dot" style="background:#fbbf24"></span>Cardinal ${activeCardinal}° window</span>`
      : "";
    legend.innerHTML = `
      <span class="legend-item"><span class="legend-dot" style="background:#c084fc"></span>M line (upper)</span>
      <span class="legend-item"><span class="legend-dot" style="background:#34d399"></span>W line (lower)</span>
      <span class="legend-item"><span class="legend-dot" style="background:#fbbf24"></span>☉ Sun @ ${fmtMoney(sunMeta.anchor_price ?? sunMeta.price)}</span>
      <span class="legend-item"><span class="legend-dot" style="background:${spotColor}"></span>Live ${fmtMoney(livePrice)} @ ${spotDeg.toFixed(1)}°</span>
      ${reversalTag}
      ${cardinalTag}
      <span class="legend-item">Markers: ${matrixMarkerManager.count()}</span>`;
  }

  matrixChartState.bounds = { pad, plotW, plotH, yMin: model._yMin, yMax: model._yMax, W, H };
  matrixChartState.harmonicNodes = harmonicNodes;
  matrixChartState.spotNearHarmonic = spotNearHarmonic;
  matrixChartState.activeCardinal = activeCardinal;
  matrixChartState.lastData = data;
  drawMatrixMarkers(performance.now());
}

function projectMarker(marker, bounds) {
  const yRange = bounds.yMax - bounds.yMin || 1;
  const x = bounds.pad.l + (marker.x_degree / 360) * bounds.plotW;
  const y =
    bounds.pad.t +
    bounds.plotH -
    ((marker.y_price - bounds.yMin) / yRange) * bounds.plotH;
  return { x, y };
}

function drawMatrixMarkers(animTime) {
  const canvas = el("mx-markers-canvas");
  const bounds = matrixChartState.bounds;
  if (!canvas || !bounds) return;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  for (const marker of matrixMarkerManager.markers) {
    const born = marker._bornAt || animTime;
    const age = animTime - born;
    const fade = Math.min(1, age / 500);
    const pulse = 0.88 + 0.12 * Math.sin(animTime / 380 + marker.x_degree * 0.05);
    const { x, y } = projectMarker(marker, bounds);
    const radius = 6.5 * pulse * fade;

    const glow = ctx.createRadialGradient(x, y, 0, x, y, radius * 3);
    glow.addColorStop(0, marker.color || "#22d3ee");
    glow.addColorStop(1, "transparent");
    ctx.globalAlpha = 0.4 * fade;
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y, radius * 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.globalAlpha = fade;
    ctx.fillStyle = marker.color || "#22d3ee";
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.9)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.globalAlpha = 1;

    if (fade > 0.85) {
      ctx.fillStyle = marker.color;
      ctx.font = "9px JetBrains Mono, monospace";
      ctx.fillText(marker.signal_type, x + 10, y - 6);
    }
  }
}

function startMarkerAnimation() {
  if (markerAnimFrame) return;
  const loop = (t) => {
    drawMatrixMarkers(t);
    markerAnimFrame = requestAnimationFrame(loop);
  };
  markerAnimFrame = requestAnimationFrame(loop);
}

function stopMarkerAnimation() {
  if (markerAnimFrame) {
    cancelAnimationFrame(markerAnimFrame);
    markerAnimFrame = null;
  }
  const overlay = el("mx-markers-canvas");
  if (overlay) overlay.getContext("2d").clearRect(0, 0, overlay.width, overlay.height);
}

function matrixConfigKey(controls) {
  return `${controls.symbol.toUpperCase()}|${controls.ppd}|${controls.leverage}`;
}

function getMatrixControls() {
  return {
    symbol: el("matrix-symbol")?.value || "BTCUSDT",
    ppd: el("matrix-ppd")?.value || "200",
    leverage: el("matrix-leverage")?.value || "50",
  };
}

function buildMatrixWsUrl(controls) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams({
    symbol: controls.symbol,
    price_per_degree: controls.ppd,
    leverage: controls.leverage,
  });
  return `${protocol}//${location.host}/ws/matrix?${params.toString()}`;
}

function matrixPayloadMatchesView(data) {
  if (!data?.symbol) return true;
  return data.symbol.toUpperCase() === matrixViewConfig.symbol.toUpperCase();
}

function markerMatchesView(marker) {
  const symbol = marker?.metadata?.symbol;
  if (!symbol) return true;
  return symbol.toUpperCase() === matrixViewConfig.symbol.toUpperCase();
}

function handleMatrixEvent(msg) {
  if (msg.event === "matrix_history") {
    if (msg.symbol && msg.symbol.toUpperCase() !== matrixViewConfig.symbol.toUpperCase()) {
      return;
    }
    matrixMarkerManager.loadHistory(msg.markers);
    drawMatrixMarkers(performance.now());
    return;
  }
  if (msg.event === "matrix_frame" && msg.data) {
    if (!matrixPayloadMatchesView(msg.data)) return;
    if (matrixFetchActive) return;
    renderMatrixData(msg.data);
    return;
  }
  if (msg.event === "matrix_signal" && msg.marker) {
    if (!markerMatchesView(msg.marker)) return;
    matrixMarkerManager.add(msg.marker);
    drawMatrixMarkers(performance.now());
    const badge = el("matrix-fetch-badge");
    if (badge && matrixFetchActive) badge.textContent = "LIVE";
  }
}

function syncMatrixWebSocket() {
  const controls = getMatrixControls();
  matrixViewConfig = controls;
  const url = buildMatrixWsUrl(controls);

  if (
    wsMatrix &&
    (wsMatrix.readyState === WebSocket.OPEN || wsMatrix.readyState === WebSocket.CONNECTING) &&
    matrixWsUrl === url
  ) {
    return;
  }

  disconnectMatrixWebSocket();
  matrixWsUrl = url;
  wsMatrix = new WebSocket(url);

  wsMatrix.onmessage = (e) => {
    try {
      handleMatrixEvent(JSON.parse(e.data));
    } catch {
      /* ignore malformed payloads */
    }
  };

  wsMatrix.onclose = () => {
    wsMatrix = null;
    matrixWsUrl = null;
    if (currentPage === "matrix" && matrixFetchActive) {
      setTimeout(syncMatrixWebSocket, 3000);
    }
  };
}

function disconnectMatrixWebSocket() {
  if (wsMatrix) {
    wsMatrix.onclose = null;
    wsMatrix.close();
    wsMatrix = null;
    matrixWsUrl = null;
  }
}

function drawMatrixChart(data) {
  drawMWMatrixChart(data);
}

function setMatrixFetchLoading(loading) {
  const btn = el("matrix-fetch-btn");
  if (!btn) return;
  btn.classList.toggle("loading", loading);
  btn.setAttribute("aria-busy", loading ? "true" : "false");
}

function setMatrixFetchLive(active) {
  const btn = el("matrix-fetch-btn");
  if (btn) btn.classList.toggle("live", active);
}

function stopMatrixChartRefreshTimer() {
  if (matrixChartRefreshTimer) {
    clearInterval(matrixChartRefreshTimer);
    matrixChartRefreshTimer = null;
  }
}

function startMatrixChartRefreshTimer() {
  stopMatrixChartRefreshTimer();
  matrixChartRefreshTimer = setInterval(() => {
    if (!matrixFetchActive || !matrixLastPayload) return;
    if (shouldRefreshMatrixChart()) {
      renderMatrixChartSection(matrixLastPayload);
    } else {
      updateMatrixChartRefreshLabel();
    }
  }, 60 * 1000);
}

function stopMatrixFetch() {
  matrixFetchActive = false;
  matrixFetchConfigKey = null;
  if (matrixFetchTimer) {
    clearInterval(matrixFetchTimer);
    matrixFetchTimer = null;
  }
  stopMatrixChartRefreshTimer();
  matrixChartLastRefresh = 0;
  matrixLastPayload = null;
  setMatrixFetchLive(false);
  setMatrixFetchLoading(false);
  const badge = el("matrix-fetch-badge");
  if (badge) badge.textContent = "IDLE";
}

async function fetchMatrixTick() {
  if (!matrixFetchActive || matrixScanInFlight) return;

  const controls = getMatrixControls();
  if (matrixFetchConfigKey !== matrixConfigKey(controls)) return;

  const { symbol, ppd, leverage } = controls;
  const badge = el("matrix-fetch-badge");

  matrixScanInFlight = true;
  setMatrixFetchLoading(true);

  try {
    const url = `/api/matrix/scan?symbol=${encodeURIComponent(symbol)}&price_per_degree=${encodeURIComponent(ppd)}&leverage=${encodeURIComponent(leverage)}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Matrix fetch failed.");
    if (!matrixFetchActive || !matrixPayloadMatchesView(payload)) return;
    matrixLastPayload = payload;
    renderMatrixLiveData(payload);
    if (shouldRefreshMatrixChart()) {
      renderMatrixChartSection(payload);
    }
    if (badge) badge.textContent = "LIVE";
  } catch (error) {
    if (badge) badge.textContent = "ERROR";
    el("matrix-signal-banner").className = "matrix-signal-banner short";
    el("matrix-signal-banner").textContent = error.message;
  } finally {
    matrixScanInFlight = false;
    setMatrixFetchLoading(false);
  }
}

function startMatrixFetch() {
  const controls = getMatrixControls();
  const configKey = matrixConfigKey(controls);

  stopMatrixFetch();

  matrixViewConfig = controls;
  matrixFetchConfigKey = configKey;
  matrixFetchActive = true;

  matrixChartLastRefresh = 0;

  syncMatrixWebSocket();
  setMatrixFetchLive(true);
  startMatrixChartRefreshTimer();

  const badge = el("matrix-fetch-badge");
  if (badge) badge.textContent = "FETCHING";

  fetchMatrixTick();
  matrixFetchTimer = setInterval(fetchMatrixTick, MATRIX_FETCH_INTERVAL_MS);
}

function connectWebSocket() {
  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return;

  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws/signals`);

  ws.onopen = () => {
    setConnectionState(true);
    el("feed-container").innerHTML =
      `<div class="feed-empty emerald">Connected. Live data routing active.</div>`;
  };

  ws.onmessage = (e) => handleFeedMessage(JSON.parse(e.data));

  ws.onclose = () => {
    setConnectionState(false);
    ws = null;
    setTimeout(connectWebSocket, 3000);
  };
}

function init() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchPage(btn.dataset.page));
  });

  el("analyzeBtn").addEventListener("click", processCosmicVerdict);
  el("audio-toggle").addEventListener("click", () => {
    audioArmed = !audioArmed;
    const btn = el("audio-toggle");
    btn.textContent = audioArmed ? "Radar Audio: ARMED" : "Radar Audio: MUTED";
    btn.classList.toggle("armed", audioArmed);
  });

  el("clearFeedBtn").addEventListener("click", () => {
    el("feed-container").innerHTML = "";
    rollingLiquidationHistory = [];
    rollingWhaleHistory = [];
    updateMomentum();
  });

  el("matrix-fetch-btn").addEventListener("click", startMatrixFetch);

  el("aspect-info-btn")?.addEventListener("click", openAspectModal);
  document.querySelectorAll("[data-close-modal]").forEach((node) => {
    node.addEventListener("click", closeAspectModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAspectModal();
  });

  connectWebSocket();
}

init();
