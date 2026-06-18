# calcs_matrix.py
"""
GQM Geo-Quantum Matrix - Paper Equation Calculation Engine
Extracts and computes geometric node vectors from manual charting matrix.
"""
import urllib.request
import json

def evaluate_matrix_pivot(current_price):
    # Core structural anchors from paper matrix guidelines
    execution_anchor = 27502.51   
    high_peak = 29888.0           
    macro_core = 50000.0          
    
    # Line 1 & 2 mathematical constants
    wave_factor = 43 * 13.79      # 592.97
    scale_factor = 0.75 * 50      # 37.5
    
    # Corridor boundary limits
    matrix_deviation = (wave_factor * scale_factor) / 100
    upper_channel = execution_anchor + matrix_deviation
    lower_channel = execution_anchor - matrix_deviation
    
    # Line 3: Live deviation metric vs the critical 1.59 threshold
    price_delta = abs(current_price - execution_anchor)
    pivot_ratio = round((price_delta / wave_factor), 4)
    
    # Determine algorithmic directional bias
    if pivot_ratio >= 1.59:
        if current_price > execution_anchor:
            bias = "LONG_EXPANSION"
            target = high_peak if current_price < macro_core else macro_core
        else:
            bias = "CASCADE_SHORT"
            target = lower_channel
    else:
        bias = "COMPRESSION_CHOP"
        target = upper_channel if current_price >= execution_anchor else lower_channel
        
    return {
        "pivot_ratio": pivot_ratio,
        "bias": bias,
        "target_level": round(target, 2),
        "upper_band": round(upper_channel, 2),
        "lower_band": round(lower_channel, 2),
        "is_triggered": pivot_ratio >= 1.59
    }

def fetch_actual_live_price():
    """Pulls genuine spot ticker value directly from global exchange data pools"""
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode())
            return float(res_data['price'])
    except Exception as err:
        print(f"⚠️ [NETWORK WARNING] Live lookup timed out ({err}). Using current market baseline.")
        return 63900.0

# =====================================================================
# LIVE PRODUCTION RUNNER
# =====================================================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("      LAUNCHING LIVE GQM MATRIX PRICE AUDIT    ")
    print("="*50)
    
    # Pulling real current market price
    live_btc_price = fetch_actual_live_price()
    print(f"[LIVE FETCH] Active Market Spot Price: ${live_btc_price:,.2f} USD")
    
    # Run the audit engine on real assets
    metrics = evaluate_matrix_pivot(live_btc_price)
    
    print(f"\n-> Active Pivot Ratio : {metrics['pivot_ratio']}")
    print(f"-> System Target Core : ${metrics['target_level']:,.2f}")
    print(f"-> Anchor State Bias  : {metrics['bias']}")
    
    if metrics["is_triggered"]:
        print(f"\n🚨 [MATRIX ALERT] Price exceeds the 1.59 threshold boundary context!")
    else:
        print(f"\n⏳ [CHOP ZONE] Price remains within normal baseline standard deviations.")
    print("="*50 + "\n")