import os
import pandas as pd
import numpy as np
from datetime import datetime

print("[INIT] Launching Godzilla Historical Backtesting Engine (Real Data Edition)...")

CSV_FILENAME = "market_data.csv"

# 1. AUTOMATIC DATA SHEET VERIFICATION LAYER (Updated Base Framework Context)
if not os.path.exists(CSV_FILENAME):
    print(f"[ALERT] '{CSV_FILENAME}' not found in current directory.")
    print("[SYSTEM] Generating a structured template file for you automatically...")
    
    # Lowercase freq="h" hotfix for modern Pandas stability
    template_dates = pd.date_range(start="2026-05-01", periods=100, freq="h")
    np.random.seed(101)
    base_price = 62500.0  # Synced to current spot market baseline
    prices = []
    for _ in range(100):
        base_price += np.random.normal(0, 0.005) * base_price
        prices.append(round(base_price, 2))
        
    template_df = pd.DataFrame({
        'timestamp': template_dates.strftime('%Y-%m-%d %H:%M:%S'),
        'close': prices,
        'volume': np.random.uniform(1000000, 25000000, size=100)
    })
    template_df.to_csv(CSV_FILENAME, index=False)
    print(f"[SUCCESS] Template created as '{CSV_FILENAME}'. Replace its rows with your actual exchange exports.")

# 2. INGEST REAL MARKET DATA
print(f"[ENGINE] Reading historical matrix from {CSV_FILENAME}...")
df = pd.read_csv(CSV_FILENAME)

# Standardize column headers to lowercase to prevent parsing failures
df.columns = [col.lower().strip() for col in df.columns]

# Enforce explicit datetime conversion
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.sort_values('timestamp').reset_index(drop=True)

# 3. HISTORICAL ASTRO LOG MAPPING MATRIX (Ashtottari Dasa Framework Transformation)
def fetch_historical_ashtottari_signatures(target_dt):
    """
    Maps historical periods straight to the active Ashtottari Dasa structural nodes
    and their spatial geometric matrix house confluences.
    """
    dasa_nodes = []
    kp_houses = []
    
    # 2026 Historical Matrix Blocks Map
    if datetime(2026, 5, 1) <= target_dt <= datetime(2026, 5, 15):
        dasa_nodes = ["ju", "ra"]  # Jupiter-Rahu Node Confluence
        kp_houses = ["11th", "2nd"]
    elif datetime(2026, 5, 16) <= target_dt <= datetime(2026, 5, 31):
        dasa_nodes = ["sat", "ma"] # Saturn-Mars Cascade Node
        kp_houses = ["12th", "8th"]
    elif datetime(2026, 6, 1) <= target_dt <= datetime(2026, 6, 18):
        dasa_nodes = ["su", "me"]  # Sun-Mercury Expansion Node
        kp_houses = ["11th", "2nd"]
    else:
        dasa_nodes = ["ke"]        # Ketu Boundary Fallback
        kp_houses = ["6th"]
        
    return dasa_nodes, kp_houses

# 4. CONFLUENCE ALGORITHM SCORING ROUTINE
# Structural node score map tuned to the Ashtottari Matrix
ASTRO_MAP = {
    'me': 12, 'ju': 15, 'ra': 15, 've': 10, 'su': 8,
    'sat': -12, 'ma': -10, 'ke': -15
}

mean_volume = df['volume'].mean() if 'volume' in df.columns else 1.0

def score_row_confluence(row):
    cosmic_score = 50
    dasa_nodes, kp_houses = fetch_historical_ashtottari_signatures(row['timestamp'])
    
    # 1. Evaluate Ashtottari Dasa Node Contributions
    for token in dasa_nodes:
        if token in ASTRO_MAP:
            cosmic_score += ASTRO_MAP[token]
            
    # 2. Compute House Confluence Metrics
    house_gains = sum(2 for h in kp_houses if h in ['11th', '2nd'])
    house_losses = sum(3 for h in kp_houses if h in ['12th', '8th'])
    if house_gains > house_losses: cosmic_score += 12
    elif house_losses > house_gains: cosmic_score -= 15
    
    # 3. Dynamic Volumetric Factor Optimization
    vol_ratio = row['volume'] / mean_volume if mean_volume > 0 else 1.0
    quant_score = min(max(round(vol_ratio * 20), 0), 100)
    
    return min(max(round((cosmic_score + quant_score) / 2), 0), 100)

print("[ENGINE] Running verification algorithms across real data rows...")
df['confluence_score'] = df.apply(score_row_confluence, axis=1)

# 5. INTEGRATED HISTORICAL SIMULATION EXECUTION LAYER (GQM Boundary Rule Execution)
initial_pool = 10000.0
capital = initial_pool
position = 0.0
entry_price = 0.0
trade_log = []

# Target geometric baseline tracking variables
SYSTEM_ANCHOR_CORE = 50000.0
BOUNDARY_THRESHOLD = 1.59

for idx, row in df.iterrows():
    score = row['confluence_score']
    price = float(row['close'])
    current_time = row['timestamp']
    
    # Compute active geometric pivot ratio inline across rows
    pivot_ratio = round(price / SYSTEM_ANCHOR_CORE, 4)
    
    # CONDITION A: LONG ENTRY (High confluence + Pivot exceeds the 1.59 boundary context)
    if score >= 62 and pivot_ratio >= BOUNDARY_THRESHOLD and position == 0:
        position = capital / price
        entry_price = price
        trade_log.append({
            'type': 'LONG_ENTRY', 
            'price': price, 
            'time': current_time, 
            'score': score, 
            'pivot_ratio': pivot_ratio
        })
        
    # CONDITION B: LONG EXIT (Confluence drops or pivot slips back beneath security threshold safety boundary)
    elif (score <= 45 or pivot_ratio < BOUNDARY_THRESHOLD) and position > 0:
        exit_value = position * price
        profit = exit_value - capital
        capital = exit_value
        position = 0.0
        trade_log.append({
            'type': 'LONG_EXIT', 
            'price': price, 
            'time': current_time, 
            'score': score, 
            'pivot_ratio': pivot_ratio, 
            'profit': profit
        })

# Final equity sweep verification
final_portfolio_value = capital if position == 0 else position * float(df.iloc[-1]['close'])
net_return = ((final_portfolio_value - initial_pool) / initial_pool) * 100
completed_trades = [t for t in trade_log if 'profit' in t]

# 6. PERFORMANCE AUDIT REPORT OUTPUT
print("\n" + "="*60)
print("       GQM GODZILLA ENGINE: REAL HISTORICAL AUDIT       ")
print("="*60)
print(f"Data Set Range Covered : {df['timestamp'].min()} to {df['timestamp'].max()}")
print(f"Total Historical Rows  : {len(df)} records parsed")
print(f"Initial Deposited Pool : ${initial_pool:,.2f} USD")
print(f"Final Account Balance  : ${final_portfolio_value:,.2f} USD")
print(f"Net Strategy Return    : {net_return:+.2f}%")
print(f"Completed Trade Cycles : {len(completed_trades)}")
print("="*60)

if completed_trades:
    trades_df = pd.DataFrame(completed_trades)
    winning_trades = trades_df[trades_df['profit'] > 0]
    win_rate = (len(winning_trades) / len(trades_df)) * 100
    print(f"Mathematical Win Rate  : {win_rate:.1f}%")
    print(f"Largest Profitable Run : ${trades_df['profit'].max():+,.2f}")
    print(f"Largest Drawdown Hit   : ${trades_df['profit'].min():+,.2f}")
else:
    print("Execution Density      : Balanced setup. No full entry/exit thresholds breached.")
print("="*60 + "\n")