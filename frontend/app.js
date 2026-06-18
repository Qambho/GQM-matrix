const symbolSelect = document.getElementById("symbolSelect");
const leverageInput = document.getElementById("leverageInput");
const refreshBtn = document.getElementById("refreshBtn");
const statusBadge = document.getElementById("statusBadge");
const marketPanel = document.getElementById("marketPanel");
const astroPanel = document.getElementById("astroPanel");
const matrixPanel = document.getElementById("matrixPanel");
const windowsList = document.getElementById("windowsList");
const levelChart = document.getElementById("levelChart");

function setStatus(text, type = "idle") {
  statusBadge.textContent = text;
  statusBadge.className = `badge badge-${type}`;
}

function formatNumber(value, digits = 2) {
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function renderMarket(data) {
  const changeClass = data.market.price_change_percent >= 0 ? "positive" : "negative";
  marketPanel.classList.remove("muted");
  marketPanel.innerHTML = `
    <div class="metric-row"><span class="metric-label">Symbol</span><span class="metric-value">${data.asset}</span></div>
    <div class="metric-row"><span class="metric-label">Current Price</span><span class="metric-value">${formatNumber(data.current_price)} USDT</span></div>
    <div class="metric-row"><span class="metric-label">24h Change</span><span class="metric-value ${changeClass}">${formatNumber(data.market.price_change_percent)}%</span></div>
    <div class="metric-row"><span class="metric-label">24h High / Low</span><span class="metric-value">${formatNumber(data.market.high_price)} / ${formatNumber(data.market.low_price)}</span></div>
    <div class="metric-row"><span class="metric-label">24h Volume</span><span class="metric-value">${formatNumber(data.market.volume, 3)}</span></div>
    <div class="metric-row"><span class="metric-label">Source</span><span class="metric-value">${data.market_source}</span></div>
  `;
}

function renderAstro(data) {
  astroPanel.classList.remove("muted");
  astroPanel.innerHTML = `
    <div class="metric-row"><span class="metric-label">Active Antardasa</span><span class="metric-value">${data.active_antardasa} (${data.active_antardasa_abbrev})</span></div>
    <div class="metric-row"><span class="metric-label">Signified KP Houses</span><span class="metric-value">${data.signified_houses.join(", ") || "None"}</span></div>
    <div class="metric-row"><span class="metric-label">KP Gain Filter</span><span class="metric-value ${data.kp_signifies_gain ? "positive" : "negative"}">${data.kp_signifies_gain ? "Aligned" : "Unfavorable"}</span></div>
    <div class="metric-row"><span class="metric-label">Generated At</span><span class="metric-value">${new Date(data.generated_at).toLocaleString()}</span></div>
  `;
}

function renderMatrix(data) {
  const matrix = data.matrix;
  const biasClass = matrix.bias === "LONG" ? "bias-long" : "bias-short";
  matrixPanel.classList.remove("muted");
  matrixPanel.innerHTML = `
    <div class="level-grid">
      <div class="level-card"><strong>Date Root</strong><span>${matrix.date_root}</span></div>
      <div class="level-card"><strong>Matrix Bias</strong><span class="${biasClass}">${matrix.bias}</span></div>
      <div class="level-card"><strong>Base Band</strong><span>${formatNumber(matrix.base_band)}</span></div>
      <div class="level-card"><strong>Entry Zone</strong><span>${formatNumber(matrix.entry_zone)}</span></div>
      <div class="level-card"><strong>Standard Target</strong><span>${formatNumber(matrix.standard_target)}</span></div>
      <div class="level-card"><strong>Alpha Node (2.73)</strong><span>${formatNumber(matrix.network_node_target)}</span></div>
      <div class="level-card"><strong>Stop Loss</strong><span>${formatNumber(matrix.stop_loss)}</span></div>
    </div>
    <div class="notice ${data.kp_signifies_gain ? "success" : "warning"}">${data.notice}</div>
  `;
}

function renderWindows(data) {
  windowsList.classList.remove("muted");
  windowsList.innerHTML = "";
  if (!data.upcoming_good_windows.length) {
    windowsList.innerHTML = "<li>No future bullish phases found in dasas.txt.</li>";
    return;
  }
  data.upcoming_good_windows.forEach((window) => {
    const item = document.createElement("li");
    item.textContent = window;
    windowsList.appendChild(item);
  });
}

function drawLevelChart(data) {
  const ctx = levelChart.getContext("2d");
  const width = levelChart.width;
  const height = levelChart.height;
  const matrix = data.matrix;
  const levels = [
    { label: "Stop Loss", value: matrix.stop_loss, color: "#ef4444" },
    { label: "Entry", value: matrix.entry_zone, color: "#f59e0b" },
    { label: "Spot", value: data.current_price, color: "#5b8cff" },
    { label: "Target", value: matrix.standard_target, color: "#22c55e" },
    { label: "Alpha Node", value: matrix.network_node_target, color: "#a855f7" },
  ];

  const values = levels.map((level) => level.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = (max - min) * 0.15 || 1;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(0, 0, width, height);

  levels.forEach((level, index) => {
    const y = height - 40 - ((level.value - (min - padding)) / ((max + padding) - (min - padding))) * (height - 80);
    ctx.strokeStyle = level.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(40, y);
    ctx.lineTo(width - 20, y);
    ctx.stroke();

    ctx.fillStyle = "#e8eefc";
    ctx.font = "13px Segoe UI, sans-serif";
    ctx.fillText(`${level.label}: ${formatNumber(level.value)}`, 48, y - 8);

    ctx.fillStyle = level.color;
    ctx.beginPath();
    ctx.arc(28, y, 5, 0, Math.PI * 2);
    ctx.fill();

    if (index < levels.length - 1) {
      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(20, y + 18);
      ctx.lineTo(width - 20, y + 18);
      ctx.stroke();
    }
  });
}

async function loadSymbols() {
  try {
    const response = await fetch("/api/market/symbols?quote=USDT");
    if (!response.ok) return;
    const payload = await response.json();
    const preferred = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"];
    const symbols = [...new Set([...preferred, ...payload.symbols])].slice(0, 12);
    symbolSelect.innerHTML = symbols
      .map((symbol) => `<option value="${symbol}">${symbol}</option>`)
      .join("");
  } catch {
    // Keep default options if symbol list fails.
  }
}

async function runBlueprint() {
  const symbol = symbolSelect.value;
  const leverage = leverageInput.value;

  refreshBtn.disabled = true;
  setStatus("Loading...", "loading");

  try {
    const response = await fetch(`/api/blueprint?base_asset=${encodeURIComponent(symbol)}&leverage=${encodeURIComponent(leverage)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Blueprint request failed.");
    }

    renderMarket(payload);
    renderAstro(payload);
    renderMatrix(payload);
    renderWindows(payload);
    drawLevelChart(payload);
    setStatus("Ready", "ready");
  } catch (error) {
    setStatus("Error", "error");
    matrixPanel.classList.remove("muted");
    matrixPanel.innerHTML = `<div class="notice warning">${error.message}</div>`;
  } finally {
    refreshBtn.disabled = false;
  }
}

refreshBtn.addEventListener("click", runBlueprint);
loadSymbols();
runBlueprint();
