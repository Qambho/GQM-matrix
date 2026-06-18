let project2Started = false;
let ws = null;

const metrics = { totalLiqVolume: 0, longsLiquidated: 0, shortsLiquidated: 0, whaleVolume: 0 };
let rollingLiquidationHistory = [];
let rollingWhaleHistory = [];
const CASCADE_THRESHOLD = 300000;
let lastAlarmTime = 0;
let audioArmed = false;

function p2El(id) {
  return document.getElementById(id);
}

function updateMacroStatsUI() {
  p2El("stat-total-liq").textContent = `$${metrics.totalLiqVolume.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  p2El("stat-longs-wiped").textContent = `$${Math.round(metrics.longsLiquidated).toLocaleString()}`;
  p2El("stat-shorts-wiped").textContent = `$${Math.round(metrics.shortsLiquidated).toLocaleString()}`;
  p2El("stat-whale-vol").textContent = `$${metrics.whaleVolume.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const total = metrics.longsLiquidated + metrics.shortsLiquidated;
  if (total <= 0) return;

  const longPercent = (metrics.longsLiquidated / total) * 100;
  const shortPercent = (metrics.shortsLiquidated / total) * 100;
  p2El("bar-longs").style.width = `${longPercent}%`;
  p2El("bar-shorts").style.width = `${shortPercent}%`;

  const ratioText = p2El("stat-ratio-text");
  if (Math.abs(longPercent - shortPercent) < 10) {
    ratioText.textContent = "NEUTRAL MIX";
    ratioText.className = "p2-value p2-muted";
  } else if (longPercent > shortPercent) {
    ratioText.textContent = "LONGS BLEEDING";
    ratioText.className = "p2-value p2-rose";
  } else {
    ratioText.textContent = "SHORTS SQUEEZING";
    ratioText.className = "p2-value p2-emerald";
  }
}

function playGodzillaRoar() {
  if (!audioArmed) return;
  const now = Date.now();
  if (now - lastAlarmTime < 6000) return;
  lastAlarmTime = now;
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc1 = audioCtx.createOscillator();
    const gain1 = audioCtx.createGain();
    osc1.type = "sawtooth";
    osc1.frequency.setValueAtTime(90, audioCtx.currentTime);
    osc1.frequency.exponentialRampToValueAtTime(350, audioCtx.currentTime + 0.4);
    gain1.gain.setValueAtTime(0.2, audioCtx.currentTime);
    gain1.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.5);
    osc1.connect(gain1);
    gain1.connect(audioCtx.destination);
    osc1.start();
    osc1.stop(audioCtx.currentTime + 0.5);
  } catch (error) {
    console.error(error);
  }
}

function calculateGodzillaPredictorEngine() {
  const now = Date.now();
  rollingLiquidationHistory = rollingLiquidationHistory.filter((item) => now - item.timestamp <= 60000);
  rollingWhaleHistory = rollingWhaleHistory.filter((item) => now - item.timestamp <= 60000);
  const liqSum = rollingLiquidationHistory.reduce((sum, item) => sum + item.amount, 0);
  const whaleSum = rollingWhaleHistory.reduce((sum, item) => sum + item.amount, 0);

  const whaleScore = Math.min((whaleSum / 12000000) * 50, 50);
  const liqScore = Math.min((liqSum / 400000) * 50, 50);
  const totalMomentumScore = Math.round(whaleScore + liqScore);

  p2El("stat-gauge-score").textContent = `${totalMomentumScore}%`;
  p2El("bar-gauge").style.width = `${totalMomentumScore}%`;

  const cascadeBanner = p2El("godzilla-cascade-banner");
  const gaugeScoreBadge = p2El("gauge-score-badge");

  if (totalMomentumScore >= 85) {
    gaugeScoreBadge.textContent = "CRITICAL METRIC OVERFLOW";
    cascadeBanner.className = "p2-banner cascade-active";
    p2El("cascade-alert-content").innerHTML = `
      <h3 class="p2-rose" style="font-weight:800;">GODZILLA BREAKOUT CASCADE DETECTED</h3>
      <p class="p2-muted">Orderbook Vacuum Breaking! Momentum: <strong class="p2-rose">${totalMomentumScore}%</strong></p>`;
    playGodzillaRoar();
  } else if (totalMomentumScore >= 45) {
    gaugeScoreBadge.textContent = "VOLATILITY BUILDING";
    cascadeBanner.className = "p2-banner";
    const percentage = Math.min((liqSum / CASCADE_THRESHOLD) * 100, 100);
    p2El("cascade-alert-content").innerHTML = `
      <div class="p2-muted" style="font-size:0.75rem;font-family:monospace;">
        Cascade Pressure: <span class="p2-amber">${Math.round(liqSum).toLocaleString()}</span> / ${CASCADE_THRESHOLD.toLocaleString()}
        <div class="p2-bar" style="margin-top:8px;"><div class="p2-bar-long" style="width:${percentage}%"></div></div>
      </div>`;
  } else {
    gaugeScoreBadge.textContent = "STABLE COMPRESSION";
    cascadeBanner.className = "p2-banner hidden";
  }
}

