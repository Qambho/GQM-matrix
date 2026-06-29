"""3-6-9 digital-root vortex compression detection."""

from __future__ import annotations

VORTEX_ROOTS = frozenset({3, 6, 9})


def digital_root(value: int | float | str) -> int:
    """Reduce a numeric value to its digital root (0–9)."""
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return 0
        n = sum(int(d) for d in digits)
    else:
        n = abs(int(round(float(value))))

    if n == 0:
        return 0
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n


def is_vortex_root(root: int) -> bool:
    return root in VORTEX_ROOTS


def vortex_flags(
    price: float,
    timestamp_ms: int,
    volume: float,
) -> dict[str, bool | int]:
    """Flag price, time, and volume when digital root ∈ {3, 6, 9}."""
    price_str = f"{float(price):.2f}".replace(".", "")
    price_root = digital_root(price_str)
    time_root = digital_root(timestamp_ms)
    volume_root = digital_root(abs(volume))

    return {
        "price_root": price_root,
        "time_root": time_root,
        "volume_root": volume_root,
        "price_vortex": is_vortex_root(price_root),
        "time_vortex": is_vortex_root(time_root),
        "volume_vortex": is_vortex_root(volume_root),
        "any_vortex": any(
            is_vortex_root(r) for r in (price_root, time_root, volume_root)
        ),
    }
