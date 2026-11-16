"""E3 purely simulated trading runtime; no real order transport by design."""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Money, _decimal, utc_datetime
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.ledger import (
    EntriesPaused, EntriesResumed, FillRecorded, OrderAccepted, OrderCanceled, OrderCancelPending,
    OrderReconciled, OrderRejected, OrderReserved, OrderUnknown,
    TradingEvent, TradingPayload, TradingStatus, exposure_for, initial_trading_state,
    reduce_trade_event,
)
from invest_engine.trading.models import (
    DecisionStatus, OrderIntent, OrderStatus, RiskDecision, Side, SimulatedFill, TradingConfig,
)
from invest_engine.trading.policy import RiskLimits, evaluate_order


@dataclass(frozen=True, slots=True)
class ExitQuote:
    instrument: InstrumentId
    limit_price: Decimal
    available_at: datetime

    def __post_init__(self) -> None:
        _decimal(self.limit_price, field="exit.quote", positive=True)
        object.__setattr__(self, "available_at", utc_datetime(self.available_at))


@dataclass(frozen=True, slots=True)
class SimulatedCancelCommand:
    intent_id: str


@dataclass(frozen=True, slots=True)
class SimulatedSubmitCommand:
    """Intention to pass an approved order to a SIMULATED broker only."""
    intent_id: str
    command_id: str


@dataclass(frozen=True, slots=True)
class SubmitOutcome:
    decision: RiskDecision
    commands: tuple[SimulatedSubmitCommand, ...] = ()


