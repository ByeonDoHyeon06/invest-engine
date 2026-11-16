"""Pure, Decimal-based technical features from finalized, ordered bars."""
from __future__ import annotations

from decimal import Decimal, localcontext
from statistics import median
from typing import Sequence

from invest_engine.domain.events import Bar


def _validate(bars: Sequence[Bar], needed: int) -> None:
    if needed < 1:
        raise ValueError("period must be positive")
    if len(bars) < needed:
        raise ValueError("not enough completed bars")
    if any(not b.finalized for b in bars):
        raise ValueError("unfinalized bars are not allowed")
    if any(a.end > b.start for a, b in zip(bars, bars[1:])):
        raise ValueError("bar sequence overlaps or is out of order")


def ema(bars: Sequence[Bar], period: int) -> Decimal:
    """Seed EMA with SMA(period), then use alpha 2/(period+1)."""
    _validate(bars, period)
    with localcontext() as ctx:
        ctx.prec = 64
        value = sum((b.close for b in bars[:period]), Decimal(0)) / period
        alpha = Decimal(2) / (period + 1)
        for bar in bars[period:]:
            value = alpha * bar.close + (Decimal(1) - alpha) * value
        return +value


def atr(bars: Sequence[Bar], period: int) -> Decimal:
    """Wilder ATR; requires period+1 bars to seed true ranges."""
    _validate(bars, period + 1)
    with localcontext() as ctx:
        ctx.prec = 64
        ranges = [max(curr.high - curr.low,
                      abs(curr.high - prior.close),
                      abs(curr.low - prior.close))
                  for prior, curr in zip(bars, bars[1:])]
        value = sum(ranges[:period], Decimal(0)) / period
        for tr in ranges[period:]:
            value = (value * (period - 1) + tr) / period
        return +value


def median_volume(bars: Sequence[Bar], minimum: int) -> Decimal:
    _validate(bars, minimum)
    with localcontext() as ctx:
        ctx.prec = 64
        return +median([b.volume for b in bars[-minimum:]])