function processCosmicVerdict() {
  const dasaText = p2El("astro-dasa-input").value;
  const kpText = p2El("astro-kp-input").value;
  const displayPanel = p2El("verdict-display-panel");

  if (!dasaText && !kpText) {
    alert("Please paste Jagannatha Hora or KP data first.");
    return;
  }

  const astroMap = {
    merc: { name: "Mercury (Budha)", weight: 10, log: "High-velocity network asset exchange active" },
    ju: { name: "Jupiter (Guru)", weight: 15, log: "Major systemic expansion window" },
    ra: { name: "Rahu", weight: 15, log: "Speculative price dilation potential" },
    ve: { name: "Venus (Shukra)", weight: 8, log: "Favorable accumulation inflows" },
    su: { name: "Sun (Surya)", weight: 5, log: "Macro trend baseline confirmation" },
    sat: { name: "Saturn (Shani)", weight: -12, log: "Structural contraction/resistance" },
    ma: { name: "Mars (Mangal)", weight: -10, log: "Aggressive liquidations and volatility" },
    ke: { name: "Ketu", weight: -15, log: "Sudden flash-crash indicators" },
  };

  let cosmicScore = 50;
  const narrativeFound = [];
  const cleanDasa = dasaText.toLowerCase();
  const cleanKp = kpText.toLowerCase();

  Object.keys(astroMap).forEach((key) => {
    const regex = new RegExp(`\\b${key}`, "g");
    if (regex.test(cleanDasa)) {
      const data = astroMap[key];
      cosmicScore += data.weight;
      narrativeFound.push(`Dasa Node [${data.name}]: ${data.log}`);
    }
  });

  let houseGains = 0;
  let houseLosses = 0;
  if (cleanKp.includes("11th") || cleanKp.includes("11 ")) houseGains += 2;
  if (cleanKp.includes("2nd") || cleanKp.includes("2 ")) houseGains += 2;
  if (cleanKp.includes("6th") || cleanKp.includes("6 ")) houseGains += 1;
  if (cleanKp.includes("10th") || cleanKp.includes("10 ")) houseGains += 1;
  if (cleanKp.includes("12th") || cleanKp.includes("12 ")) houseLosses += 3;
  if (cleanKp.includes("8th") || cleanKp.includes("8 ")) houseLosses += 3;
  if (cleanKp.includes("5th") || cleanKp.includes("5 ")) houseLosses += 1;

  if (houseGains > houseLosses) {
    cosmicScore += 12;
    narrativeFound.push("KP Matrix: formations lean toward accumulation vectors");
  } else if (houseLosses > houseGains) {
    cosmicScore -= 15;
    narrativeFound.push("KP Matrix: alert for sudden clearing events or drops");
  }

  const currentQuantScore = parseInt(p2El("stat-gauge-score").textContent, 10) || 0;
  const finalConfluenceScore = Math.min(Math.max(Math.round((cosmicScore + currentQuantScore) / 2), 0), 100);

  displayPanel.classList.add("verdict-glow");

  const vBadge = p2El("verdict-badge");
  const vBias = p2El("v-bias-state");
  const vNarrative = p2El("verdict-narrative-text");

  p2El("v-quant-state").textContent = currentQuantScore > 75 ? "High Velocity Inflow" : currentQuantScore > 40 ? "Moderate Setup" : "Compressed Inflow";
  p2El("v-astro-state").textContent = cosmicScore > 65 ? "Auspicious Horizon" : cosmicScore < 40 ? "High Risk Alignment" : "Stable Alignment";

  if (finalConfluenceScore >= 65) {
    vBadge.textContent = "GODZILLA SUPREME EXPANSION";
    vBias.textContent = "STRONG ACCUMULATION PUMP";
    vBias.className = "p2-value p2-emerald";
    vNarrative.textContent = `[CONFLUENCE CONFIRMED] ${narrativeFound.join(". ")}. High probability of upward trend confirmation.`;
  } else if (finalConfluenceScore <= 40) {
    vBadge.textContent = "GODZILLA CASCADE IMMINENT";
    vBias.textContent = "HIGH VOLATILITY DEVIATION DUMP";
    vBias.className = "p2-value p2-rose";
    vNarrative.textContent = `[ORDERBOOK RISK] ${narrativeFound.join(". ")}. Secure spot positions or trailing stop loss measures.`;
  } else {
    vBadge.textContent = "COMPRESSION HOLD";
    vBias.textContent = "SIDEWAYS LIQUIDITY CHOP";
    vBias.className = "p2-value p2-amber";
    vNarrative.textContent = `[BALANCED CONFLUENCE] ${narrativeFound.length ? narrativeFound.join(". ") : "Cosmic indicators match order book baseline"}. Expect localized range chop.`;
  }
}

