"""Account target allocation and broker-free simulated-intent planning.

All intents still require E3 TradingRuntime.submit() risk approval.
No orders are submitted by this module.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, localcontext

from invest_engine.domain.primitives import InstrumentId, _decimal, utc_datetime
from invest_engine.trading.ledger import TradingState
from invest_engine.trading.models import OrderIntent, OrderStatus, Side, TradingConfig
from invest_engine.trading.monitoring import MarketMark
from invest_engine.strategies.contracts import SignalDirection, StrategySignal


@dataclass(frozen=True, slots=True)
class AllocationPolicy:
    max_symbol_fraction: Decimal = Decimal("0.10")
    max_currency_fraction: Decimal = Decimal("0.30")

    def __post_init__(self) -> None:
        for name in ("max_symbol_fraction", "max_currency_fraction"):
            value = _decimal(getattr(self, name), field=name, positive=True)
            if value > 1:
                raise ValueError("allocation fraction cannot exceed one")


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    instrument: InstrumentId
    target_fraction: Decimal
    source_signal_ids: tuple[str, ...]
    strategy_targets: tuple[tuple[str, Decimal], ...]
    stop_price: Decimal | None
    as_of: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AllocationResult:
    plans: tuple[AllocationPlan, ...]
    reason_codes: tuple[str, ...] = ()


def allocate_targets(signals: tuple[StrategySignal, ...], *,
                     as_of: datetime, policy: AllocationPolicy = AllocationPolicy()) -> AllocationResult:
    """Exit overrides longs, cap per symbol/currency, never imply KRW⇄USD FX.

    One active signal per strategy+instrument is permitted in a decision batch.
    Virtual targets allow research attribution; **not** fill-based virtual P&L.
    """
    now = utc_datetime(as_of)
    active = [s for s in signals if s.generated_at <= now < s.expires_at]
    if not active:
        return AllocationResult((), ("NO_ACTIVE_SIGNAL",))
    if len({s.signal_id for s in active}) != len(active):
        raise ValueError("duplicate signal IDs in allocator")
    grouped: dict[str, list[StrategySignal]] = {}
    for signal in active:
        grouped.setdefault(signal.instrument.key, []).append(signal)
    plans: list[AllocationPlan] = []
    currency_totals: dict[str, Decimal] = {}
    reasons: set[str] = set()
    for key in sorted(grouped):
        group = sorted(grouped[key], key=lambda s: (s.strategy_id, s.signal_id))
        if len({s.strategy_id for s in group}) != len(group):
            raise ValueError("multiple conflicting signals from same strategy")
        inst = group[0].instrument
        if any(s.instrument != inst for s in group):
            raise ValueError("instrument metadata conflict")
        expires_at = min(s.expires_at for s in group)
        if any(s.direction is SignalDirection.EXIT for s in group):
            target = Decimal(0)
            virtual: tuple[tuple[str, Decimal], ...] = ()
            stop: Decimal | None = None
            reasons.add("EXIT_TAKES_PRECEDENCE")
        else:
            virtual = tuple((s.strategy_id, s.target_fraction) for s in group)
            target = sum((fraction for _, fraction in virtual), Decimal(0))
            stop_options = [s.stop_price for s in group]
            if any(v is None for v in stop_options):
                reasons.add("STOP_PLAN_REQUIRED")
                continue
            # Lowest stop implies greatest planned long downside (conservative).
            stop = min(v for v in stop_options if v is not None)
            if target > policy.max_symbol_fraction:
                reasons.add("SYMBOL_TARGET_CAPPED")
                with localcontext() as ctx:
                    ctx.prec = 64
                    scale = policy.max_symbol_fraction / target
                    clipped = [(name, fraction * scale) for name, fraction in virtual[:-1]]
                    last_name, _ = virtual[-1]
                    last_fraction = policy.max_symbol_fraction - sum(
                        (fraction for _, fraction in clipped), Decimal(0)
                    )
                    virtual = tuple(clipped + [(last_name, last_fraction)])
                target = policy.max_symbol_fraction
        currency_totals[inst.currency] = currency_totals.get(inst.currency, Decimal(0)) + target
        plans.append(AllocationPlan(inst, target, tuple(s.signal_id for s in group),
                                    virtual, stop, now, expires_at))
    # Reject rather than silently rescale, preserving transparent risk decisions.
    if any(total > policy.max_currency_fraction for total in currency_totals.values()):
        return AllocationResult((), ("CURRENCY_TARGET_EXCEEDED",))
    return AllocationResult(tuple(plans), tuple(sorted(reasons)))


def propose_simulated_intents(
    plans: tuple[AllocationPlan, ...], *,
    state: TradingState, config: TradingConfig,
    marks: tuple[MarketMark, ...], as_of: datetime,
    max_mark_age: timedelta = timedelta(minutes=1),
) -> tuple[OrderIntent, ...]:
    """Compute deterministic delta intents; does not submit, reserve, fill, or FX.

    Orders are *proposals* and can still be rejected by E3 Risk. An existing
    open order for a symbol blocks another planned order.
    """
    now = utc_datetime(as_of)
    if state.account_id != config.account_id or max_mark_age < timedelta(0):
        raise ValueError("wrong account or negative mark max age")
    result: list[OrderIntent] = []
    seen: set[str] = set()
    by_key = {mark.instrument.key: mark for mark in marks}
    if len(by_key) != len(marks):
        raise ValueError("conflicting duplicated market marks")
    for plan in sorted(plans, key=lambda p: p.instrument.key):
        inst = plan.instrument
        if inst.key in seen:
            raise ValueError("duplicate allocation plan for instrument")
        seen.add(inst.key)
        if plan.as_of > now or plan.expires_at <= now:
            continue
        mark = by_key.get(inst.key)
        if (mark is None or mark.instrument != inst or mark.available_at > now
            or now - mark.available_at > max_mark_age):
            continue
        if any(order.intent.instrument.key == inst.key and
               order.status not in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}
               for order in state.orders):
            continue
        cash = state.account(inst.currency)
        rules = config.rules_for(inst)
        try:
            rules.validate_price(mark.price)
        except ValueError:
            continue
        with localcontext() as ctx:
            ctx.prec = 64
            equity_cost = cash.settled + sum(
                (p.quantity * p.average_cost for p in state.positions
                 if p.instrument.currency == inst.currency), Decimal(0)
            )
            held = state.position(inst)
            held_qty = held.quantity if held is not None else Decimal(0)
            delta = equity_cost * plan.target_fraction / mark.price - held_qty
            if abs(delta) < rules.lot_size:
                continue
            quantity = (abs(delta) / rules.lot_size).to_integral_value(rounding=ROUND_FLOOR) * rules.lot_size
            side = Side.BUY if delta > 0 else Side.SELL
            if side is Side.SELL:
                quantity = min(quantity, held_qty - (held.reserved_sell if held else 0))
                quantity = (quantity / rules.lot_size).to_integral_value(rounding=ROUND_FLOOR) * rules.lot_size
            if quantity <= 0 or (side is Side.BUY and
                                  (plan.stop_price is None or plan.stop_price >= mark.price)):
                continue
            digest = hashlib.sha256((config.account_id + ":" + state.digest + ":" +
                                     inst.key + ":" + ",".join(plan.source_signal_ids) +
                                     ":" + now.isoformat()).encode()).hexdigest()[:20]
            result.append(OrderIntent(
                f"allocation:{digest}", config.account_id, "e4-allocator",
                inst, side, quantity, mark.price, now,
                plan.stop_price if side is Side.BUY else None,
            ))
    return tuple(result)
