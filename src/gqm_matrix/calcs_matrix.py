"""GQM Geo-Quantum Matrix pivot calculation engine (Umair project)."""


def evaluate_matrix_pivot(current_price: float) -> dict[str, float | str | bool]:
    execution_anchor = 27502.51
    high_peak = 29888.0
    macro_core = 50000.0

    wave_factor = 43 * 13.79
    scale_factor = 0.75 * 50

    matrix_deviation = (wave_factor * scale_factor) / 100
    upper_channel = execution_anchor + matrix_deviation
    lower_channel = execution_anchor - matrix_deviation

    price_delta = abs(current_price - execution_anchor)
    pivot_ratio = round((price_delta / wave_factor), 4)

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
        "is_triggered": pivot_ratio >= 1.59,
    }
