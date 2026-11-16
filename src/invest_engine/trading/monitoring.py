"""E3.3 deterministic, read-only market valuation and synthetic account comparison.

No network calls or brokers. A monitoring observation MUST be journaled before it
can authorize a new BUY in the opt-in monitored simulation mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from invest_engine.domain.primitives import InstrumentId, Money, _currency, _decimal, utc_datetime
from invest_engine.trading.models import OrderStatus

if TYPE_CHECKING:
    from invest_engine.trading.ledger import TradingState
    from invest_engine.trading.policy import RiskLimits


@dataclass(frozen=True, slots=True)
class MarketMark:
    instrument: InstrumentId
    price: Decimal
    available_at: datetime
    source: str

    def __post_init__(self) -> None:
        _decimal(self.price, field="mark.price", positive=True)
        object.__setattr__(self, "available_at", utc_datetime(self.available_at))
        if not self.source.strip():
            raise ValueError("mark provenance required")


@dataclass(frozen=True, slots=True)
class FxMark:
    base: str
    quote: str
    rate: Decimal
    available_at: datetime
    source: str

    def __post_init__(self) -> None:
        _currency(self.base)
        _currency(self.quote)
        if self.base == self.quote:
            raise ValueError("FX base and quote must differ")
        _decimal(self.rate, field="fx.rate", positive=True)
        object.__setattr__(self, "available_at", utc_datetime(self.available_at))
        if not self.source.strip():
            raise ValueError("FX provenance required")


@dataclass(frozen=True, slots=True)
class SessionBaseline:
    currency: str
    session_id: str
    equity: Decimal
    started_at: datetime

    def __post_init__(self) -> None:
        _currency(self.currency)
        if not self.session_id.strip():
            raise ValueError("baseline session id required")
        _decimal(self.equity, field="baseline.equity", positive=True)
        object.__setattr__(self, "started_at", utc_datetime(self.started_at))


@dataclass(frozen=True, slots=True)
class ReferencePosition:
    instrument_key: str
    quantity: Decimal

    def __post_init__(self) -> None:
        if not self.instrument_key.strip():
            raise ValueError("reference instrument key required")
        _decimal(self.quantity, field="reference.quantity")
        if self.quantity < 0:
            raise ValueError("reference quantity cannot be negative")


@dataclass(frozen=True, slots=True)
class ExternalAccountReference:
    """Synthetic as-of account snapshot, NOT a real broker connectivity assertion."""

    account_id: str
    as_of: datetime
    cash: tuple[Money, ...]
    positions: tuple[ReferencePosition, ...]
    open_intent_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("reference account required")
        object.__setattr__(self, "as_of", utc_datetime(self.as_of))
        if not isinstance(self.cash, tuple) or not isinstance(self.positions, tuple):
            raise ValueError("reference must contain immutable tuples")
        if len({v.currency for v in self.cash}) != len(self.cash):
            raise ValueError("duplicate reference cash currencies")
        if len({v.instrument_key for v in self.positions}) != len(self.positions):
            raise ValueError("duplicate reference position symbols")
        if self.open_intent_ids is not None and (
            len(set(self.open_intent_ids)) != len(self.open_intent_ids)
            or any(not x.strip() for x in self.open_intent_ids)
        ):
            raise ValueError("duplicate or empty reference order IDs")


@dataclass(frozen=True, slots=True)
class MonitorInput:
    checked_at: datetime
    session_id: str
    base_currency: str
    marks: tuple[MarketMark, ...] = ()
    fx_rates: tuple[FxMark, ...] = ()
    baselines: tuple[SessionBaseline, ...] = ()
    reference: ExternalAccountReference | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", utc_datetime(self.checked_at))
        _currency(self.base_currency)
        if not self.session_id.strip():
            raise ValueError("session id required")
        if any(not isinstance(v, tuple) for v in (self.marks, self.fx_rates, self.baselines)):
            raise ValueError("monitor inputs must be immutable tuples")
        if len({m.instrument.key for m in self.marks}) != len(self.marks):
            raise ValueError("duplicate market marks")
        if len({(f.base, f.quote) for f in self.fx_rates}) != len(self.fx_rates):
            raise ValueError("duplicate FX quotes")
        if len({b.currency for b in self.baselines}) != len(self.baselines):
            raise ValueError("duplicate currency baselines")


@dataclass(frozen=True, slots=True)
class CurrencyValuation:
    currency: str
    equity: Decimal | None
    unrealized_pnl: Decimal | None
    realized_pnl: Decimal
    daily_return: Decimal | None


@dataclass(frozen=True, slots=True)
class MonitorResult:
    checked_at: datetime
    session_id: str
    base_currency: str
    valuations: tuple[CurrencyValuation, ...]
    converted_equity: Decimal | None
    reasons: tuple[str, ...]
    marks: tuple[MarketMark, ...]
    preceding_ordinal: int

    @property
    def healthy(self) -> bool:
        return not self.reasons


def _is_fresh(at: datetime, observed: datetime, max_age: timedelta) -> bool:
    return observed <= at and at - observed <= max_age


def evaluate_monitor(
    state: TradingState, input: MonitorInput, limits: RiskLimits,
) -> MonitorResult:
    """Compute a marked valuation; reasons are sorted, stable decision codes.

    Missing marks are NOT substituted by historical cost. External comparisons
    are as-of and conservative; no FX conversion occurs in a cash ledger.
    """
    reasons: set[str] = set()
    at = input.checked_at
    marks = {v.instrument.key: v for v in input.marks}
    fx = {(v.base, v.quote): v for v in input.fx_rates}
    baselines = {v.currency: v for v in input.baselines}
    rows: list[CurrencyValuation] = []
    by_currency: dict[str, Decimal] = {}
    complete = True
    with localcontext() as ctx:
        ctx.prec = 64
        for balance in state.cash:
            equity = balance.settled + balance.unsettled
            unrealized = Decimal(0)
            realized = Decimal(0)
            currency_complete = True
            for position in state.positions:
                if position.instrument.currency != balance.currency:
                    continue
                realized += position.realized_pnl
                if position.quantity <= 0:
                    continue
                mark = marks.get(position.instrument.key)
                if mark is None:
                    currency_complete = False
                    reasons.add("MARK_MISSING")
                    continue
                if not _is_fresh(at, mark.available_at, limits.mark_max_age):
                    currency_complete = False
                    reasons.add("MARK_STALE_OR_FUTURE")
                    continue
                equity += position.quantity * mark.price
                unrealized += position.quantity * (mark.price - position.average_cost)
            baseline = baselines.get(balance.currency)
            daily_return: Decimal | None = None
            if baseline is None or baseline.session_id != input.session_id or baseline.started_at > at:
                reasons.add("SESSION_BASELINE_MISSING")
            elif currency_complete:
                daily_return = (equity - baseline.equity) / baseline.equity
                if daily_return <= -limits.max_daily_loss_fraction:
                    reasons.add("DAILY_LOSS_LIMIT")
            if currency_complete:
                rows.append(CurrencyValuation(balance.currency, equity, unrealized, realized, daily_return))
                by_currency[balance.currency] = equity
            else:
                # A partial mark is NOT a portfolio valuation. Suppress daily
                # PnL evaluation and never latch based on missing prices.
                complete = False
                rows.append(CurrencyValuation(balance.currency, None, None, realized, None))

        total = Decimal(0)
        for currency, equity in by_currency.items():
            if currency == input.base_currency:
                total += equity
                continue
            rate = fx.get((currency, input.base_currency))
            if rate is None:
                reasons.add("FX_MARK_MISSING")
                continue
            if not _is_fresh(at, rate.available_at, limits.mark_max_age):
                reasons.add("FX_MARK_STALE_OR_FUTURE")
                continue
            total += equity * rate.rate

    # A missing FX quote makes the aggregate untrustworthy. Never pretend
    # the partial sum is the whole account equity.
    if not complete or "FX_MARK_MISSING" in reasons or "FX_MARK_STALE_OR_FUTURE" in reasons:
        total_result: Decimal | None = None
    else:
        total_result = total

    if any(o.status is OrderStatus.UNKNOWN for o in state.orders):
        reasons.add("ORDER_STATUS_UNKNOWN")
    reference = input.reference
    if reference is None:
        if limits.require_account_reference:
            reasons.add("ACCOUNT_REFERENCE_MISSING")
    elif reference.account_id != state.account_id:
        reasons.add("REFERENCE_ACCOUNT_MISMATCH")
    elif (not _is_fresh(at, reference.as_of, limits.mark_max_age)
          or (state.observed_at is not None and reference.as_of < state.observed_at)):
        reasons.add("REFERENCE_STALE_OR_FUTURE")
    else:
        expected_cash = {b.currency: b.settled for b in state.cash}
        actual_cash = {v.currency: v.amount for v in reference.cash}
        if expected_cash != actual_cash:
            reasons.add("CASH_RECONCILIATION_MISMATCH")
        expected_positions = {p.instrument.key: p.quantity for p in state.positions if p.quantity > 0}
        actual_positions = {p.instrument_key: p.quantity for p in reference.positions if p.quantity > 0}
        if expected_positions != actual_positions:
            reasons.add("POSITION_RECONCILIATION_MISMATCH")
        if reference.open_intent_ids is not None:
            open_statuses = (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED,
                             OrderStatus.CANCEL_PENDING, OrderStatus.UNKNOWN)
            expected_orders = {o.intent.intent_id for o in state.orders if o.status in open_statuses}
            if expected_orders != set(reference.open_intent_ids):
                reasons.add("ORDER_RECONCILIATION_MISMATCH")
    return MonitorResult(
        at, input.session_id, input.base_currency, tuple(rows), total_result,
        tuple(sorted(reasons)), tuple(sorted(input.marks, key=lambda x: x.instrument.key)),
        state.last_ordinal,
    )
