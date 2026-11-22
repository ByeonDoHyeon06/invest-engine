"""Offline shared-account replay for trusted portfolio strategies.

This module coordinates existing E2 observation, E4 allocation and E3
simulated trading components.  It has no broker, network or live-order path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from invest_engine.core.replay import canonical_bytes
from invest_engine.core.runtime import EventRuntime, RuntimeConfig
from invest_engine.data.calendar import SessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, Money
from invest_engine.research.fills import BarFillPolicy, eligible_fill
from invest_engine.research.portfolio_report import (
    PortfolioBacktestReport,
    PortfolioExecutionRecord,
    PortfolioSessionWindow,
    UniverseDecisionRecord,
    summarize_portfolio_executions,
)
from invest_engine.research.report import (
    BacktestReport,
    DecisionRecord,
    EquityPoint,
    FillTrace,
    drawdown,
    sha256,
)
from invest_engine.strategies.allocation import (
    AllocationPlan,
    AllocationPolicy,
    allocate_targets,
    propose_simulated_intents,
)
from invest_engine.strategies.attribution import (
    AttributionTicket,
    VirtualLedger,
    audit_virtual_against_account,
    record_simulated_fill,
    ticket_for_plan,
)
from invest_engine.strategies.contracts import SignalDirection, StrategySignal
from invest_engine.strategies.portfolio_contracts import (
    PortfolioStrategy,
    UniverseFrameStatus,
)
from invest_engine.strategies.portfolio_runtime import PortfolioStrategyRunner
from invest_engine.strategies.universe import UniverseFrameCoordinator
from invest_engine.trading.models import (
    DecisionStatus,
    OrderStatus,
    SellSettlementMode,
    Side,
    TradingConfig,
)
from invest_engine.trading.monitoring import (
    MarketMark,
    MonitorInput,
    MonitorResult,
    SessionBaseline,
)
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.runtime import TradingRuntime


_ONE_MINUTE = timedelta(minutes=1)
_TERMINAL_ORDER_STATUSES = frozenset(
    {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}
)


@dataclass(frozen=True, slots=True)
class PortfolioBacktestSettings:
    run_version: str = "e6-portfolio-shared-account-v1"
    max_history_bars: int = 500_000
    code_sha: str = "UNPINNED"
    dataset_source: str = "caller-supplied"
    data_license: str = "caller-responsible"

    def __post_init__(self) -> None:
        if not isinstance(self.run_version, str) or not self.run_version.strip():
            raise ValueError("portfolio run version is required")
        if type(self.max_history_bars) is not int or self.max_history_bars < 1:
            raise ValueError("portfolio history capacity must be positive")
        identifiers = (self.code_sha, self.dataset_source, self.data_license)
        if not all(isinstance(value, str) and value.strip() for value in identifiers):
            raise ValueError("portfolio provenance identifiers are required")


@dataclass(slots=True)
class _DecisionBuilder:
    as_of: datetime
    status: UniverseFrameStatus
    frame_id: str | None = None
    missing_instrument_keys: tuple[str, ...] = ()
    selected_instrument_keys: tuple[str, ...] = ()
    signal_ids: tuple[str, ...] = ()
    intent_ids: list[str] = field(default_factory=list)
    canceled_intent_ids: list[str] = field(default_factory=list)
    decisions: list[tuple[str, str, tuple[str, ...]]] = field(
        default_factory=list
    )
    fills: list[str] = field(default_factory=list)
    reason_codes: set[str] = field(default_factory=set)

    def freeze(self) -> UniverseDecisionRecord:
        return UniverseDecisionRecord(
            as_of=self.as_of,
            status=self.status,
            frame_id=self.frame_id,
            missing_instrument_keys=self.missing_instrument_keys,
            selected_instrument_keys=self.selected_instrument_keys,
            signal_ids=self.signal_ids,
            intent_ids=tuple(self.intent_ids),
            canceled_intent_ids=tuple(self.canceled_intent_ids),
            decisions=tuple(self.decisions),
            fills=tuple(self.fills),
            reason_codes=tuple(sorted(self.reason_codes)),
        )


@dataclass(slots=True)
class _ReplaySession:
    session_id: str
    start: datetime
    end: datetime
    checkpoints: tuple[datetime, ...]
    baseline: SessionBaseline
    finalized_checkpoints: set[datetime] = field(default_factory=set)
    closed: bool = False

    @property
    def window(self) -> PortfolioSessionWindow:
        return PortfolioSessionWindow(self.session_id, self.start, self.end)


class HistoricalPortfolioBacktest:
    """Single-use, deterministic, USD-only shared-account simulation."""

    def __init__(
        self,
        *,
        calendar: SessionCalendar,
        instruments: tuple[InstrumentId, ...],
        strategy: PortfolioStrategy,
        config: TradingConfig,
        opening_cash: tuple[Money, ...],
        risk: RiskLimits,
        fill_policy: BarFillPolicy | None = None,
        allocation_policy: AllocationPolicy | None = None,
        settings: PortfolioBacktestSettings | None = None,
    ) -> None:
        if not isinstance(instruments, tuple) or len(instruments) < 2:
            raise ValueError("portfolio backtest requires at least two instruments")
        ordered = tuple(sorted(instruments, key=lambda item: item.key))
        if len({item.key for item in ordered}) != len(ordered):
            raise ValueError("portfolio instruments must be unique")
        if any(item.currency != "USD" for item in ordered):
            raise ValueError("portfolio backtest v1 accepts only USD instruments")
        if len({item.market for item in ordered}) != 1:
            raise ValueError("portfolio instruments must share one market")
        if config.sell_settlement_mode is not SellSettlementMode.IMMEDIATE:
            raise ValueError("portfolio backtest requires IMMEDIATE settlement")
        if not isinstance(risk, RiskLimits) or not risk.require_monitoring:
            raise ValueError("portfolio backtest requires monitored E3 risk")
        if risk.require_account_reference:
            raise ValueError("offline portfolio replay cannot attest a broker account")
        if not isinstance(opening_cash, tuple) or not opening_cash:
            raise ValueError("portfolio opening cash must be a nonempty tuple")
        if len({item.currency for item in opening_cash}) != len(opening_cash):
            raise ValueError("duplicate portfolio opening cash currency")
        if tuple(item.currency for item in opening_cash) != ("USD",):
            raise ValueError("portfolio backtest v1 requires one USD cash balance")
        if opening_cash[0].amount <= 0:
            raise ValueError("portfolio opening USD cash must be positive")
        config.cash_rules("USD")
        for instrument in ordered:
            config.rules_for(instrument)
        if strategy.manifest.bar_interval != _ONE_MINUTE:
            raise ValueError("portfolio backtest currently requires one-minute bars")

        self.calendar = calendar
        self.instruments = ordered
        self.strategy = strategy
        self.config = config
        self.opening_cash = opening_cash
        self.risk = risk
        self.fill_policy = fill_policy or BarFillPolicy()
        self.allocation_policy = allocation_policy or AllocationPolicy()
        self.settings = settings or PortfolioBacktestSettings()
        self._used = False

    def config_digest(self) -> str:
        """Bind all execution policy and strategy-owned initial state."""
        return sha256(
            (
                self.config,
                self.opening_cash,
                self.risk,
                self.fill_policy,
                self.allocation_policy,
                self.settings,
                self.instruments,
                self.strategy.manifest,
                self.strategy.snapshot().hex(),
                getattr(self.calendar, "sessions", None),
            )
        )

    def run(
        self,
        events: tuple[EventEnvelope[MarketPayload], ...],
    ) -> PortfolioBacktestReport:
        if self._used:
            raise RuntimeError("portfolio backtest is single-use; construct a fresh instance")
        self._used = True
        if not isinstance(events, tuple) or not events:
            raise ValueError("historical portfolio events must be a nonempty tuple")
        data_sha = sha256(tuple(canonical_bytes(event).hex() for event in events))
        replay = _PortfolioReplay(self, data_sha, self.config_digest())
        return replay.run(events)


class _PortfolioReplay:
    def __init__(
        self,
        owner: HistoricalPortfolioBacktest,
        data_sha: str,
        config_sha: str,
    ) -> None:
        self.owner = owner
        self.data_sha = data_sha
        self.config_sha = config_sha
        self.observation = EventRuntime(RuntimeConfig(owner.settings.run_version))
        coordinator = UniverseFrameCoordinator(
            owner.calendar,
            owner.instruments,
            bar_interval=owner.strategy.manifest.bar_interval,
            checkpoint_interval=owner.strategy.manifest.checkpoint_interval,
            max_bars=owner.settings.max_history_bars,
        )
        self.runner = PortfolioStrategyRunner(owner.strategy, coordinator)
        self.trader = TradingRuntime(owner.config, owner.opening_cash, owner.risk)
        self.virtual = VirtualLedger()
        self.marks: dict[str, MarketMark] = {}
        self.mark_bar_ends: dict[str, datetime] = {}
        self.sessions: dict[tuple[datetime, datetime], _ReplaySession] = {}
        self.decisions: list[_DecisionBuilder] = []
        self.tickets: dict[str, AttributionTicket] = {}
        self.intent_source: dict[str, _DecisionBuilder] = {}
        self.intent_expiry: dict[str, datetime] = {}
        self.executions: list[PortfolioExecutionRecord] = []
        self.fill_traces: list[FillTrace] = []
        self.equity: list[EquityPoint] = []
        self.realized: dict[str, Decimal] = {}
        self.turnover: dict[str, Decimal] = {}
        self.exit_results: dict[str, list[Decimal]] = {}
        self.entries = 0
        self.exits = 0

    def run(
        self,
        events: tuple[EventEnvelope[MarketPayload], ...],
    ) -> PortfolioBacktestReport:
        for event in events:
            bar, instrument, now, session = self._preflight_event(event)
            key = (session.start, session.end)
            if key not in self.sessions:
                self._finalize_due(now, inclusive=False)
                self._close_due_sessions(now, inclusive=False)
                self._register_session(session)
            self._finalize_due(now, inclusive=False)

            self.observation.accept(event)
            self._cancel_entries_before_bar(event, now)
            self._fill_existing_orders(event, session)
            self._cancel_entries_after_bar(event, now)
            self.marks[instrument.key] = MarketMark(
                instrument,
                bar.close,
                now,
                "e6:portfolio-finalized-bar",
            )
            self.mark_bar_ends[instrument.key] = bar.end
            self.runner.accept(event)
            self.equity.append(self._equity_point(now))

        last_known = self.runner.coordinator.last_known
        if last_known is None:
            raise InvalidEvent("portfolio replay ended without an observed clock")
        self._finalize_due(last_known, inclusive=True)
        self._close_due_sessions(last_known, inclusive=True)
        if any(not session.closed for session in self.sessions.values()):
            raise InvalidEvent("portfolio replay ended before an authoritative session close")
        audit_virtual_against_account(self.virtual, self.trader.state)
        return self._report(events)

    def _preflight_event(
        self,
        event: EventEnvelope[MarketPayload],
    ) -> tuple[Bar, InstrumentId, datetime, TradingSession]:
        if not isinstance(event.payload, Bar):
            raise InvalidEvent("portfolio replay accepts only bars")
        instrument = event.instrument_id
        if instrument is None or instrument not in self.owner.instruments:
            raise InvalidEvent("portfolio event instrument is outside the universe")
        bar = event.payload
        now = max(event.available_at, event.received_at)
        if bar.end > now or event.event_time < bar.end:
            raise InvalidEvent("portfolio bar is not causally available")
        session = self.owner.calendar.session_for(instrument, bar.start)
        if session is None or bar.end > session.end:
            raise InvalidEvent("portfolio bar is outside its authoritative session")
        return bar, instrument, now, session

    def _register_session(self, session: TradingSession) -> None:
        key = (session.start, session.end)
        if key in self.sessions:
            return
        if any(
            position.quantity > 0 or position.reserved_sell > 0
            for position in self.trader.state.positions
        ):
            raise InvalidEvent("new portfolio session requires a flat account")
        if any(
            order.status not in _TERMINAL_ORDER_STATUSES
            for order in self.trader.state.orders
        ):
            raise InvalidEvent("new portfolio session has unresolved orders")
        interval = self.owner.strategy.manifest.checkpoint_interval
        checkpoints: list[datetime] = []
        checkpoint = session.start + interval
        final_checkpoint = session.end - interval
        while checkpoint <= final_checkpoint:
            checkpoints.append(checkpoint)
            checkpoint += interval
        if not checkpoints:
            raise InvalidEvent("portfolio session has no decision checkpoint")
        session_id = f"{session.market.value}:{session.start.date().isoformat()}"
        if any(item.session_id == session_id for item in self.sessions.values()):
            raise InvalidEvent("duplicate portfolio session identity")
        cash = self.trader.state.account("USD")
        opening_equity = cash.settled + cash.unsettled
        self.sessions[key] = _ReplaySession(
            session_id=session_id,
            start=session.start,
            end=session.end,
            checkpoints=tuple(checkpoints),
            baseline=SessionBaseline(
                "USD",
                session_id,
                opening_equity,
                session.start,
            ),
        )

    def _session_for_checkpoint(self, checkpoint: datetime) -> _ReplaySession:
        matches = tuple(
            session
            for session in self.sessions.values()
            if session.start < checkpoint < session.end
        )
        if len(matches) != 1:
            raise InvalidEvent("checkpoint does not map to exactly one session")
        return matches[0]

    def _finalize_due(self, now: datetime, *, inclusive: bool) -> None:
        due = sorted(
            checkpoint
            for session in self.sessions.values()
            for checkpoint in session.checkpoints
            if checkpoint not in session.finalized_checkpoints
            and (checkpoint <= now if inclusive else checkpoint < now)
        )
        for checkpoint in due:
            self._evaluate_checkpoint(checkpoint)
            self._session_for_checkpoint(checkpoint).finalized_checkpoints.add(
                checkpoint
            )

    def _checkpoint_has_current_marks(self, checkpoint: datetime) -> bool:
        return all(
            self.mark_bar_ends.get(instrument.key) == checkpoint
            and self.marks[instrument.key].available_at <= checkpoint
            for instrument in self.owner.instruments
            if instrument.key in self.marks
        ) and len(self.marks) == len(self.owner.instruments)

    def _observe(self, session: _ReplaySession, at: datetime) -> MonitorResult:
        return self.trader.observe_market_and_account(
            MonitorInput(
                checked_at=at,
                session_id=session.session_id,
                base_currency="USD",
                marks=tuple(sorted(self.marks.values(), key=lambda item: item.instrument.key)),
                baselines=(session.baseline,),
            )
        )

    @staticmethod
    def _usd_equity(result: MonitorResult | None) -> Decimal | None:
        if result is None:
            return None
        row = next(
            (item for item in result.valuations if item.currency == "USD"),
            None,
        )
        return row.equity if row is not None else None

    def _evaluate_checkpoint(self, checkpoint: datetime) -> None:
        session = self._session_for_checkpoint(checkpoint)
        unresolved_exits = tuple(
            order
            for order in self.trader.state.orders
            if order.intent.side is Side.SELL
            and order.status not in _TERMINAL_ORDER_STATUSES
            and self.intent_source[order.intent.intent_id].as_of < checkpoint
        )
        if unresolved_exits:
            raise InvalidEvent(
                "portfolio checkpoint has unresolved EXIT order from an older frame"
            )
        self._cancel_replaced_entries(checkpoint)
        monitor = (
            self._observe(session, checkpoint)
            if self._checkpoint_has_current_marks(checkpoint)
            else None
        )
        evaluation = self.runner.evaluate(checkpoint)
        outcome = evaluation.frame_outcome
        builder = _DecisionBuilder(
            checkpoint,
            outcome.status,
            frame_id=outcome.frame.frame_id if outcome.frame is not None else None,
            missing_instrument_keys=outcome.missing_instrument_keys,
            reason_codes=set(outcome.reason_codes) | set(evaluation.reason_codes),
        )
        self.decisions.append(builder)
        if outcome.status is not UniverseFrameStatus.COMPLETE:
            return
        if evaluation.batch is None or outcome.frame is None:
            raise InvalidEvent("complete portfolio checkpoint has no strategy batch")
        if monitor is None:
            monitor = self._observe(session, checkpoint)
        builder.reason_codes.update(monitor.reasons)

        signals = evaluation.batch.signals
        builder.signal_ids = tuple(signal.signal_id for signal in signals)
        builder.selected_instrument_keys = tuple(
            signal.instrument.key
            for signal in signals
            if signal.direction is SignalDirection.LONG
        )
        execution_signals = signals
        if session.session_id in self.trader.state.daily_loss_sessions:
            builder.reason_codes.add("DAILY_LOSS_EXIT_OVERRIDE")
            if "DAILY_LOSS_LIMIT" not in monitor.reasons:
                builder.reason_codes.add("DAILY_LOSS_LATCHED")
            execution_signals = tuple(
                StrategySignal(
                    signal_id=(
                        "risk:daily-loss:"
                        + outcome.frame.frame_id
                        + ":"
                        + instrument.key
                    ),
                    strategy_id="e6-daily-loss-overlay",
                    strategy_version="1.0.0",
                    instrument=instrument,
                    direction=SignalDirection.EXIT,
                    target_fraction=Decimal(0),
                    generated_at=checkpoint,
                    expires_at=(
                        checkpoint
                        + self.owner.strategy.manifest.checkpoint_interval
                    ),
                    trigger_event_id=trigger.event_id,
                    reason_codes=("DAILY_LOSS_EXIT_OVERRIDE",),
                )
                for instrument, trigger in zip(
                    outcome.frame.instruments,
                    outcome.frame.trigger_bars,
                    strict=True,
                )
            )
        allocated = allocate_targets(
            execution_signals,
            as_of=checkpoint,
            policy=self.owner.allocation_policy,
        )
        builder.reason_codes.update(allocated.reason_codes)
        target_equity = self._usd_equity(monitor) or session.baseline.equity
        proposed = propose_simulated_intents(
            allocated.plans,
            state=self.trader.state,
            config=self.owner.config,
            marks=tuple(sorted(self.marks.values(), key=lambda item: item.instrument.key)),
            as_of=checkpoint,
            max_mark_age=self.owner.risk.mark_max_age,
            target_equity_by_currency=(("USD", target_equity),),
        )
        plans_by_key: dict[str, AllocationPlan] = {
            plan.instrument.key: plan for plan in allocated.plans
        }
        for intent in proposed:
            if intent.side is Side.BUY:
                self._observe(session, checkpoint)
            result = self.trader.submit(intent)
            builder.intent_ids.append(intent.intent_id)
            builder.decisions.append(
                (
                    intent.intent_id,
                    result.decision.decision.value,
                    result.decision.reason_codes,
                )
            )
            if result.decision.decision is not DecisionStatus.APPROVED:
                continue
            plan = plans_by_key[intent.instrument.key]
            self.tickets[intent.intent_id] = ticket_for_plan(plan, intent)
            self.intent_source[intent.intent_id] = builder
            if intent.side is Side.BUY:
                self.intent_expiry[intent.intent_id] = plan.expires_at
            self.trader.accept_simulated(intent.intent_id, checkpoint)

    def _cancel_entry(self, intent_id: str, at: datetime, reason: str) -> None:
        order = self.trader.state.order(intent_id)
        if order is None or order.status not in {
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        }:
            return
        if order.intent.side is not Side.BUY:
            raise InvalidEvent("only a replaceable BUY may use entry cancellation")
        self.trader.request_cancel(intent_id, at)
        self.trader.confirm_cancel(intent_id, at)
        source = self.intent_source.get(intent_id)
        if source is None:
            raise InvalidEvent("entry cancellation has no source decision")
        source.canceled_intent_ids.append(intent_id)
        source.reason_codes.add(reason)

    def _cancel_replaced_entries(self, checkpoint: datetime) -> None:
        replaceable = sorted(
            (
                order
                for order in self.trader.state.orders
                if order.intent.side is Side.BUY
                and order.status
                in {OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED}
                and self.intent_source[order.intent.intent_id].as_of < checkpoint
            ),
            key=lambda item: item.intent.intent_id,
        )
        for order in replaceable:
            self._cancel_entry(
                order.intent.intent_id,
                checkpoint,
                "REPLACED_ENTRY_CANCELED",
            )

    def _cancel_entries_before_bar(
        self,
        event: EventEnvelope[MarketPayload],
        now: datetime,
    ) -> None:
        if not isinstance(event.payload, Bar) or event.instrument_id is None:
            return
        for order in tuple(self.trader.state.orders):
            expiry = self.intent_expiry.get(order.intent.intent_id)
            if (
                expiry is not None
                and order.intent.instrument == event.instrument_id
                and event.payload.start >= expiry
            ):
                at_later_checkpoint = any(
                    event.payload.end in session.checkpoints
                    and self.intent_source[order.intent.intent_id].as_of
                    < event.payload.end
                    for session in self.sessions.values()
                )
                self._cancel_entry(
                    order.intent.intent_id,
                    now,
                    (
                        "REPLACED_ENTRY_CANCELED"
                        if at_later_checkpoint
                        else "ENTRY_EXPIRED"
                    ),
                )

    def _cancel_entries_after_bar(
        self,
        event: EventEnvelope[MarketPayload],
        now: datetime,
    ) -> None:
        if not isinstance(event.payload, Bar) or event.instrument_id is None:
            return
        for order in tuple(self.trader.state.orders):
            expiry = self.intent_expiry.get(order.intent.intent_id)
            if (
                expiry is not None
                and order.intent.instrument == event.instrument_id
                and event.payload.end >= expiry
            ):
                self._cancel_entry(order.intent.intent_id, now, "ENTRY_EXPIRED")

    def _fill_existing_orders(
        self,
        event: EventEnvelope[MarketPayload],
        session: TradingSession,
    ) -> None:
        used_volume = Decimal(0)
        for order in tuple(self.trader.state.orders):
            candidate = eligible_fill(
                order,
                event,
                self.owner.config.rules_for(order.intent.instrument),
                self.owner.fill_policy,
                used_volume=used_volume,
            )
            if candidate is None:
                continue
            before = self.trader.state.position(order.intent.instrument)
            before_quantity = before.quantity if before is not None else Decimal(0)
            before_realized = before.realized_pnl if before is not None else Decimal(0)
            fill_id = f"e6:{event.event_id}:{candidate.intent_id}"
            self.trader.fill_simulated(
                candidate.intent_id,
                price=candidate.price,
                quantity=candidate.quantity,
                execution_id=fill_id,
                at=candidate.observed_at,
            )
            actual = self.trader.state.fills[-1]
            charge = self.trader.state.charges[-1]
            ticket = self.tickets.get(actual.intent_id)
            source = self.intent_source.get(actual.intent_id)
            if ticket is None or source is None or source.frame_id is None:
                raise InvalidEvent("portfolio fill has no approved frame attribution")
            self.virtual = record_simulated_fill(self.virtual, ticket, actual)
            after = self.trader.state.position(order.intent.instrument)
            after_quantity = after.quantity if after is not None else Decimal(0)
            after_realized = after.realized_pnl if after is not None else Decimal(0)
            realized_delta = after_realized - before_realized
            session_state = self.sessions[(session.start, session.end)]
            self.executions.append(
                PortfolioExecutionRecord(
                    execution_id=fill_id,
                    intent_id=actual.intent_id,
                    source_frame_id=source.frame_id,
                    market_event_id=event.event_id,
                    instrument=order.intent.instrument,
                    side=order.intent.side,
                    quantity=actual.quantity,
                    price=actual.price,
                    fee=actual.fee,
                    tax=charge.tax,
                    realized_pnl=realized_delta,
                    occurred_at=actual.occurred_at,
                    position_before=before_quantity,
                    position_after=after_quantity,
                    session_id=session_state.session_id,
                )
            )
            self.fill_traces.append(
                FillTrace(
                    fill_id,
                    actual.intent_id,
                    event.event_id,
                    order.intent.side.value,
                    actual.quantity,
                    actual.price,
                    actual.fee,
                    charge.tax,
                    realized_delta,
                )
            )
            source.fills.append(fill_id)
            used_volume += actual.quantity
            currency = order.intent.instrument.currency
            self.turnover[currency] = (
                self.turnover.get(currency, Decimal(0)) + charge.gross
            )
            if order.intent.side is Side.BUY:
                self.entries += 1
            else:
                self.exits += 1
                self.realized[currency] = (
                    self.realized.get(currency, Decimal(0)) + realized_delta
                )
                self.exit_results.setdefault(currency, []).append(realized_delta)

    def _equity_point(self, now: datetime) -> EquityPoint:
        values = {
            cash.currency: cash.settled + cash.unsettled
            for cash in self.trader.state.cash
        }
        complete = True
        for position in self.trader.state.positions:
            if position.quantity <= 0:
                continue
            mark = self.marks.get(position.instrument.key)
            if (
                mark is None
                or mark.available_at > now
                or now - mark.available_at > self.owner.risk.mark_max_age
            ):
                complete = False
                continue
            values[position.instrument.currency] = (
                values.get(position.instrument.currency, Decimal(0))
                + position.quantity * mark.price
            )
        return EquityPoint(
            now,
            tuple(sorted(values.items())) if complete else (),
            complete,
        )

    def _close_due_sessions(self, now: datetime, *, inclusive: bool) -> None:
        due = sorted(
            (
                session
                for session in self.sessions.values()
                if not session.closed
                and (session.end <= now if inclusive else session.end < now)
            ),
            key=lambda item: item.start,
        )
        for session in due:
            if set(session.checkpoints) != session.finalized_checkpoints:
                raise InvalidEvent("session closed before all checkpoints were finalized")
            if any(
                order.status not in _TERMINAL_ORDER_STATUSES
                for order in self.trader.state.orders
            ):
                raise InvalidEvent("portfolio session ended with unresolved orders")
            if any(
                position.quantity > 0 or position.reserved_sell > 0
                for position in self.trader.state.positions
            ):
                raise InvalidEvent("portfolio session ended with final inventory")
            session.closed = True

    def _report(
        self,
        events: tuple[EventEnvelope[MarketPayload], ...],
    ) -> PortfolioBacktestReport:
        if not self.equity:
            raise InvalidEvent("portfolio replay has no equity observations")
        final_point = self.equity[-1]
        if not final_point.complete:
            raise InvalidEvent("portfolio replay ended without complete valuation")
        frozen_decisions = tuple(builder.freeze() for builder in self.decisions)
        account_decisions = tuple(
            DecisionRecord(
                event_id=(
                    decision.frame_id
                    or "portfolio-checkpoint:" + decision.as_of.isoformat()
                ),
                signal_ids=decision.signal_ids,
                intent_ids=decision.intent_ids,
                decisions=decision.decisions,
                fills=decision.fills,
                reason_codes=decision.reason_codes,
            )
            for decision in frozen_decisions
        )
        start = tuple(
            sorted((money.currency, money.amount) for money in self.owner.opening_cash)
        )
        fees: dict[str, Decimal] = {}
        taxes: dict[str, Decimal] = {}
        for charge in self.trader.state.charges:
            fees[charge.currency] = fees.get(charge.currency, Decimal(0)) + charge.fee
            taxes[charge.currency] = taxes.get(charge.currency, Decimal(0)) + charge.tax
        drawdowns = tuple(
            (currency, drawdown(tuple(self.equity), currency))
            for currency, _ in start
        )
        account_run_sha = sha256(
            (
                self.data_sha,
                self.config_sha,
                self.observation.state.digest,
                self.trader.state.digest,
                account_decisions,
                self.equity,
                self.fill_traces,
            )
        )
        net = tuple(
            (currency, dict(final_point.by_currency)[currency] - opening)
            for currency, opening in start
        )
        factors: list[tuple[str, Decimal | None]] = []
        expectations: list[tuple[str, Decimal | None]] = []
        for currency, _ in start:
            values = self.exit_results.get(currency, [])
            wins = sum((value for value in values if value > 0), Decimal(0))
            losses = sum((-value for value in values if value < 0), Decimal(0))
            factors.append((currency, wins / losses if losses else None))
            expectations.append(
                (
                    currency,
                    sum(values, Decimal(0)) / len(values) if values else None,
                )
            )
        account = BacktestReport(
            dataset_sha256=self.data_sha,
            config_sha256=self.config_sha,
            state_digest=self.trader.state.digest,
            run_sha256=account_run_sha,
            event_count=len(events),
            by_currency_start=start,
            by_currency_end=final_point.by_currency,
            max_drawdown=drawdowns,
            entry_fill_count=self.entries,
            exit_fill_count=self.exits,
            total_fees=tuple(sorted(fees.items())),
            total_taxes=tuple(sorted(taxes.items())),
            realized_exit_pnl=tuple(sorted(self.realized.items())),
            equity=tuple(self.equity),
            decisions=account_decisions,
            fills=tuple(self.fill_traces),
            net_pnl=net,
            turnover=tuple(sorted(self.turnover.items())),
            profit_factor=tuple(factors),
            exit_fill_expectancy=tuple(expectations),
            notes=(
                "Offline shared-account portfolio research; no broker connection.",
                "Bar penetration and volume assumptions do not certify execution.",
                "USD-only v1; monitoring is synthetic and caller-supplied.",
            ),
        )
        windows = tuple(
            session.window
            for session in sorted(self.sessions.values(), key=lambda item: item.start)
        )
        execution_summary = summarize_portfolio_executions(
            tuple(self.executions),
            windows,
        )
        blocked = sum(
            decision.status is UniverseFrameStatus.DATA_UNAVAILABLE
            for decision in frozen_decisions
        )
        portfolio_run_sha = sha256(
            (
                account.run_sha256,
                frozen_decisions,
                self.executions,
                execution_summary,
                blocked,
            )
        )
        return PortfolioBacktestReport(
            account_report=account,
            universe_decisions=frozen_decisions,
            executions=tuple(self.executions),
            cycles=execution_summary.cycles,
            sessions=execution_summary.sessions,
            symbols=execution_summary.symbols,
            largest_positive_symbol_pnl_share=(
                execution_summary.largest_positive_symbol_pnl_share
            ),
            blocked_checkpoint_count=blocked,
            run_sha256=portfolio_run_sha,
            notes=(
                "Shared account and virtual attribution reconciled at finalization.",
                "LIVE and Paper trading remain unauthorized.",
            ),
        )
