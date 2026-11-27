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


@dataclass(frozen=True, slots=True)
class SimulatedIntentProposalResult:
    proposal_id: str
    instrument: InstrumentId
    intent: OrderIntent | None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, str) or not self.proposal_id.strip():
            raise ValueError("proposal result identity is required")
        if not isinstance(self.instrument, InstrumentId):
            raise ValueError("proposal result instrument is required")
        if self.intent is None:
            if not self.reason_codes:
                raise ValueError("no-action proposal result requires a reason")
        elif self.intent.instrument != self.instrument or self.reason_codes:
            raise ValueError("intent proposal result is inconsistent")


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


def propose_simulated_intent_results(
    plans: tuple[AllocationPlan, ...], *,
    state: TradingState, config: TradingConfig,
    marks: tuple[MarketMark, ...], as_of: datetime,
    max_mark_age: timedelta = timedelta(minutes=1),
    target_equity_by_currency: tuple[tuple[str, Decimal], ...] | None = None,
) -> tuple[SimulatedIntentProposalResult, ...]:
    """Explain every deterministic intent proposal or explicit no-action result.

    Orders are *proposals* and can still be rejected by E3 Risk. An existing
    open order for a symbol blocks another planned order.
    """
    now = utc_datetime(as_of)
    if state.account_id != config.account_id or max_mark_age < timedelta(0):
        raise ValueError("wrong account or negative mark max age")
    result: list[SimulatedIntentProposalResult] = []
    seen: set[str] = set()
    by_key = {mark.instrument.key: mark for mark in marks}
    if len(by_key) != len(marks):
        raise ValueError("conflicting duplicated market marks")
    open_instrument_keys = {
        order.intent.instrument.key
        for order in state.orders
        if order.status
        not in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}
    }
    target_equity: dict[str, Decimal] | None = None
    if target_equity_by_currency is not None:
        if not isinstance(target_equity_by_currency, tuple):
            raise ValueError("target equity rows must be an immutable tuple")
        target_equity = {}
        for currency, value in target_equity_by_currency:
            if not isinstance(currency, str) or currency in target_equity:
                raise ValueError("target equity currencies must be unique strings")
            config.cash_rules(currency)
            target_equity[currency] = _decimal(
                value,
                field="target_equity",
                positive=True,
            )
        missing = {
            plan.instrument.currency for plan in plans
        } - target_equity.keys()
        if missing:
            raise ValueError("target equity is missing a plan currency")
    for plan in sorted(plans, key=lambda p: p.instrument.key):
        inst = plan.instrument
        if inst.key in seen:
            raise ValueError("duplicate allocation plan for instrument")
        seen.add(inst.key)
        digest = hashlib.sha256((config.account_id + ":" + state.digest + ":" +
                                 inst.key + ":" + ",".join(plan.source_signal_ids) +
                                 ":" + now.isoformat()).encode()).hexdigest()[:20]
        proposal_id = f"allocation:{digest}"

        def no_action(
            reason: str,
            *,
            current_proposal_id: str = proposal_id,
            current_instrument: InstrumentId = inst,
        ) -> None:
            result.append(
                SimulatedIntentProposalResult(
                    current_proposal_id,
                    current_instrument,
                    None,
                    (reason,),
                )
            )

        if plan.as_of > now or plan.expires_at <= now:
            no_action("NO_ACTION_PLAN_INACTIVE")
            continue
        mark = by_key.get(inst.key)
        if mark is None:
            no_action("NO_ACTION_MARK_MISSING")
            continue
        if mark.instrument != inst:
            no_action("NO_ACTION_MARK_MISMATCH")
            continue
        if mark.available_at > now:
            no_action("NO_ACTION_MARK_NOT_AVAILABLE")
            continue
        if now - mark.available_at > max_mark_age:
            no_action("NO_ACTION_MARK_STALE")
            continue
        if inst.key in open_instrument_keys:
            no_action("NO_ACTION_OPEN_ORDER")
            continue
        cash = state.account(inst.currency)
        rules = config.rules_for(inst)
        try:
            rules.validate_price(mark.price)
        except ValueError:
            no_action("NO_ACTION_INVALID_MARK_PRICE")
            continue
        with localcontext() as ctx:
            ctx.prec = 64
            equity_cost = (
                target_equity[inst.currency]
                if target_equity is not None
                else cash.settled + sum(
                    (p.quantity * p.average_cost for p in state.positions
                     if p.instrument.currency == inst.currency), Decimal(0)
                )
            )
            held = state.position(inst)
            held_qty = held.quantity if held is not None else Decimal(0)
            delta = equity_cost * plan.target_fraction / mark.price - held_qty
            if abs(delta) < rules.lot_size:
                no_action("NO_ACTION_TARGET_BELOW_LOT")
                continue
            quantity = (abs(delta) / rules.lot_size).to_integral_value(rounding=ROUND_FLOOR) * rules.lot_size
            side = Side.BUY if delta > 0 else Side.SELL
            if side is Side.SELL:
                quantity = min(quantity, held_qty - (held.reserved_sell if held else 0))
                quantity = (quantity / rules.lot_size).to_integral_value(rounding=ROUND_FLOOR) * rules.lot_size
            if quantity <= 0:
                no_action("NO_ACTION_NO_SELLABLE_QUANTITY")
                continue
            if side is Side.BUY and (
                plan.stop_price is None or plan.stop_price >= mark.price
            ):
                no_action("NO_ACTION_INVALID_BUY_STOP")
                continue
            intent = OrderIntent(
                proposal_id, config.account_id, "e4-allocator",
                inst, side, quantity, mark.price, now,
                plan.stop_price if side is Side.BUY else None,
            )
            result.append(
                SimulatedIntentProposalResult(proposal_id, inst, intent)
            )
    return tuple(result)


def propose_simulated_intents(
    plans: tuple[AllocationPlan, ...], *,
    state: TradingState, config: TradingConfig,
    marks: tuple[MarketMark, ...], as_of: datetime,
    max_mark_age: timedelta = timedelta(minutes=1),
    target_equity_by_currency: tuple[tuple[str, Decimal], ...] | None = None,
) -> tuple[OrderIntent, ...]:
    """Preserve the legacy proposal-only API while detailed audit is additive."""
    return tuple(
        result.intent
        for result in propose_simulated_intent_results(
            plans,
            state=state,
            config=config,
            marks=marks,
            as_of=as_of,
            max_mark_age=max_mark_age,
            target_equity_by_currency=target_equity_by_currency,
        )
        if result.intent is not None
    )
