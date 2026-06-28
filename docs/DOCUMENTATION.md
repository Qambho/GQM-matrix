# GQM Matrix — Project Documentation

**GQM Astro-Quant Matrix** is a live trading analysis platform that maps cryptocurrency price action onto a **360° sidereal zodiac grid** using Ashtottari lattice geometry, frozen swing anchors, and M–W wave structure. The backend (Python/FastAPI) computes anchors, lattice levels, and celestial confluence; the frontend (Canvas) renders the geometric matrix and reversal alerts.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [System Architecture](#system-architecture)
3. [Symbols & Constants](#symbols--constants)
4. [Market Data Formulas](#market-data-formulas)
5. [Celestial Coordinates](#celestial-coordinates)
6. [Frozen Swing Anchor](#frozen-swing-anchor)
7. [Macro Lattice (Ashtottari Grid)](#macro-lattice-ashtottari-grid)
8. [M–W Wave Geometry (Chart)](#m-w-wave-geometry-chart)
9. [Harmonic Nodes & Reversal Alerts](#harmonic-nodes--reversal-alerts)
10. [Chart Projection (Canvas)](#chart-projection-canvas)
11. [Trading Signal Logic](#trading-signal-logic)
12. [Celestial Confluence & Aspects](#celestial-confluence--aspects)
13. [Source File Reference](#source-file-reference)

---

## Quick Start

```powershell
cd GQM-matrix
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m gqm_matrix.server
```

Open **http://127.0.0.1:8000** → **GQM Matrix** page → click **Fetch**. Full formula reference: sidebar **Docs**.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `symbol` | `BTCUSDT` | Binance Futures pair |
| `price_per_degree` (ppd fallback) | `200` | Fallback when ATR unavailable |
| Dynamic PPD | ATR-driven | `(ATR₅ / 0.0458) × 0.5`, clamped 25–800 |
| Anchor recalibration | every **5m candle close** | Frozen 5m swing pivot |
| Live poll | every **1 s** | REST `/api/matrix/scan` |

---

## System Architecture

```
Binance Futures API
        │
        ▼
GodzillaProductionEngine (godzilla_engine.py)
  ├── 5m swing anchor (mw_anchor.py)
  ├── Dynamic PPD (dynamic_ppd.py)
  ├── Celestial ephemeris (ephem + Lahiri ayanamsha)
  ├── MW lattice grid
  └── Signal scanner
        │
        ▼
FastAPI /api/matrix/scan  ──►  frontend/app.js (Canvas chart)
```

**Key design rule:** The **Sun anchor price** is frozen from the last confirmed **5m fractal swing** and recalibrates on every **5m candle close**. **PPD** adapts each scan from 5-period ATR. Live price is tracked separately.

---

## Dynamic Price-Per-Degree (PPD)

Lattice sensitivity adapts to micro-volatility:

\[
\text{PPD}_{\text{dynamic}} = \frac{ATR_5}{\text{moon\_velocity\_5m}} \times \text{scaling\_factor}
\]

| Parameter | Default | Description |
|-----------|---------|-------------|
| \(ATR_5\) | 5-bar rolling | True Range average on 5m series |
| moon_velocity_5m | **0.0458** | Moon sidereal speed per 5m bar |
| scaling_factor | **0.1** | Grid sensitivity multiplier (0.1–0.2 range) |
| min_ppd / max_ppd | **25 / 350** | Clamps to prevent grid blowout |
| fallback_ppd | **200** | Used when ATR is invalid |

\[
\text{PPD} = \clamp(\text{PPD}_{\text{dynamic}},\; \text{min\_ppd},\; \text{max\_ppd})
\]

**Source:** `dynamic_ppd.calculate_dynamic_ppd`, `godzilla_engine.update_dynamic_ppd`

---

## Symbols & Constants

| Symbol | Meaning |
|--------|---------|
| \(P\) | Live spot price (5m close) |
| \(P_{\text{live}}\) | Same as \(P\) |
| \(P_{\text{swing}}\) | 5m swing high/low pivot price (Sun anchor) |
| \(\lambda_{\Moon}\) | Sidereal Moon longitude at pivot (°) |
| \(\lambda_{\Sun}\) | Sidereal Sun longitude at pivot (°) |
| \(\lambda_{\Mars}\) | Sidereal Mars longitude at pivot (°) |
| \(A\) | Static anchor (price intercept) |
| \(\text{ppd}\) | Price per degree ($/°) |
| \(\alpha\) | Lahiri ayanamsha (default **24.2°**) |
| \(\Delta_{\text{nak}}\) | Nakshatra span = **13.33°** (= 360°/27) — used for sign mapping only |

Lattice **price** band is volatility-native (not fixed \$2,666):

\[
\text{half\_band} = ATR_5 \quad\text{(or PPD fallback when ATR invalid)}
\]
\[
P_{\text{upper}} = P_{\text{primary}} + \text{half\_band}, \quad
P_{\text{lower}} = P_{\text{primary}} - \text{half\_band}
\]

Band in zodiac degrees: \(\text{band\_degrees} = ATR_5 / \text{PPD}\)

**Source:** `lattice_band.py`, `dynamic_ppd.py`

---

## Market Data Formulas

### True Range (per bar)

\[
TR_t = \max\bigl(H_t - L_t,\; |H_t - C_{t-1}|,\; |L_t - C_{t-1}|\bigr)
\]

### Average True Range (5-period, 5m)

\[
ATR_5 = \frac{1}{5}\sum_{i=1}^{5} TR_i
\]

*(Default `atr_period=5` on the 5m feed.)*

### Dynamic Wick Tolerance

Used to test proximity of price to lattice nodes:

\[
\tau =
\begin{cases}
0.5 \times ATR & \text{if ATR is valid} \\
0.0015 \times P & \text{fallback}
\end{cases}
\]

### Distance to Lattice Levels

\[
d_{\text{primary}} = |P - P_{\text{primary}}|
\]
\[
d_{\text{upper}} = |P - P_{\text{upper}}|
\]

---

## Celestial Coordinates

### Sidereal Longitude

For any body (Moon, Sun, Mars, Mercury) at UTC time \(t\):

\[
\lambda_{\text{sidereal}} = \bigl(\lambda_{\text{tropical}}(t) - \alpha\bigr) \bmod 360
\]

where \(\lambda_{\text{tropical}}\) is the ecliptic longitude from PyEphem.

**Source:** `mw_anchor.sidereal_longitude`, `godzilla_engine.calculate_celestial_coordinates`

### Zodiac Sign & Sign Degree

\[
\text{sign index} = \left\lfloor \frac{\lambda \mod 360}{30} \right\rfloor \mod 12
\]
\[
\lambda_{\text{in sign}} = (\lambda \mod 360) \mod 30
\]

### Angular Separation (Short Arc)

\[
\delta(a, b) = \min\bigl(|a - b| \mod 360,\; 360 - |a - b| \mod 360\bigr)
\]

### High-Volume Moon–Mars Window

Active when separation is within **3°** of **0°, 90°, or 180°**:

\[
\exists\, \theta \in \{0, 90, 180\}:\; \min\bigl(|\delta_{\Moon\Mars} - \theta|,\; |360 - \delta_{\Moon\Mars} - \theta|\bigr) < 3°
\]

---

## Frozen Swing Anchor

### Fractal Swing Detection (5m)

A bar at index \(i\) is a **swing high** if:

\[
H_i > H_{i-j}\;\forall j \in [1, L], \quad H_i \geq H_{i+j}\;\forall j \in [1, R]
\]

A **swing low** if:

\[
L_i < L_{i-j}\;\forall j \in [1, L], \quad L_i \leq L_{i+j}\;\forall j \in [1, R]
\]

Defaults: \(L = R = 2\) (`SWING_LEFT_BARS`, `SWING_RIGHT_BARS`).

The **last formed swing** (highest bar index) becomes the pivot.

### Sun Anchor Price

\[
P_{\text{swing}} = P_{\text{swing high}} \text{ or } P_{\text{swing low}}
\]
\[
P_{\Sun} = P_{\text{anchor}} = P_{\text{swing}}
\]

**Constraint:** \(P_{\Sun} \neq P_{\text{live}}\) (validated at runtime).

Ephemeris at pivot time \(t_p\):

\[
\lambda_{\Moon} = \lambda_{\Moon}(t_p), \quad
\lambda_{\Sun} = \lambda_{\Sun}(t_p), \quad
\lambda_{\Mars} = \lambda_{\Mars}(t_p)
\]

---

## Macro Lattice (Ashtottari Grid)

All lattice prices are computed at **calibration** from the frozen pivot and **do not** update with live spot.

### Static Anchor

\[
A = P_{\text{swing}} - \lambda_{\Moon} \times \text{ppd}
\]

### Primary Vector Support

\[
P_{\text{primary}} = A + \lambda_{\Moon} \times \text{ppd}
\]

*(Equivalently \(P_{\text{primary}} = P_{\text{swing}}\) when Moon degree at pivot is used consistently.)*

### Upper & Lower Lattice Nodes

\[
P_{\text{upper}} = P_{\text{primary}} + \text{half\_band}
\]
\[
P_{\text{lower}} = P_{\text{primary}} - \text{half\_band}
\]

where \(\text{half\_band} = ATR_5\) derived from dynamic PPD context (see `lattice_band.py`).

### Exit Upper Node (MW vertex C)

\[
\Delta_{\text{exp}} = P_{\text{upper}} - P_{\text{primary}}
\]
\[
P_{\text{exit upper}} = P_{\text{upper}} + 0.95 \times \Delta_{\text{exp}}
\]

### Live Grid Recalculation (Moon-driven)

During each scan, the **display grid** also updates with **live** Moon longitude \(\lambda_{\Moon}^{\text{live}}\):

\[
P_{\text{primary}}^{\text{live}} = A + \lambda_{\Moon}^{\text{live}} \times \text{ppd}
\]

Frozen anchor block retains pivot-time values for MW vertices; `grid` in API response uses live Moon for distance metrics.

**Source:** `mw_anchor.build_frozen_swing_anchor`, `godzilla_engine.calculate_mw_vector_grid`

---

## M–W Wave Geometry (Chart)

Chart vertices are built in `frontend/app.js` → `buildMwWaveGeometry()`.

### Band Width

\[
B = \frac{P_{\text{upper}} - P_{\text{lower}}}{4}
\]

### Leg Stub (vertical extension beyond curve anchor)

\[
S = 0.58 \times B
\]

### Entry / Exit Degrees

\[
\theta_{\text{entry}} = \lambda_{\Moon}(t_p), \quad
\theta_{\text{exit}} = \lambda_{\Sun}(t_p)
\]

### Center Degree (short-arc midpoint)

\[
\Delta\theta = \bigl((\theta_{\text{exit}} - \theta_{\text{entry}} + 540) \mod 360\bigr) - 180
\]
\[
\theta_{\text{center}} = (\theta_{\text{entry}} + 0.5 \times \Delta\theta + 360) \mod 360
\]

### Curve Anchors (on vertical legs)

| Point | Degree | Price |
|-------|--------|-------|
| M3 (exit peak anchor) | \(\theta_{\text{exit}}\) | \(P_{\text{exit upper}}\) |
| M1 (entry peak anchor) | \(\theta_{\text{entry}}\) | \(P_{\text{upper}}\) |
| W3 (exit trough anchor) | \(\theta_{\text{exit}}\) | \(P_{\text{lower}}\) |
| W1 (entry trough anchor) | \(\theta_{\text{entry}}\) | \(P_{\text{lower}}\) |

### Stub Starts (line endpoints beyond curve)

| Point | Degree | Price | Rule |
|-------|--------|-------|------|
| C | \(\theta_{\text{exit}}\) | \(P_{\text{exit upper}} - S\) | below peak |
| A | \(\theta_{\text{entry}}\) | \(P_{\text{upper}} - S\) | below peak |
| D | \(\theta_{\text{exit}}\) | \(P_{\text{lower}} + S\) | above trough |
| B | \(\theta_{\text{entry}}\) | \(P_{\text{lower}} + S\) | above trough |

### Center Diamond (Sun crossing)

\[
P_{\diamond} = P_{\Sun}, \quad \theta_{\diamond} = \lambda_{\Sun}(t_p)
\]
\[
M2 = W2 \text{ at } (\theta_{\text{center}},\; P_{\Sun})
\]

### M Path (upper wave, purple)

Ordered by increasing X (exit → entry when exit is left):

\[
C \to M3 \to M2 \to M1 \to A
\]

Forms an **M** with peaks at M3/M1 and valley at M2.

### W Path (lower wave, green)

\[
D \to W3 \to W2 \to W1 \to B
\]

Forms a **W** with troughs at W3/W1 and peak at W2.

---

## Harmonic Nodes & Reversal Alerts

Harmonic levels subdivide the **dynamic band** between Primary Vector and lattice extremes (33% / 66%), computed from live PPD + ATR — no fixed price spacing.

### Upper Harmonics (33% & 66%)

Given \(\text{half\_band} = dynamicLatticeHalfBand(\text{PPD}, ATR_5)\):

\[
H_{\uparrow,1} = P_{\text{primary}} + \frac{\text{half\_band}}{3}
\]
\[
H_{\uparrow,2} = P_{\text{primary}} + \frac{2 \cdot \text{half\_band}}{3}
\]

### Lower Harmonics (33% & 66%)

\[
H_{\downarrow,1} = P_{\text{primary}} - \frac{\text{half\_band}}{3}
\]
\[
H_{\downarrow,2} = P_{\text{primary}} - \frac{2 \cdot \text{half\_band}}{3}
\]

**Source:** `buildHarmonicNodes()` in `frontend/app.js`

### Reversal Alert (Red Spot)

Let \(\mathcal{H} = \{H_{\uparrow,1}, H_{\uparrow,2}, H_{\downarrow,1}, H_{\downarrow,2}\}\).

\[
\text{Reversal active} \iff \exists\, h \in \mathcal{H}:\; |P - h| \leq 5
\]

Spot marker color: **red** (`#ef4444`) if active, else **cyan** (`#22d3ee`).

### Cardinal Window Alert (Gold Grid)

Live spot X-degree:

\[
\theta_{\text{spot}} = P \mod 360
\]

Cardinal set: \(\mathcal{C} = \{0°, 90°, 180°, 270°\}\).

\[
\text{Cardinal active} \iff \exists\, c \in \mathcal{C}:\; \delta(\theta_{\text{spot}}, c) \leq 2°
\]

When active, the matching vertical grid line is highlighted **gold**.

---

## Chart Projection (Canvas)

### X-Axis Mappings

**Live Spot (cyan/red dot)** — raw modulo only:

\[
\theta_{\text{spot}} = (P \mod 360 + 360) \mod 360
\]

**Example:** \(P = \$59{,}926.10 \Rightarrow \theta_{\text{spot}} = 166.1°\)

**Planets & lattice vertices** — ephemeris / pivot degrees:

\[
\theta_{\Moon} = \lambda_{\Moon}^{\text{live}}, \quad
\theta_{\Mars} = \lambda_{\Mars}^{\text{live}}
\]

**Lattice price → degree** (for planet Y reference, not spot X):

\[
\theta_{\text{lattice}}(p) = \left(\frac{p - A}{\text{ppd}} + 360\right) \mod 360
\]

**Inverse (degree → price):**

\[
p(\theta) = A + \theta \times \text{ppd}
\]

### Pixel Coordinates

Given plot padding and dimensions:

\[
x(\theta) = \text{pad}_L + \frac{\theta}{360} \times W_{\text{plot}}
\]

\[
y(p) = \text{pad}_T + H_{\text{plot}} - \frac{p - p_{\min}}{p_{\max} - p_{\min}} \times H_{\text{plot}}
\]

where \(p_{\min}, p_{\max}\) include wave vertices, harmonic nodes, and live price ± tolerance.

---

## Trading Signal Logic

Signals require **high-volume Moon–Mars aspect window** and no open trade.

### LONG Confluence (Primary Vector)

Condition:

\[
d_{\text{primary}} < \tau
\]

Stop loss & take profit:

\[
SL = P - ATR, \quad TP = P + 2 \times ATR
\]

Position size:

\[
Q = \frac{R \times B_{\text{account}}}{|P - SL|}
\]

where \(R = 0.02\) (2% risk).

Liquidation (LONG):

\[
P_{\text{liq}} = P \times \left(1 - \frac{1}{L} + m\right)
\]

Effective stop: \(\max(SL, P_{\text{liq}})\) where \(L\) = leverage, \(m\) = maintenance margin rate (0.005).

### SHORT Confluence (Upper Lattice)

Condition:

\[
d_{\text{upper}} < \tau
\]

\[
SL = P + ATR, \quad TP = P - 2 \times ATR
\]

\[
P_{\text{liq}} = P \times \left(1 + \frac{1}{L} - m\right)
\]

Effective stop: \(\min(SL, P_{\text{liq}})\).

### PnL on Close

LONG:

\[
\text{PnL} = Q \times (P_{\text{exit}} - P_{\text{entry}})
\]

SHORT:

\[
\text{PnL} = Q \times (P_{\text{entry}} - P_{\text{exit}})
\]

---

## Celestial Confluence & Aspects

### Three-Body Longitude Sum

\[
\Sigma = \lambda_{\Moon} + \lambda_{\Mercury} + \lambda_{\Mars}
\]
\[
\Lambda_{\text{composite}} = \Sigma \mod 360
\]

### Pairwise Aspect Match

For planets \(a, b\) with separation \(\delta(a,b)\), an aspect with target angle \(\phi\) and orb \(\omega\) matches if:

\[
|\delta(a,b) - \phi| \leq \omega
\]

Standard aspects: Conjunction (0°, orb 8°), Sextile (60°, 6°), Square (90°, 8°), Trine (120°, 8°), Opposition (180°, 8°), etc.

### Composite Aspect

\[
\delta_{\text{comp}} = \min(\Lambda_{\text{composite}},\; 360 - \Lambda_{\text{composite}})
\]

Test \(\delta_{\text{comp}}\) against aspect orbs.

### Cardinal Harmonic (Composite)

\[
\exists\, c \in \{0, 90, 180, 270\}:\; \min(|\Lambda - c|, 360 - |\Lambda - c|) \leq 3°
\]

**Source:** `celestial_aspects.analyze_confluence`

---

## Source File Reference

| File | Responsibility |
|------|----------------|
| `src/gqm_matrix/godzilla_engine.py` | Main scanner, ATR, signals, grid API |
| `src/gqm_matrix/mw_anchor.py` | 5m swing pivot, frozen anchor, MW vertices |
| `src/gqm_matrix/celestial_aspects.py` | Confluence, aspects, cardinal harmonics |
| `src/gqm_matrix/coordinates.py` | Generic (θ, price) coordinate generator |
| `src/gqm_matrix/api.py` | REST endpoints |
| `frontend/app.js` | Chart rendering, harmonics, reversal UI |
| `frontend/index.html` | GQM Matrix page layout |

---

## API Response Shape (Key Fields)

```json
{
  "market": { "live_price", "atr", "atr_tolerance" },
  "anchor": { "sun_anchor_price", "swing_anchor_price", "primary_vector_support", "upper_lattice_node", "lower_lattice_node" },
  "mw_structure": { "vertices": { "A", "B", "C", "D", "sun_crossing" }, "entry_degree", "exit_degree" },
  "grid": { "primary_vector_support", "upper_lattice_node", "lower_lattice_node", "price_per_degree" },
  "celestial": { "moon_degree", "mars_degree", "mercury_degree", "confluence" },
  "distances": { "to_primary", "to_upper" },
  "signal": { "status", "message" }
}
```

---

## Reversal Radar Workflow

1. **Red spot** → live price within ±$5 of a harmonic node (exhaustion zone).
2. **Gold vertical** → spot degree within ±2° of a cardinal (0°, 90°, 180°, 270°).
3. **Confluence** → both active = highest-probability scalp window back toward \(P_{\text{primary}}\).

---

*Last updated to match codebase: GQM Matrix v1.0.0 (`app.js?v=21`).*
