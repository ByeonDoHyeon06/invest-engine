"""E3 purely simulated trading runtime; no real order transport by design."""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal

from invest_engine.domain.errors import InvalidEvent
from invest_engine.trading.actions import (
    DelistingObserved, DelistingCashResolved, DividendEntitled, DividendPaymentConfirmed, SplitApplied, action_fingerprint,
)
from invest_engine.domain.primitives import InstrumentId, Money, _decimal, utc_datetime
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.monitoring import MonitorInput, MonitorResult
from invest_engine.trading.ledger import (
    AccountReconciliationReviewed, CashSettlementConfirmed, EntriesPaused, EntriesResumed, FillRecorded, OrderAccepted, OrderCanceled, OrderCancelPending,
    OrderReconciled, OrderRejected, OrderReserved, OrderUnknown, RiskObserved,
    TradingEvent, TradingPayload, TradingStatus, exposure_for, initial_trading_state,
    reduce_trade_event,
)
from invest_engine.trading.models import (
    DecisionStatus, OrderIntent, OrderStatus, RiskDecision, Side, SimulatedFill, TradingConfig,
)
from invest_engine.trading.policy import Exposure, RiskLimits, evaluate_order


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
            proposed = reduce_trade_event(self.state, event, self.config, self.limits)
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

    def apply_split(self, action: SplitApplied, at: datetime) -> bool:
        """Explicit synthetic event only; no provider inference or order repricing."""
        if action.action_id in self.state.applied_corporate_ids:
            previous = dict(self.state.corporate_fingerprints)[action.action_id]
            if previous != action_fingerprint(action):
                self._force_halt("conflicting corporate action identity")
                raise InvalidEvent("conflicting repeated corporate action")
            return False
        self._emit(action, at, "corporate:split:" + action.action_id)
        return True

    def record_dividend(self, action: DividendEntitled, at: datetime) -> bool:
        if action.action_id in self.state.applied_corporate_ids:
            previous = dict(self.state.corporate_fingerprints)[action.action_id]
            if previous != action_fingerprint(action):
                self._force_halt("conflicting corporate action identity")
                raise InvalidEvent("conflicting repeated corporate action")
            return False
        self._emit(action, at, "corporate:dividend:" + action.action_id)
        return True

    def confirm_dividend_payment(self, action_id: str, at: datetime) -> bool:
        if action_id in self.state.paid_dividend_ids:
            return False
        self._emit(DividendPaymentConfirmed(action_id), at,
                   "corporate:dividend-paid:" + action_id)
        return True

    def flag_delisting(self, action: DelistingObserved, at: datetime) -> bool:
        if action.action_id in self.state.applied_corporate_ids:
            previous = dict(self.state.corporate_fingerprints)[action.action_id]
            if previous != action_fingerprint(action):
                self._force_halt("conflicting corporate action identity")
                raise InvalidEvent("conflicting repeated corporate action")
            return False
        self._emit(action, at, "corporate:delist:" + action.action_id)
        return True

    def resolve_delisted_cash(self, resolution: DelistingCashResolved, at: datetime) -> bool:
        """Persist independently declared net cash recovery; no synthetic price."""
        if any(row.action_id == resolution.action_id
               for row in self.state.delisting_resolutions):
            previous = next(row for row in self.state.delisting_resolutions
                            if row.action_id == resolution.action_id)
            if previous.terms_sha256 != action_fingerprint(resolution):
                self._force_halt("conflicting terminal settlement")
                raise InvalidEvent("conflicting terminal settlement")
            return False
        self._emit(resolution, at, "corporate:delisting-recovery:" + resolution.action_id)
        return True

    def confirm_cash_settlement(self, execution_id: str, at: datetime) -> bool:
        """Confirm a synthetic SELL receivable; never infer broker settlement.

        Duplicate confirmations are idempotent. A nonexistent execution HALTs
        the simulation rather than manufacturing cash.
        """
        if self.state.status is TradingStatus.HALTED:
            raise InvalidEvent("runtime halted")
        if execution_id in self.state.settled_execution_ids:
            return False
        pending = next(
            (p for p in self.state.pending_settlements if p.execution_id == execution_id),
            None,
        )
        if pending is None or utc_datetime(at) < pending.occurred_at:
            self._force_halt("unknown or prematurely settled execution")
            raise InvalidEvent("no eligible pending settlement")
        self._emit(CashSettlementConfirmed(execution_id), at, "settle:" + execution_id)
        return True

    def observe_market_and_account(self, snapshot: MonitorInput) -> MonitorResult:
        """Persist exactly the observations used for valuation/reconciliation.

        No market feed or broker is queried; the caller owns input provenance.
        """
        self._emit(RiskObserved(snapshot), snapshot.checked_at,
                   "risk-observation:" + str(self.state.last_ordinal + 1))
        result = self.state.monitoring
        if result is None:
            raise InvalidEvent("monitoring result was not applied")
        return result

    def review_reconciliation_hold(self, *, reviewed_by: str, at: datetime) -> None:
        """Explicit operator review after a verified healthy reconciliation."""
        if not reviewed_by.strip():
            raise PermissionError("reviewer identity required")
        self._emit(AccountReconciliationReviewed(reviewed_by), at,
                   "reconciliation-review:" + str(self.state.last_ordinal + 1))

    def _monitor_buy_reasons(self, intent: OrderIntent) -> tuple[str, ...]:
        if not self.limits.require_monitoring or intent.side is Side.SELL:
            return ()
        result = self.state.monitoring
        if result is None:
            return ("MARK_MONITORING_REQUIRED",)
        if result.session_id in self.state.daily_loss_sessions:
            return ("DAILY_LOSS_LATCHED",)
        if self.state.reconciliation_hold:
            return ("ACCOUNT_RECONCILIATION_REVIEW_REQUIRED",)
        if result.reasons:
            return result.reasons
        if result.preceding_ordinal + 1 != self.state.last_ordinal:
            return ("MARK_RECHECK_AFTER_STATE_CHANGE",)
        if (intent.submitted_at < result.checked_at
            or intent.submitted_at - result.checked_at > self.limits.mark_max_age):
            return ("MONITOR_CHECK_STALE",)
        quote = next((v for v in result.marks if v.instrument.key == intent.instrument.key), None)
        if quote is None:
            return ("ENTRY_MARK_MISSING",)
        if (quote.available_at > intent.submitted_at
            or intent.submitted_at - quote.available_at > self.limits.mark_max_age):
            return ("ENTRY_MARK_STALE",)
        return ()

    def _marked_exposure(self, intent: OrderIntent) -> Exposure:
        """Use current marked equity and exposure rather than acquisition cost."""
        old = exposure_for(self.state, intent.instrument.currency, intent.instrument)
        result = self.state.monitoring
        if intent.side is Side.SELL or not self.limits.require_monitoring or result is None:
            return old
        by_key = {m.instrument.key: m.price for m in result.marks}
        held_value = sum(
            (p.quantity * by_key[p.instrument.key] for p in self.state.positions
             if p.instrument.currency == intent.instrument.currency and p.quantity > 0),
            Decimal(0),
        )
        symbol_marked = sum(
            (p.quantity * by_key[p.instrument.key] for p in self.state.positions
             if p.instrument.key == intent.instrument.key and p.quantity > 0), Decimal(0),
        )
        existing_held_cost = sum(
            (p.quantity * p.average_cost for p in self.state.positions
             if p.instrument.currency == intent.instrument.currency), Decimal(0),
        )
        symbol_held_cost = sum(
            (p.quantity * p.average_cost for p in self.state.positions
             if p.instrument.key == intent.instrument.key), Decimal(0),
        )
        return replace(old,
            equity_at_cost=old.cash + held_value,
            total_cost=old.total_cost - existing_held_cost + held_value,
            symbol_cost=old.symbol_cost - symbol_held_cost + symbol_marked,
        )

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
        monitor_reasons = self._monitor_buy_reasons(intent)
        if monitor_reasons:
            decision = RiskDecision(intent.intent_id, DecisionStatus.REJECTED,
                                    reason_codes=monitor_reasons)
        elif self.state.entry_pause_reason is not None and intent.side is Side.BUY:
            decision = RiskDecision(
                intent.intent_id, DecisionStatus.REJECTED, reason_codes=("NEW_ENTRIES_PAUSED",)
            )
        elif intent.instrument.key in self.state.delisted_instruments:
            decision = RiskDecision(intent.intent_id, DecisionStatus.REJECTED,
                                    reason_codes=("INSTRUMENT_DELISTED",))
        elif intent.account_id != self.config.account_id:
            decision = RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("ACCOUNT_MISMATCH",))
        else:
            try:
                exposure = self._marked_exposure(intent)
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
        prior = (tuple(f for f in self.state.fills if f.intent_id == intent_id)
                 if self.config.requires_order_fill_history else ())
        try:
            fee, _ = self.config.fill_cost(order.intent, price, quantity, at, prior)
        except ValueError as exc:
            self._force_halt(str(exc))
            raise InvalidEvent("cannot price simulated execution") from exc
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
