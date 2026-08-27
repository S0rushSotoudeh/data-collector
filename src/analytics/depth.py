from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class DepthLevel:
    level: int
    bid_price: float
    bid_volume: int
    bid_order_count: int
    ask_price: float
    ask_volume: int
    ask_order_count: int


@dataclass(frozen=True)
class DepthBook:
    source_time: datetime
    levels: tuple[DepthLevel, ...]

    @property
    def best(self) -> DepthLevel | None:
        return min(self.levels, key=lambda item: item.level) if self.levels else None

    def price(self, side: Side) -> float | None:
        best = self.best
        return None if best is None else (best.ask_price if side == "buy" else best.bid_price)

    def queue_volume(self, side: Side) -> int:
        best = self.best
        return 0 if best is None else int(best.bid_volume if side == "buy" else best.ask_volume)

    def total_volume(self, side: Side) -> int:
        return sum(max(0, int(level.ask_volume if side == "buy" else level.bid_volume)) for level in self.levels)

    def fills(self, side: Side, quantity: int) -> list[tuple[int, float, int]] | None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        rows = [
            (
                level.level,
                float(level.ask_price if side == "buy" else level.bid_price),
                max(0, int(level.ask_volume if side == "buy" else level.bid_volume)),
            )
            for level in self.levels
        ]
        rows = [(level, price, volume) for level, price, volume in rows if price > 0 and volume > 0]
        rows.sort(key=lambda item: item[1], reverse=side == "sell")
        remaining = quantity
        fills: list[tuple[int, float, int]] = []
        for level, price, volume in rows:
            filled = min(remaining, volume)
            fills.append((level, price, filled))
            remaining -= filled
            if remaining == 0:
                return fills
        return None

    def vwap(self, side: Side, quantity: int) -> float | None:
        fills = self.fills(side, quantity)
        return None if fills is None else sum(price * filled for _, price, filled in fills) / quantity

    def validation_reasons(self, label: str) -> list[str]:
        best = self.best
        if best is None:
            return [f"missing_{label}_book"]
        reasons: list[str] = []
        if best.bid_price <= 0 or best.ask_price <= 0:
            reasons.append(f"{label}_one_sided_or_non_positive")
        if best.bid_price > best.ask_price:
            reasons.append(f"{label}_crossed_book")
        if best.bid_volume <= 0 or best.ask_volume <= 0:
            reasons.append(f"{label}_zero_top_volume")
        return reasons
