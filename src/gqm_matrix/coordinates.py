"""Coordinate generation for the MW geometric matrix (x = zodiac°, y = price)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MatrixCoordinate:
    x_degree: float
    y_price: float


class CoordinateGenerator:
    """Maps market instants to (x_degree, y_price) on the rotational matrix."""

    def __init__(self, anchor: float, price_per_degree: float) -> None:
        self.anchor = anchor
        self.price_per_degree = price_per_degree

    def calculate_y_price(self, price: float) -> float:
        if price is None or price <= 0:
            raise ValueError("Invalid market price for coordinate generation.")
        return round(float(price), 2)

    def calculate_x_degree(self, moon_degree: float) -> float:
        if moon_degree is None:
            raise ValueError("Missing moon degree for x-axis coordinate.")
        return round(float(moon_degree) % 360.0, 4)

    def price_to_zodiac_degree(self, price: float) -> float:
        if self.price_per_degree <= 0:
            raise ValueError("price_per_degree must be positive.")
        degree = ((price - self.anchor) / self.price_per_degree) % 360.0
        return round(degree, 4)

    def generate_coordinate(
        self,
        price: float,
        moon_degree: float,
        use_moon_for_x: bool = True,
    ) -> MatrixCoordinate:
        """Both inputs must represent the same market instant."""
        y_price = self.calculate_y_price(price)
        x_degree = (
            self.calculate_x_degree(moon_degree)
            if use_moon_for_x
            else self.price_to_zodiac_degree(price)
        )
        return MatrixCoordinate(x_degree=x_degree, y_price=y_price)

    @classmethod
    def from_scan_report(cls, report: dict[str, Any]) -> CoordinateGenerator:
        grid = report.get("grid", {})
        return cls(
            anchor=float(grid.get("static_anchor", 0)),
            price_per_degree=float(grid.get("price_per_degree", 200)),
        )

    def coordinate_from_scan(self, report: dict[str, Any]) -> MatrixCoordinate:
        market = report["market"]
        celestial = report["celestial"]
        return self.generate_coordinate(
            price=market["price"],
            moon_degree=celestial["moon_degree"],
        )
