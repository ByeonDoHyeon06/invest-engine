"""Conservative limit-order execution assumptions for finalized historical bars.

A bar proves neither order queue priority nor actual fill. The model requires
*strict* price penetration plus an assumed spread/impact buffer; no favorable
price improvement is inferred, and fills are recorded only at bar availability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR, localcontext

from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import _decimal
from invest_engine.trading.models import OrderStatus, Side
from invest_engine.trading.ledger import OrderRecord
from invest_engine.trading.money import InstrumentRules


@dataclass(frozen=True, slots=True)
class BarFillPolicy:
    participation: Decimal = Decimal("0.05")
    spread_bps: Decimal = Decimal("5")
    impact_bps: Decimal = Decimal("5")
    version: str = "penetration-limit-v1"

    def __post_init__(self) -> None:
        for name in ("participation", "spread_bps", "impact_bps"):
            value = _decimal(getattr(self, name), field=name)
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.participation <= 0 or self.participation > 1:
            raise ValueError("participation must be within (0,1]")
        if not self.version.strip():
            raise ValueError("fill model version required")


@dataclass(frozen=True, slots=True)
class FillCandidate:
    intent_id: str
    quantity: Decimal
    price: Decimal
    observed_at: datetime
    source_event_id: str


def eligible_fill(
    order: OrderRecord, event: EventEnvelope[MarketPayload],
    rules: InstrumentRules, policy: BarFillPolicy,
    *, used_volume: Decimal = Decimal(0),
) -> FillCandidate | None:
    """Strict next-eligible bar crossing, bounded by available bar volume.

    The signal/intent must exist at the *start* of the bar, but we record fills
    only after that bar is fully observable. Same-bar or late-bar entry is barred.
    Zero-volume / incomplete / non-time bars cannot fill.
    """
    bar = event.payload
    if not isinstance(bar, Bar) or not bar.finalized or bar.kind is not BarKind.TIME:
        return None
    if event.instrument_id != order.intent.instrument:
        return None
    if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED):
        return None
    if order.intent.submitted_at > bar.start or event.received_at < bar.end:
        return None
    if bar.volume <= 0 or order.remaining <= 0:
        return None
    if used_volume < 0 or used_volume > bar.volume:
        raise ValueError("invalid consumed bar volume")
    # Penetration is intentionally stricter than 'limit touched'.
    with localcontext() as ctx:
        ctx.prec = 64
        buffer = order.intent.limit_price * (policy.spread_bps + policy.impact_bps) / Decimal(10000)
        if order.intent.side is Side.BUY:
            crossed = bar.low < order.intent.limit_price - buffer
        else:
            crossed = bar.high > order.intent.limit_price + buffer
        if not crossed:
            return None
        volume_cap = (bar.volume * policy.participation - used_volume)
        if volume_cap <= 0:
            return None
        qty = min(order.remaining, volume_cap)
        qty = (qty / rules.lot_size).to_integral_value(rounding=ROUND_FLOOR) * rules.lot_size
        if qty <= 0:
            return None
    return FillCandidate(order.intent.intent_id, qty, order.intent.limit_price,
                         max(event.available_at, event.received_at, bar.end), event.event_id)
