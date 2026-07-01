/** Dual-exchange order book — Binance Spot + Bybit Spot via /ws/orderbook */

let obWs = null;
let obActive = false;
let obSymbol = "BTCUSDT";
const obVolumeHistory = {
  "ob-binance": { bid: null, ask: null },
  "ob-bybit": { bid: null, ask: null },
};

const obEl = (id) => document.getElementById(id);

function formatPrice(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatQty(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  if (n >= 100) return n.toFixed(3);
  if (n >= 1) return n.toFixed(4);
  return n.toFixed(6);
}

function formatNotional(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function setPaneStatus(prefix, book) {
  const badge = obEl(`${prefix}-status`);
  if (!badge) return;
  const status = book?.status || "offline";
  badge.textContent = status.toUpperCase();
  badge.className = "chip";
  if (status === "live") badge.classList.add("ob-live");
  else if (status === "connecting" || status === "waiting") badge.classList.add("ob-warn");
  else badge.classList.add("ob-error");
}

function resetVolumeHistory(prefix) {
  if (obVolumeHistory[prefix]) {
    obVolumeHistory[prefix].bid = null;
    obVolumeHistory[prefix].ask = null;
  }
  ["bid", "ask"].forEach((side) => {
    const arrow = obEl(`${prefix}-${side}-vol-arrow`);
    if (arrow) {
      arrow.textContent = "—";
      arrow.className = "ob-vol-arrow flat";
    }
  });
}

function updateVolumeStat(prefix, side, rawValue) {
  const valueEl = obEl(`${prefix}-${side}-vol`);
  const arrowEl = obEl(`${prefix}-${side}-vol-arrow`);
  if (!valueEl) return;

  valueEl.textContent = formatQty(rawValue);
  const next = Number(rawValue);
  if (Number.isNaN(next) || !arrowEl) return;

  const history = obVolumeHistory[prefix] || { bid: null, ask: null };
  const prev = history[side];
  if (prev != null) {
    if (next > prev) {
      arrowEl.textContent = "▲";
      arrowEl.className = "ob-vol-arrow up";
    } else if (next < prev) {
      arrowEl.textContent = "▼";
      arrowEl.className = "ob-vol-arrow down";
    } else {
      arrowEl.textContent = "—";
      arrowEl.className = "ob-vol-arrow flat";
    }
  }
  history[side] = next;
}

function renderBookPane(prefix, book) {
  if (!book) return;
  setPaneStatus(prefix, book);

  const title = obEl(`${prefix}-title`);
  if (title) {
    title.textContent = `${book.exchange || "—"} · ${book.market || "Spot"} · ${book.symbol || obSymbol}`;
  }

  obEl(`${prefix}-best-bid`).textContent = formatPrice(book.best_bid);
  obEl(`${prefix}-best-ask`).textContent = formatPrice(book.best_ask);
  obEl(`${prefix}-mid`).textContent = formatPrice(book.mid);
  obEl(`${prefix}-spread`).textContent =
    book.spread != null ? `${formatPrice(book.spread)} (${Number(book.spread_bps || 0).toFixed(2)} bps)` : "—";
  obEl(`${prefix}-obi`).textContent =
    book.obi_pct != null ? `${book.obi_pct >= 0 ? "+" : ""}${Number(book.obi_pct).toFixed(2)}%` : "—";
  obEl(`${prefix}-obi`).className = `ob-stat-value ${book.obi_pct >= 0 ? "emerald" : "rose"}`;

  updateVolumeStat(prefix, "bid", book.bid_volume);
  updateVolumeStat(prefix, "ask", book.ask_volume);
  obEl(`${prefix}-bid-notional`).textContent = formatNotional(book.bid_notional);
  obEl(`${prefix}-ask-notional`).textContent = formatNotional(book.ask_notional);
  obEl(`${prefix}-levels`).textContent = book.levels ? `${book.levels} levels` : "—";
  obEl(`${prefix}-update-id`).textContent = book.update_id != null ? `#${book.update_id}` : "—";

  if (book.timestamp_ms) {
    obEl(`${prefix}-updated`).textContent = new Date(book.timestamp_ms).toLocaleTimeString();
  }

  if (book.status !== "live") {
    obEl(`${prefix}-asks`).innerHTML = `<div class="ob-empty">${book.status || "Waiting"}…</div>`;
    obEl(`${prefix}-bids`).innerHTML = "";
    obEl(`${prefix}-spread-row`).textContent = "—";
    return;
  }

  const asks = book.asks || [];
  const bids = book.bids || [];
  const maxQty = Math.max(
    ...asks.map((row) => row.qty || 0),
    ...bids.map((row) => row.qty || 0),
    0.000001
  );

  obEl(`${prefix}-spread-row`).innerHTML = `
    <span class="ob-spread-label">Spread</span>
    <span class="ob-spread-value">${formatPrice(book.spread)}</span>
    <span class="ob-spread-mid">Mid ${formatPrice(book.mid)}</span>
  `;

  obEl(`${prefix}-asks`).innerHTML = [...asks].reverse().map((row) => {
    const width = Math.min(100, (row.qty / maxQty) * 100);
    return `
      <div class="ob-row ob-row-ask">
        <div class="ob-depth-bar ask" style="width:${width}%"></div>
        <span class="ob-col-price rose">${formatPrice(row.price)}</span>
        <span class="ob-col-qty">${formatQty(row.qty)}</span>
        <span class="ob-col-total">${formatQty(row.cum_qty)}</span>
        <span class="ob-col-notional">${formatNotional(row.notional)}</span>
      </div>
    `;
  }).join("");

  obEl(`${prefix}-bids`).innerHTML = bids.map((row) => {
    const width = Math.min(100, (row.qty / maxQty) * 100);
    return `
      <div class="ob-row ob-row-bid">
        <div class="ob-depth-bar bid" style="width:${width}%"></div>
        <span class="ob-col-price emerald">${formatPrice(row.price)}</span>
        <span class="ob-col-qty">${formatQty(row.qty)}</span>
        <span class="ob-col-total">${formatQty(row.cum_qty)}</span>
        <span class="ob-col-notional">${formatNotional(row.notional)}</span>
      </div>
    `;
  }).join("");
}

function applyOrderbookFrame(payload) {
  if (payload.symbol) {
    obEl("ob-symbol-label").textContent = payload.symbol;
  }
  renderBookPane("ob-binance", payload.binance);
  renderBookPane("ob-bybit", payload.bybit);
}

function disconnectOrderbookWebSocket() {
  if (obWs) {
    obWs.onclose = null;
    obWs.close();
    obWs = null;
  }
  const badge = obEl("ob-connect-badge");
  badge?.classList.remove("ob-live");
  if (badge) badge.textContent = "DISCONNECTED";
}

function connectOrderbookWebSocket() {
  disconnectOrderbookWebSocket();
  resetVolumeHistory("ob-binance");
  resetVolumeHistory("ob-bybit");
  obSymbol = obEl("ob-symbol")?.value || "BTCUSDT";
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${location.host}/ws/orderbook?symbol=${encodeURIComponent(obSymbol)}`;

  obEl("ob-connect-badge").textContent = "CONNECTING";
  obWs = new WebSocket(url);

  obWs.onopen = () => {
    obEl("ob-connect-badge").textContent = "LIVE";
    obEl("ob-connect-badge").classList.add("ob-live");
  };

  obWs.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.event === "orderbook_frame" || payload.event === "orderbook_history") {
        applyOrderbookFrame(payload);
      }
    } catch {
      // ignore malformed frames
    }
  };

  obWs.onclose = () => {
    obEl("ob-connect-badge").textContent = "DISCONNECTED";
    obEl("ob-connect-badge").classList.remove("ob-live");
    obWs = null;
    if (obActive) {
      setTimeout(connectOrderbookWebSocket, 2000);
    }
  };
}

function startOrderbookPage() {
  if (obActive) return;
  obActive = true;
  connectOrderbookWebSocket();
}

function stopOrderbookPage() {
  obActive = false;
  disconnectOrderbookWebSocket();
}

function initOrderbookPage() {
  obEl("ob-connect-btn")?.addEventListener("click", () => {
    stopOrderbookPage();
    startOrderbookPage();
  });
  obEl("ob-symbol")?.addEventListener("change", () => {
    if (obActive) {
      stopOrderbookPage();
      startOrderbookPage();
    }
  });
}

initOrderbookPage();