function toggleAudioPermission() {
  audioArmed = !audioArmed;
  const audioBtn = p2El("audio-toggle");
  if (audioArmed) {
    audioBtn.textContent = "Radar Audio: ARMED";
    audioBtn.className = "p2-btn-secondary p2-emerald";
  } else {
    audioBtn.textContent = "Radar Audio: MUTED";
    audioBtn.className = "p2-btn-secondary";
  }
}

function clearDisplayFeed() {
  p2El("feed-container").innerHTML = "";
  rollingLiquidationHistory = [];
  rollingWhaleHistory = [];
  calculateGodzillaPredictorEngine();
}

function handleFeedMessage(data) {
  const feed = p2El("feed-container");
  if (feed.querySelector(".p2-feed-empty")) feed.innerHTML = "";

  const card = document.createElement("div");
  card.className = "p2-feed-item";

  if (data.source === "binance_futures") {
    card.style.background = "rgba(76, 5, 25, 0.2)";
    card.style.borderColor = "rgba(244, 63, 94, 0.4)";
    metrics.totalLiqVolume += data.usd_value;
    if (data.side === "SELL") metrics.longsLiquidated += data.usd_value;
    else metrics.shortsLiquidated += data.usd_value;
    rollingLiquidationHistory.push({ timestamp: Date.now(), amount: data.usd_value });

    card.innerHTML = `
      <div><span class="p2-badge p2-rose">LIQUIDATION</span> <strong>${data.symbol}</strong></div>
      <div style="font-family:monospace;text-align:right;">
        <div class="p2-muted" style="font-size:0.7rem;">SIDE</div>
        <div class="${data.side === "BUY" ? "p2-emerald" : "p2-rose"}">${data.side === "BUY" ? "SHORT WIPE" : "LONG WIPE"}</div>
        <div class="p2-muted" style="font-size:0.7rem;margin-top:6px;">VALUE</div>
        <div class="p2-rose">$${Number(data.usd_value).toLocaleString()}</div>
      </div>`;
  } else {
    card.style.background = "rgba(8, 51, 68, 0.1)";
    card.style.borderColor = "rgba(34, 211, 238, 0.4)";
    metrics.whaleVolume += data.usd_value;
    rollingWhaleHistory.push({ timestamp: Date.now(), amount: data.usd_value });

    card.innerHTML = `
      <div><span class="p2-badge p2-cyan">WHALE FLOW</span> <strong>${data.from}</strong><div class="p2-muted" style="font-size:0.75rem;">${data.to}</div></div>
      <div style="font-family:monospace;text-align:right;">
        <div class="p2-muted" style="font-size:0.7rem;">ASSET</div>
        <div class="p2-cyan">${data.token}</div>
        <div class="p2-muted" style="font-size:0.7rem;margin-top:6px;">VOLUME</div>
        <div>$${Number(data.usd_value).toLocaleString()}</div>
      </div>`;
  }

  feed.insertBefore(card, feed.firstChild);
  if (feed.children.length > 30) feed.removeChild(feed.lastChild);

  updateMacroStatsUI();
  calculateGodzillaPredictorEngine();
}

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${window.location.host}/ws/signals`);

  ws.onopen = () => {
    p2El("status-indicator").className = "p2-status-dot pulse-light";
    p2El("status-indicator").style.background = "#10b981";
    p2El("engine-status-text").textContent = "ONLINE";
    p2El("engine-status-text").className = "p2-emerald";
    p2El("feed-container").innerHTML = `<div class="p2-feed-empty p2-emerald">System connected. Live data routing active.</div>`;
  };

  ws.onmessage = (event) => {
    handleFeedMessage(JSON.parse(event.data));
  };

  ws.onclose = () => {
    p2El("status-indicator").style.background = "#ef4444";
    p2El("engine-status-text").textContent = "OFFLINE";
    p2El("engine-status-text").className = "p2-rose";
    ws = null;
  };
}

window.initProject2 = function initProject2() {
  if (project2Started) {
    connectWebSocket();
    return;
  }
  project2Started = true;

  p2El("analyzeBtn").addEventListener("click", processCosmicVerdict);
  p2El("audio-toggle").addEventListener("click", toggleAudioPermission);
  p2El("clearFeedBtn").addEventListener("click", clearDisplayFeed);

  connectWebSocket();
};
