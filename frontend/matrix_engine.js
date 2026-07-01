/** Geo-Quantum Engine V4 dashboard — polls /api/matrix-engine/* */

const GE_POLL_MS = 800;
let gePollTimer = null;
let geActive = false;

const geEl = (id) => document.getElementById(id);

function formatCountdown(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function formatPrice(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `$${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatBtcSize(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(4)} BTC`;
}

function setGeBadge(text, tone = "muted") {
  const badge = geEl("ge-status-badge");
  if (!badge) return;
  badge.textContent = text;
  badge.className = "chip";
  if (tone === "live") badge.classList.add("geo-live");
  if (tone === "warn") badge.classList.add("geo-warn");
  if (tone === "alert") badge.classList.add("geo-alert");
}

function renderNodes(nodes, spotPrice) {
  const panel = geEl("ge-nodes-panel");
  if (!panel) return;

  if (!Array.isArray(nodes) || nodes.length === 0) {
    panel.className = "matrix-level-list muted";
    panel.textContent = "No node data yet.";
    return;
  }

  panel.className = "matrix-level-list";
  panel.innerHTML = "";

  const sorted = [...nodes].sort((a, b) => Number(b.price) - Number(a.price));
  sorted.forEach((node) => {
    const row = document.createElement("div");
    row.className = "matrix-level-row";
    const distance = Math.abs(Number(spotPrice) - Number(node.price));
    if (distance <= Math.max(Number(spotPrice) * 0.0001, 5)) {
      row.classList.add("highlight");
    }
    if (node.support_wall) row.classList.add("geo-node-support");
    if (node.resistance_wall) row.classList.add("geo-node-resistance");

    let wallTag = "";
    if (node.support_wall) {
      wallTag = `<span class="geo-wall-tag emerald">SUPPORT ${formatBtcSize(node.support_wall.volume)}</span>`;
    } else if (node.resistance_wall) {
      wallTag = `<span class="geo-wall-tag rose">RESIST ${formatBtcSize(node.resistance_wall.volume)}</span>`;
    }

    row.innerHTML = `
      <span>Node ${node.angle}° ${wallTag}</span>
      <span>${formatPrice(node.price)}</span>
    `;
    panel.appendChild(row);
  });
}

function renderTrade(trade) {
  const panel = geEl("ge-trade-panel");
  if (!panel) return;

  if (!trade || trade.status === "IDLE") {
    panel.className = "geo-trade-panel muted";
    panel.textContent = "No active trade.";
    return;
  }

  panel.className = "geo-trade-panel";
  const sideClass = trade.side === "LONG" ? "emerald" : "rose";
  panel.innerHTML = `
    <div class="geo-trade-head">
      <span class="chip ${sideClass}">${trade.side || "—"}</span>
      <span class="chip">${trade.status || "—"}</span>
    </div>
    <div class="geo-trade-grid">
      <div><span class="field-label">Entry</span><span>${formatPrice(trade.entry)} @ ${trade.entry_angle ?? "—"}°</span></div>
      <div><span class="field-label">TP1</span><span>${formatPrice(trade.tp1)}</span></div>
      <div><span class="field-label">TP2</span><span>${formatPrice(trade.tp2)}</span></div>
      <div><span class="field-label">Stop</span><span class="rose">${formatPrice(trade.sl)}</span></div>
    </div>
  `;
}

function renderSignalLog(lines) {
  const panel = geEl("ge-signal-log");
  if (!panel) return;
  if (!Array.isArray(lines) || lines.length === 0) {
    panel.className = "geo-signal-log muted";
    panel.textContent = "No liquidity-wall confluence events yet.";
    return;
  }
  panel.className = "geo-signal-log";
  panel.innerHTML = lines
    .slice(-12)
    .map((line) => `<div class="geo-signal-log-line">${line}</div>`)
    .join("");
}

function renderSignalBanner(data) {
  const banner = geEl("ge-signal-banner");
  if (!banner) return;

  if (data.quadruple_confluence) {
    const wall = data.active_liquidity_wall;
    const size = wall ? formatBtcSize(wall.volume) : "—";
    banner.className = "matrix-signal-banner trade geo-quadruple-banner";
    banner.textContent = `🔥🔥🔥🔥 QUADRUPLE CONFLUENCE — node hit + 3-6-9 + time gate + liquidity wall (${size})`;
    return;
  }

  if (data.triple_confluence) {
    banner.className = "matrix-signal-banner trade geo-triple-banner";
    banner.textContent = "🔥 TRIPLE CONFLUENCE — 3-6-9 root + node hit + time gate open";
    return;
  }

  const priceRoot = data.price_root;
  if ([3, 6, 9].includes(priceRoot)) {
    banner.className = "matrix-signal-banner long";
    banner.textContent = `⚡ Standard 3-6-9 vibration alignment (price root ${priceRoot})`;
    return;
  }

  banner.className = "matrix-signal-banner hidden";
  banner.textContent = "";
}

function applyMetrics(data) {
  if (data.status === "initializing") {
    setGeBadge(data.engine_running ? "WARMING UP" : "OFFLINE", "warn");
    geEl("ge-last-update").textContent = "Engine loop starting — first Bybit tick pending…";
    return;
  }

  setGeBadge("LIVE", "live");
  const ts = data.timestamp ? new Date(data.timestamp * 1000).toLocaleTimeString() : "—";
  geEl("ge-last-update").textContent = `Last tick ${ts} UTC`;

  geEl("ge-spot-price").textContent = formatPrice(data.spot_price);
  geEl("ge-wave-status").textContent = data.wave_status || "—";
  geEl("ge-bias").textContent = `Bias ${data.bias || "—"}`;

  geEl("ge-nakshatra").textContent = data.nakshatra || "—";

  const rootTone = [3, 6, 9].includes(data.price_root) ? "emerald" : "muted";
  geEl("ge-roots").innerHTML = `<span class="${rootTone}">[${data.price_root ?? "—"}]</span> · <span class="amber">[${data.dasha_root ?? "—"}]</span>`;
  geEl("ge-dasha-lord").textContent = `Lord ${data.dasha_lord || "—"}`;

  const countdown = Number(data.countdown) || 0;
  const gateOpen = countdown <= 15 || countdown >= 165;
  geEl("ge-countdown").textContent = formatCountdown(countdown);
  geEl("ge-countdown").className = `stat-value ${gateOpen ? "rose" : "emerald"}`;
  geEl("ge-gate-state").textContent = gateOpen ? "Time gate OPEN" : "Time gate closed";

  geEl("ge-anchor").textContent = formatPrice(data.anchor);
  geEl("ge-scale").textContent = `PPD scale ${Number(data.scale || 0).toFixed(2)}`;

  renderNodes(data.nodes, data.spot_price);
  renderTrade(data.active_trade);
  renderSignalBanner(data);
  renderSignalLog(data.signal_log);
}

async function fetchGeoMetrics() {
  try {
    const res = await fetch("/api/matrix-engine/metrics");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    applyMetrics(data);
  } catch (err) {
    setGeBadge("ERROR", "warn");
    geEl("ge-last-update").textContent = `Metrics fetch failed: ${err.message}`;
  }
}

function fillConfigForm(config) {
  if (!config) return;
  geEl("ge-anchor-price").value = config.anchor_price ?? "";
  geEl("ge-atr-window").value = config.atr_window_seconds ?? "";
  geEl("ge-flank-coef").value = config.flanking_coefficient ?? "";
  geEl("ge-min-scale").value = config.min_scale ?? "";
  geEl("ge-max-scale").value = config.max_scale ?? "";
  geEl("ge-alert-enabled").checked = Boolean(config.alert_enabled);
}

async function loadGeoConfig() {
  try {
    const res = await fetch("/api/matrix-engine/config");
    if (!res.ok) return;
    fillConfigForm(await res.json());
  } catch {
    // non-fatal
  }
}

async function submitDasa() {
  const raw = geEl("ge-dasa-input")?.value?.trim();
  if (!raw) {
    geEl("ge-config-msg").textContent = "Paste a Jagannatha Hora block first.";
    return;
  }
  geEl("ge-dasa-btn").disabled = true;
  try {
    const res = await fetch("/api/matrix-engine/update-dasa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_dasa: raw }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || body.message || `HTTP ${res.status}`);
    geEl("ge-config-msg").textContent = body.message || "Dasa synchronized.";
    geEl("ge-config-msg").className = "card-hint emerald";
    await fetchGeoMetrics();
  } catch (err) {
    geEl("ge-config-msg").textContent = err.message;
    geEl("ge-config-msg").className = "card-hint rose";
  } finally {
    geEl("ge-dasa-btn").disabled = false;
  }
}

async function submitConfig() {
  const payload = {
    anchor_price: Number(geEl("ge-anchor-price").value),
    atr_window_seconds: Number(geEl("ge-atr-window").value),
    flanking_coefficient: Number(geEl("ge-flank-coef").value),
    min_scale: Number(geEl("ge-min-scale").value),
    max_scale: Number(geEl("ge-max-scale").value),
    alert_enabled: geEl("ge-alert-enabled").checked,
  };

  geEl("ge-config-btn").disabled = true;
  try {
    const res = await fetch("/api/matrix-engine/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || body.message || `HTTP ${res.status}`);
    fillConfigForm(body.config);
    geEl("ge-config-msg").textContent = body.message || "Configuration saved.";
    geEl("ge-config-msg").className = "card-hint emerald";
  } catch (err) {
    geEl("ge-config-msg").textContent = err.message;
    geEl("ge-config-msg").className = "card-hint rose";
  } finally {
    geEl("ge-config-btn").disabled = false;
  }
}

function startGeoPolling() {
  if (gePollTimer) return;
  fetchGeoMetrics();
  gePollTimer = setInterval(fetchGeoMetrics, GE_POLL_MS);
}

function stopGeoPolling() {
  if (gePollTimer) {
    clearInterval(gePollTimer);
    gePollTimer = null;
  }
}

function startGeoEnginePage() {
  if (geActive) return;
  geActive = true;
  loadGeoConfig();
  startGeoPolling();
}

function stopGeoEnginePage() {
  geActive = false;
  stopGeoPolling();
}

function initGeoEnginePage() {
  geEl("ge-refresh-btn")?.addEventListener("click", fetchGeoMetrics);
  geEl("ge-dasa-btn")?.addEventListener("click", submitDasa);
  geEl("ge-config-btn")?.addEventListener("click", submitConfig);
}

initGeoEnginePage();
