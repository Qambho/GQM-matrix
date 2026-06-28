"""Sidereal longitude confluence and geometric aspect analysis."""

from __future__ import annotations

from typing import Any

ZODIAC_SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

ASPECT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"name": "Conjunction", "symbol": "☌", "angle": 0.0, "orb": 8.0},
    {"name": "Semi-Sextile", "symbol": "⚺", "angle": 30.0, "orb": 3.0},
    {"name": "Sextile", "symbol": "⚹", "angle": 60.0, "orb": 6.0},
    {"name": "Square", "symbol": "□", "angle": 90.0, "orb": 8.0},
    {"name": "Trine", "symbol": "△", "angle": 120.0, "orb": 8.0},
    {"name": "Quincunx", "symbol": "⚻", "angle": 150.0, "orb": 3.0},
    {"name": "Opposition", "symbol": "☍", "angle": 180.0, "orb": 8.0},
)

CARDINAL_HARMONICS: tuple[tuple[float, str], ...] = (
    (0.0, "Aries Point"),
    (90.0, "Cancer Point"),
    (180.0, "Libra Point"),
    (270.0, "Capricorn Point"),
)


def degree_to_sign(degree: float) -> dict[str, Any]:
    normalized = float(degree) % 360.0
    index = int(normalized // 30) % 12
    sign_degree = round(normalized % 30.0, 2)
    return {
        "sign": ZODIAC_SIGNS[index],
        "sign_degree": sign_degree,
        "label": f"{ZODIAC_SIGNS[index]} {sign_degree}°",
    }


def angular_separation(degree_a: float, degree_b: float) -> float:
    diff = abs(degree_a - degree_b) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return round(diff, 2)


def match_aspect(separation: float) -> dict[str, Any] | None:
    for aspect in ASPECT_DEFINITIONS:
        exactness = abs(separation - aspect["angle"])
        if exactness <= aspect["orb"]:
            return {
                "aspect_name": aspect["name"],
                "aspect_symbol": aspect["symbol"],
                "target_angle": aspect["angle"],
                "separation": separation,
                "orb": aspect["orb"],
                "exactness": round(exactness, 2),
            }
    return None


def analyze_confluence(
    moon_degree: float,
    mercury_degree: float,
    mars_degree: float,
) -> dict[str, Any]:
    planets = {
        "Moon": float(moon_degree) % 360.0,
        "Mercury": float(mercury_degree) % 360.0,
        "Mars": float(mars_degree) % 360.0,
    }

    raw_sum = sum(planets.values())
    composite = raw_sum % 360.0

    planet_rows = []
    reasoning_steps: list[str] = []
    for name, degree in planets.items():
        sign = degree_to_sign(degree)
        planet_rows.append(
            {
                "name": name,
                "degree": round(degree, 2),
                "sign": sign["sign"],
                "sign_degree": sign["sign_degree"],
                "label": sign["label"],
            }
        )
        reasoning_steps.append(
            f"{name} sidereal longitude: {degree:.2f}° ({sign['label']})."
        )

    reasoning_steps.append(
        f"Raw longitude sum: {planets['Moon']:.2f}° + {planets['Mercury']:.2f}° + "
        f"{planets['Mars']:.2f}° = {raw_sum:.2f}°."
    )
    reasoning_steps.append(f"Composite longitude (mod 360): {composite:.2f}°.")

    pairwise_aspects: list[dict[str, Any]] = []
    pairs = (("Moon", "Mercury"), ("Moon", "Mars"), ("Mercury", "Mars"))
    for planet_a, planet_b in pairs:
        separation = angular_separation(planets[planet_a], planets[planet_b])
        aspect = match_aspect(separation)
        if not aspect:
            reasoning_steps.append(
                f"{planet_a}–{planet_b} separation: {separation:.2f}° — no major aspect within orb."
            )
            continue

        reasoning = (
            f"{planet_a}–{planet_b} separation is {separation:.2f}°, forming a "
            f"{aspect['aspect_name']} {aspect['aspect_symbol']} "
            f"(target {aspect['target_angle']:.0f}°, exactness {aspect['exactness']:.2f}° "
            f"within {aspect['orb']:.0f}° orb)."
        )
        reasoning_steps.append(reasoning)
        pairwise_aspects.append(
            {
                "planet_a": planet_a,
                "planet_b": planet_b,
                "reasoning": reasoning,
                **aspect,
            }
        )

    sum_harmonic: dict[str, Any] | None = None
    composite_separation = min(composite, 360.0 - composite)
    composite_aspect = match_aspect(composite_separation)
    if composite_aspect:
        sum_harmonic = {
            "kind": "composite_aspect",
            "reasoning": (
                f"The composite sum {composite:.2f}° sits {composite_separation:.2f}° from the "
                f"0° reference, aligning with a {composite_aspect['aspect_name']} "
                f"{composite_aspect['aspect_symbol']} harmonic."
            ),
            "composite_degree": round(composite, 2),
            **composite_aspect,
        }
        reasoning_steps.append(sum_harmonic["reasoning"])

    for target, label in CARDINAL_HARMONICS:
        delta = min(abs(composite - target), 360.0 - abs(composite - target))
        if delta <= 3.0 and sum_harmonic is None:
            sum_harmonic = {
                "kind": "cardinal_harmonic",
                "aspect_name": f"Cardinal alignment ({label})",
                "aspect_symbol": "⊕",
                "target_angle": target,
                "composite_degree": round(composite, 2),
                "separation": round(delta, 2),
                "orb": 3.0,
                "exactness": round(delta, 2),
                "reasoning": (
                    f"Composite longitude {composite:.2f}° is within {delta:.2f}° of the "
                    f"{label} ({target:.0f}°), indicating a cardinal harmonic trigger."
                ),
            }
            reasoning_steps.append(sum_harmonic["reasoning"])
            break

    has_active_aspect = bool(pairwise_aspects or sum_harmonic)
    if pairwise_aspects:
        lead = pairwise_aspects[0]
        summary = (
            f"{lead['aspect_symbol']} {lead['aspect_name']} · "
            f"{lead['planet_a']}–{lead['planet_b']}"
        )
        if len(pairwise_aspects) > 1:
            summary = f"{len(pairwise_aspects)} aspects · {summary}"
    elif sum_harmonic:
        summary = f"{sum_harmonic['aspect_symbol']} {sum_harmonic['aspect_name']}"
    else:
        summary = f"Σ {raw_sum:.2f}° → {composite:.2f}° · No aspect"

    if has_active_aspect:
        reasoning_steps.append(
            "Active geometry detected — confluence window may amplify lattice reactions "
            "when price interacts with primary vector nodes."
        )
    else:
        reasoning_steps.append(
            "No geometric aspect is within standard orb for the three-body sum or pairwise separations."
        )

    return {
        "planets": planet_rows,
        "longitude_sum_raw": round(raw_sum, 2),
        "longitude_sum_mod360": round(composite, 2),
        "has_active_aspect": has_active_aspect,
        "summary": summary,
        "pairwise_aspects": pairwise_aspects,
        "sum_harmonic": sum_harmonic,
        "reasoning_steps": reasoning_steps,
    }
