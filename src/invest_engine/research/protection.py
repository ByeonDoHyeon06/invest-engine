"""Conservative standing stop/target hypotheses for *offline* OHLCV research.

A protection lot is armed only after its entry Fill has been *observed*, never
retroactively within the entry bar. The simulated sell is an accounting device,
not proof a stop or a take-profit order would have executed at that price.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR, localcontext

from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, _decimal, utc_datetime
from invest_engine.trading.money import InstrumentRules


@dataclass(frozen=True, slots=True)
class ProtectionPolicy:
    """Disabled by default to preserve E5.1/E5.2 backtest behavior."""

    enabled: bool = False
    reward_multiple: Decimal | None = None
    adverse_bps: Decimal = Decimal("0")
    version: str = "protective-ohlcv-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool) or not self.version.strip():
            raise ValueError("invalid protection policy")
        if self.reward_multiple is not None:
            _decimal(self.reward_multiple, field="reward_multiple", positive=True)
        _decimal(self.adverse_bps, field="adverse_bps")
        if self.adverse_bps < 0 or self.adverse_bps >= 10000:
            raise ValueError("adverse_bps must be within [0,10000)")


@dataclass(frozen=True, slots=True)
class ProtectionLot:
    instrument: InstrumentId
    source_execution_id: str
    quantity: Decimal
    stop_price: Decimal
    target_price: Decimal | None
    armed_at: datetime

    def __post_init__(self) -> None:
        if not self.source_execution_id:
            raise ValueError("source execution id required")
        _decimal(self.quantity, field="protected quantity", positive=True)
        _decimal(self.stop_price, field="stop price", positive=True)
        if self.target_price is not None:
            _decimal(self.target_price, field="target price", positive=True)
            if self.target_price <= self.stop_price:
                raise ValueError("target price must exceed stop")
        object.__setattr__(self, "armed_at", utc_datetime(self.armed_at))


@dataclass(frozen=True, slots=True)
class ProtectiveExit:
    source_execution_id: str
    quantity: Decimal
    price: Decimal
    observed_at: datetime
    reason_code: str


def new_protected_lot(
    instrument: InstrumentId, *, source_execution_id: str, quantity: Decimal,
    entry_price: Decimal, stop_price: Decimal, armed_at: datetime,
    policy: ProtectionPolicy,
) -> ProtectionLot:
    """Never assume an E4 planned stop is active before a recorded entry fill."""
    _decimal(entry_price, field="entry price", positive=True)
    _decimal(stop_price, field="stop price", positive=True)
    if not policy.enabled or stop_price >= entry_price:
        raise ValueError("enabled protection requires stop below actual entry price")
    with localcontext() as ctx:
        ctx.prec = 64
        target = (entry_price + (entry_price - stop_price) * policy.reward_multiple
                  if policy.reward_multiple is not None else None)
    return ProtectionLot(instrument, source_execution_id, quantity,
                         stop_price, target, armed_at)


def protective_exit(
    lot: ProtectionLot, event: EventEnvelope[MarketPayload],
    rules: InstrumentRules, policy: ProtectionPolicy, *,
    remaining_volume: Decimal,
) -> ProtectiveExit | None:
    """Stop-first worst case, adverse gap opening, capped participation.

    The OHLCV candle cannot identify the intrabar path. Stops trigger on a
    low <= stop, targets on a high >= target, and collisions always choose
    the stop. No favorable open-price improvement is credited for targets.
    """
    bar = event.payload
    if (not policy.enabled or not isinstance(bar, Bar) or not bar.finalized
        or bar.kind is not BarKind.TIME or event.instrument_id != lot.instrument
        or lot.armed_at > bar.start or event.available_at < bar.end
        or event.received_at < bar.end):
        return None
    if remaining_volume < 0:
        raise ValueError("remaining volume cannot be negative")
    if remaining_volume == 0 or bar.volume <= 0:
        return None
    stop_hit = bar.low <= lot.stop_price
    # A target limit must be penetrated rather than merely touched; using the
    # adverse execution buffer avoids inventing queue priority from OHLCV.
    target_hit = (lot.target_price is not None and
                  bar.high > lot.target_price * (
                      Decimal(1) + policy.adverse_bps / Decimal(10000)))
    if not stop_hit and not target_hit:
        return None
    with localcontext() as ctx:
        ctx.prec = 64
        if stop_hit:
            if bar.open < lot.stop_price:
                base = bar.open
                reason = "GAP_BELOW_STOP"
            else:
                base = lot.stop_price
                reason = "STOP_FIRST_COLLISION" if target_hit else "STOP_TRIGGERED"
        else:
            assert lot.target_price is not None
            base = lot.target_price
            reason = "TARGET_TRIGGERED"
        # Execution price never improves versus the trigger in this model.
        modeled = base * (Decimal(1) - policy.adverse_bps / Decimal(10000))
        price = (modeled / rules.tick_size).to_integral_value(rounding=ROUND_FLOOR) * rules.tick_size
        if price <= 0:
            raise ValueError("adverse fill would produce a nonpositive valid-tick price")
        quantity = min(lot.quantity, remaining_volume)
        quantity = (quantity / rules.lot_size).to_integral_value(rounding=ROUND_FLOOR) * rules.lot_size
        if quantity <= 0:
            return None
    return ProtectiveExit(lot.source_execution_id, quantity, price,
                          max(event.available_at, event.received_at, bar.end), reason)


def session_close_exit(
    lot: ProtectionLot, event: EventEnvelope[MarketPayload],
    rules: InstrumentRules, policy: ProtectionPolicy, *,
    session_end: datetime, remaining_volume: Decimal,
) -> ProtectiveExit | None:
    """Standing liquidation at the final bar's open, observed after its end.

    This is a precommitted research assumption, not an actual opening print
    fill or market-on-close order. Minute volume only bounds modeled size.
    """
    bar = event.payload
    if (not policy.enabled or not isinstance(bar, Bar) or not bar.finalized
        or bar.kind is not BarKind.TIME or event.instrument_id != lot.instrument
        or bar.end != utc_datetime(session_end) or lot.armed_at > bar.start
        or event.available_at < bar.end or event.received_at < bar.end):
        return None
    _decimal(remaining_volume, field="remaining volume")
    if remaining_volume < 0:
        raise ValueError("remaining volume cannot be negative")
    if bar.volume <= 0 or remaining_volume == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 64
        modeled = bar.open * (Decimal(1) - policy.adverse_bps / Decimal(10000))
        price = (modeled / rules.tick_size).to_integral_value(rounding=ROUND_FLOOR) * rules.tick_size
        if price <= 0:
            raise ValueError("adverse close liquidation produces a nonpositive tick price")
        quantity = min(lot.quantity, remaining_volume)
        quantity = (quantity / rules.lot_size).to_integral_value(rounding=ROUND_FLOOR) * rules.lot_size
        if quantity <= 0:
            return None
    return ProtectiveExit(lot.source_execution_id, quantity, price,
                          max(event.available_at, event.received_at, bar.end),
                          "SESSION_CLOSE_LIQUIDATION")


def consume_protection(lots: tuple[ProtectionLot, ...], execution_id: str,
                       quantity: Decimal) -> tuple[ProtectionLot, ...]:
    """Debits a *specific* entry lot when its protective sell fills."""
    _decimal(quantity, field="protected exit quantity", positive=True)
    result: list[ProtectionLot] = []
    consumed = False
    for lot in lots:
        if lot.source_execution_id == execution_id:
            if consumed or quantity > lot.quantity:
                raise ValueError("protection lot insufficient or duplicate")
            consumed = True
            if lot.quantity > quantity:
                result.append(replace(lot, quantity=lot.quantity - quantity))
        else:
            result.append(lot)
    if not consumed:
        raise ValueError("unknown protection lot")
    return tuple(result)


def consume_oldest(lots: tuple[ProtectionLot, ...], instrument: InstrumentId,
                   quantity: Decimal) -> tuple[ProtectionLot, ...]:
    """Existing non-protective sell debits the oldest protected inventory."""
    _decimal(quantity, field="sell quantity", positive=True)
    remaining = quantity
    result: list[ProtectionLot] = []
    for lot in lots:
        if lot.instrument.key != instrument.key or remaining <= 0:
            result.append(lot)
            continue
        taken = min(lot.quantity, remaining)
        remaining -= taken
        if lot.quantity > taken:
            result.append(replace(lot, quantity=lot.quantity - taken))
    if remaining != 0:
        raise ValueError("selling untracked protected inventory")
    return tuple(result)