class TradingRuntime:
    """Single-writer simulation. All persisted state transitions are events."""

    def __init__(
        self, config: TradingConfig, opening_cash: tuple[Money, ...],
        limits: RiskLimits | None = None,
        *, journal: SQLiteTradingJournal | None = None,
        checkpoint_interval: int = 10,
    ) -> None:
        if checkpoint_interval < 1:
            raise ValueError("checkpoint interval must be positive")
        self.config = config
        self.limits = limits if limits is not None else RiskLimits()
        self.journal = journal
        self.checkpoint_interval = checkpoint_interval
        self.state = initial_trading_state(config.account_id, opening_cash)
        for cash in self.state.cash:
            rule = config.cash_rules(cash.currency)
            if rule.settle(cash.settled) != cash.settled:
                raise ValueError("opening balance violates currency precision")
        if journal is not None:
            self.state = journal.restore(self.state, config, self.limits)
        self._halt_reason: str | None = journal.halt_reason() if journal else None

    def _emit(self, payload: TradingPayload, at: datetime, event_id: str) -> TradingEvent:
        """Rejects invalid transitions and freezes output only after durable commit."""
        if self.state.status is TradingStatus.HALTED:
            raise InvalidEvent("runtime halted")
        event = TradingEvent(event_id, self.state.last_ordinal + 1, utc_datetime(at), payload)
        try:
            proposed = reduce_trade_event(self.state, event, self.config)
            if self.journal is not None:
                self.journal.commit(event, proposed, checkpoint=(event.ordinal+1) % self.checkpoint_interval == 0)
            self.state = proposed
            return event
        except Exception as exc:
            self.state = replace(self.state, status=TradingStatus.HALTED)
            self._halt_reason = f"{type(exc).__name__}: {exc}"
            if self.journal is not None:
                with suppress(Exception):
                    self.journal.record_halt(self._halt_reason)
            raise

    def submit(self, intent: OrderIntent) -> SubmitOutcome:
        existing = self.state.order(intent.intent_id)
        if existing is not None:
            if existing.intent != intent:
                self._force_halt("same intent id has different details")
                raise InvalidEvent("conflicting repeated order intent")
            if existing.status is OrderStatus.REJECTED:
                return SubmitOutcome(RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=existing.reason_codes))
            # Idempotency: does not generate another outbox command / submit.
            return SubmitOutcome(RiskDecision(intent.intent_id, DecisionStatus.APPROVED,
                                              approved_qty=intent.quantity, reservation=existing.reserved_cash))
        if self.state.status is TradingStatus.HALTED:
            return SubmitOutcome(RiskDecision(intent.intent_id, DecisionStatus.HALTED, reason_codes=("RUNTIME_HALTED",)))
        if self.state.entry_pause_reason is not None and intent.side is Side.BUY:
            decision = RiskDecision(
                intent.intent_id, DecisionStatus.REJECTED, reason_codes=("NEW_ENTRIES_PAUSED",)
            )
        elif intent.account_id != self.config.account_id:
            decision = RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("ACCOUNT_MISMATCH",))
        else:
            try:
                exposure = exposure_for(self.state, intent.instrument.currency, intent.instrument)
                unknown = any(o.status is OrderStatus.UNKNOWN for o in self.state.orders)
                decision = evaluate_order(intent, self.config, self.limits, exposure, halted=unknown)
            except InvalidEvent:
                decision = RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("UNFUNDED_CURRENCY",))
        if decision.decision is DecisionStatus.APPROVED:
            self._emit(OrderReserved(intent, decision.reservation), intent.submitted_at, "reserved:"+intent.intent_id)
            return SubmitOutcome(decision, (SimulatedSubmitCommand(intent.intent_id, "sim-submit:"+intent.intent_id),))
        self._emit(OrderRejected(intent, decision.reason_codes), intent.submitted_at, "rejected:"+intent.intent_id)
        return SubmitOutcome(decision)

    def accept_simulated(self, intent_id: str, at: datetime) -> None:
        self._emit(OrderAccepted(intent_id), at, "accepted:"+intent_id)

    def mark_unknown(self, intent_id: str, at: datetime) -> None:
        self._emit(OrderUnknown(intent_id), at, "unknown:"+intent_id)

    def reconcile(self, intent_id: str, status: OrderStatus, at: datetime) -> None:
        self._emit(OrderReconciled(intent_id, status), at, "reconcile:"+intent_id)

    def pause_new_entries(self, *, reason: str, at: datetime) -> None:
        """Operator safety pause. Does not cancel existing orders or positions."""
        self._emit(EntriesPaused(reason), at, "pause:"+str(self.state.last_ordinal+1))

    def resume_new_entries(self, *, reviewed_by: str, at: datetime) -> None:
        """A reviewed resume; blocked when unresolved UNKNOWN orders remain."""
        if not reviewed_by.strip():
            raise PermissionError("reviewer identity is required")
        self._emit(EntriesResumed(reviewed_by), at, "resume:"+str(self.state.last_ordinal+1))

    def request_cancel_all(self, *, at: datetime) -> tuple["SimulatedCancelCommand", ...]:
        """Request cancellation of accepted orders; never presume success."""
        commands: list[SimulatedCancelCommand] = []
        for order in tuple(self.state.orders):
            if order.status in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED):
                self.request_cancel(order.intent.intent_id, at)
                commands.append(SimulatedCancelCommand(order.intent.intent_id))
        return tuple(commands)

    def plan_flatten(self, *, at: datetime, quotes: tuple["ExitQuote", ...],
                     max_age: timedelta) -> tuple[OrderIntent, ...]:
        """Return only *proposed* synthetic SELL intents; no orders are submitted.

        All open positions require a supplied valid fresh quote or the entire
        plan is rejected. Remaining reserved SELL quantity is not double-sold.
        """
        now = utc_datetime(at)
        if max_age < timedelta(0):
            raise ValueError("max_age must be nonnegative")
        by_key = {item.instrument.key: item for item in quotes}
        if len(by_key) != len(quotes):
            raise InvalidEvent("duplicate flatten quotes")
        intents: list[OrderIntent] = []
        for position in self.state.positions:
            free = position.quantity - position.reserved_sell
            if free <= 0:
                continue
            quote = by_key.get(position.instrument.key)
            if quote is None or quote.available_at > now or now - quote.available_at > max_age:
                raise InvalidEvent("missing or stale quote for flatten plan")
            rules = self.config.rules_for(position.instrument)
            rules.validate_price(quote.limit_price)
            rules.validate_quantity(free)
            intents.append(OrderIntent(
                f"flatten:{position.instrument.key}:{self.state.last_ordinal+1}",
                self.config.account_id, "operator:flatten", position.instrument,
                Side.SELL, free, quote.limit_price, now,
            ))
        return tuple(sorted(intents, key=lambda item: item.instrument.key))

    def request_cancel(self, intent_id: str, at: datetime) -> None:
        self._emit(OrderCancelPending(intent_id), at, "cancel-requested:"+intent_id)

    def confirm_cancel(self, intent_id: str, at: datetime) -> None:
        self._emit(OrderCanceled(intent_id), at, "canceled:"+intent_id)

    def fill_simulated(
        self, intent_id: str, *, price: Decimal, quantity: Decimal,
        execution_id: str, at: datetime,
    ) -> None:
        if execution_id in self.state.seen_fills:
            previous = next(f for f in self.state.fills if f.execution_id == execution_id)
            if (previous.intent_id, previous.price, previous.quantity, previous.occurred_at) != (
                intent_id, price, quantity, utc_datetime(at)
            ):
                self._force_halt("same execution id has conflicting fill details")
                raise InvalidEvent("conflicting repeated fill")
            return
        order = self.state.order(intent_id)
        if order is None:
            raise InvalidEvent("unknown intent")
        with localcontext() as ctx:
            ctx.prec = 64
            money = self.config.cash_rules(order.intent.instrument.currency)
            fee = money.settle(price*quantity*self.config.fee_rate)
        fill = SimulatedFill(execution_id, intent_id, quantity, price, fee, at)
        self._emit(FillRecorded(fill), at, "fill:"+execution_id)

    def _force_halt(self, reason: str) -> None:
        self.state = replace(self.state, status=TradingStatus.HALTED)
        self._halt_reason = reason
        if self.journal is not None:
            with suppress(Exception):
                self.journal.record_halt(reason)

    def resume_after_review(self, *, reviewed: bool = False) -> None:
        if not reviewed:
            raise PermissionError("operator review required")
        if self.journal is not None:
            self.journal.clear_halt()
        self._halt_reason = None
        self.state = replace(self.state, status=TradingStatus.RUNNING)

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason
