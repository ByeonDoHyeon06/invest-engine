"""Offline E2→E4→E3 backtest integration. No live broker or external I/O.

Signals created on a finalized bar can only fill in a *later* bar that started
on/after the signal observation. A conservative limit penetration/volume model
is explicit, not evidence that the historical order really would have filled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from invest_engine.core.replay import canonical_bytes
from invest_engine.research.corporate_replay import SplitSchedule
from invest_engine.research.dividend_replay import DividendSchedule
from invest_engine.research.delisting_replay import DelistingSchedule
from invest_engine.core.runtime import EventRuntime, RuntimeConfig
from invest_engine.data.calendar import SessionCalendar
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Money
from invest_engine.research.evaluation import EvaluationWindow, validate_window
from invest_engine.research.fills import BarFillPolicy, eligible_fill
from invest_engine.research.fx import FxReportingPolicy, FxSeries, base_drawdown
from invest_engine.research.protection import (
    ProtectionLot, ProtectionPolicy, consume_oldest, consume_protection,
    new_protected_lot, protective_exit,
)
from invest_engine.research.report import (
    BacktestReport, DecisionRecord, EquityPoint, FillTrace, drawdown, sha256,
)
from invest_engine.strategies.allocation import (
    AllocationPolicy, allocate_targets, propose_simulated_intents,
)
from invest_engine.strategies.attribution import (
    AttributionTicket, VirtualLedger, audit_virtual_against_account,
    record_simulated_fill, ticket_for_plan, rebase_virtual_for_split,
    resolve_virtual_delisting,
)
from invest_engine.strategies.contracts import SignalDirection, Strategy
from invest_engine.strategies.runtime import StrategyRunner
from invest_engine.trading.ledger import TradingState
from invest_engine.trading.models import (
    DecisionStatus, OrderIntent, OrderStatus, SellSettlementMode, Side, TradingConfig,
)
from invest_engine.trading.monitoring import MarketMark
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.runtime import TradingRuntime


@dataclass(frozen=True, slots=True)
class BacktestSettings:
    run_version: str = "e5-research-v1"
    max_mark_age: timedelta = timedelta(minutes=5)
    max_strategy_bars: int = 50000
    code_sha: str = "UNPINNED"
    dataset_source: str = "caller-supplied"
    data_license: str = "caller-responsible"

    def __post_init__(self) -> None:
        if not self.run_version.strip() or self.max_mark_age < timedelta(0):
            raise ValueError("invalid research settings")
        if self.max_strategy_bars < 1:
            raise ValueError("strategy history capacity must be positive")
        if not all((self.code_sha.strip(), self.dataset_source.strip(), self.data_license.strip())):
            raise ValueError("provenance and code revision identifiers are required")


def _equity(state: TradingState, marks: dict[str, MarketMark], now: datetime,
            max_age: timedelta) -> EquityPoint:
    """No invented last price or FX. Incomplete valuation is not reported as zero."""
    cash = {c.currency: c.settled+c.unsettled for c in state.cash}
    # Dividend entitlements are assets, not settled cash / buying power.
    # Including net receivables prevents an artificial equity drop before pay date.
    for receivable in state.dividend_receivables:
        cash[receivable.currency] = cash.get(receivable.currency, Decimal(0)) + receivable.net
    complete = True
    for position in state.positions:
        if position.quantity <= 0:
            continue
        mark = marks.get(position.instrument.key)
        if (mark is None or mark.available_at > now
            or now - mark.available_at > max_age):
            complete = False
            continue
        currency = position.instrument.currency
        cash[currency] = cash.get(currency, Decimal(0)) + position.quantity * mark.price
    return EquityPoint(now, tuple(sorted(cash.items())) if complete else (), complete)


class HistoricalBacktest:
    """Single-use deterministic simulation coordinator.

    All input is caller-supplied, historically ordered, finalized market events.
    A fresh instance of each strategy is required per independent run.
    E4 stops remain plans unless the explicitly opt-in offline protection
    simulator is enabled. No real protective orders are ever sent.
    """

    def __init__(
        self, *, calendar: SessionCalendar, strategies: tuple[Strategy, ...],
        config: TradingConfig, opening_cash: tuple[Money, ...],
        risk: RiskLimits | None = None,
        fill_policy: BarFillPolicy | None = None,
        protection_policy: ProtectionPolicy | None = None,
        allocation_policy: AllocationPolicy | None = None,
        settings: BacktestSettings | None = None,
        fx_series: FxSeries | None = None, fx_policy: FxReportingPolicy | None = None,
        split_schedule: SplitSchedule | None = None,
        dividend_schedule: DividendSchedule | None = None,
        delisting_schedule: DelistingSchedule | None = None,
        evaluation_window: EvaluationWindow | None = None,
        first_entry_only: bool = False,
    ) -> None:
        if not strategies or len({s.manifest.strategy_id for s in strategies}) != len(strategies):
            raise ValueError("at least one uniquely named strategy required")
        if config.sell_settlement_mode is not SellSettlementMode.IMMEDIATE:
            raise ValueError("E5 historical simulator has no settlement calendar; choose IMMEDIATE")
        self.calendar = calendar
        self.strategies = strategies
        self.config = config
        self.opening_cash = opening_cash
        self.risk = risk if risk is not None else RiskLimits()
        if self.risk.require_monitoring:
            raise ValueError("E5 does not yet supply the E3 monitored risk snapshot")
        self.fill_policy = fill_policy if fill_policy is not None else BarFillPolicy()
        self.protection_policy = (protection_policy if protection_policy is not None
                                  else ProtectionPolicy())
        self.allocation_policy = allocation_policy if allocation_policy is not None else AllocationPolicy()
        self.settings = settings if settings is not None else BacktestSettings()
        if (fx_series is None) != (fx_policy is None):
            raise ValueError("FX data and reporting policy must be explicitly supplied together")
        self.fx_series = fx_series
        self.fx_policy = fx_policy
        self.split_schedule = split_schedule if split_schedule is not None else SplitSchedule()
        self.dividend_schedule = (dividend_schedule if dividend_schedule is not None
                                  else DividendSchedule())
        self.delisting_schedule = (delisting_schedule if delisting_schedule is not None
                                   else DelistingSchedule())
        if self.split_schedule.splits and self.protection_policy.enabled:
            raise ValueError("PROTECTIVE_LOTS_NOT_SPLIT_ADJUSTED")
        self.evaluation_window = evaluation_window
        if type(first_entry_only) is not bool:
            raise ValueError("first_entry_only must be boolean")
        if first_entry_only and (evaluation_window is None or len(strategies) != 1):
            raise ValueError("FIRST_ENTRY_ONLY_REQUIRES_SINGLE_STRATEGY_FIXED_WINDOW")
        # Buy-and-hold is not a rebalancing strategy. Once any BUY fills, keep
        # existing DAY-order lifecycle but suppress subsequent new LONG targets.
        self.first_entry_only = first_entry_only
        if evaluation_window is not None and (self.split_schedule.splits
                or self.dividend_schedule.entitlements or self.dividend_schedule.payments
                or self.delisting_schedule.delistings):
            raise ValueError("EVALUATION_WINDOW_REQUIRES_NO_ACTION_INTERVAL")
        self._used = False

    def run(self, events: tuple[EventEnvelope[MarketPayload], ...]) -> BacktestReport:
        if self._used:
            raise RuntimeError("backtest instance is single-use; construct fresh strategies")
        self._used = True
        if not events:
            raise ValueError("historical market events required")
        coverage = (validate_window(events, self.calendar, self.evaluation_window)
                    if self.evaluation_window is not None else None)
        if coverage is not None and self.settings.max_strategy_bars < len(events):
            raise ValueError("EVALUATION_HISTORY_CAPACITY_TOO_SMALL")
        self.split_schedule.preflight(events)
        self.dividend_schedule.preflight(events)
        self.delisting_schedule.preflight(events)
        schedule_by_time = {(s.instrument.key, s.effective_at): s
                            for s in self.split_schedule.splits}
        if len(schedule_by_time) != len(self.split_schedule.splits):
            raise ValueError("multiple splits at same instrument/time unsupported")
        used_splits: set[str] = set()
        entitlements_by_time = {(d.instrument.key, d.effective_at): d
                                for d in self.dividend_schedule.entitlements}
        payments_by_time = {(p.instrument.key, p.paid_at): p
                            for p in self.dividend_schedule.payments}
        used_entitlements: set[str] = set()
        used_payments: set[str] = set()
        delist_by_time = {(d.instrument.key, d.effective_at): d
                          for d in self.delisting_schedule.delistings}
        used_delistings: set[str] = set()
        payout_by_id = {r.action_id: r for r in self.delisting_schedule.resolutions}
        if len(entitlements_by_time) != len(self.dividend_schedule.entitlements):
            raise ValueError("duplicate dividend entitlement boundary")
        if len(payments_by_time) != len(self.dividend_schedule.payments):
            raise ValueError("duplicate dividend payment boundary")
        if (set(delist_by_time) & set(schedule_by_time) or
            set(delist_by_time) & set(entitlements_by_time) or
            set(delist_by_time) & set(payments_by_time)):
            raise ValueError("SIMULTANEOUS_DELISTING_AND_OTHER_ACTION_UNSUPPORTED")
        if set(entitlements_by_time) & set(schedule_by_time):
            raise ValueError("SIMULTANEOUS_SPLIT_AND_DIVIDEND_UNSUPPORTED")
        # Input source/license and calendar are verified by the caller; no network calls.
        data_sha = sha256(tuple(canonical_bytes(e).hex() for e in events))
        identity = (self.config, self.risk, self.fill_policy, self.protection_policy,
                    self.allocation_policy, self.settings,
                    # E4 ORB configuration differs from runtime snapshot; include both.
                    self.fx_policy,
                    self.fx_series.digest if self.fx_series is not None else None,
                    self.split_schedule, self.dividend_schedule,
                    tuple((s.manifest, getattr(s, "params", None), s.snapshot().hex())
                          for s in self.strategies),
                    # StaticSessionCalendar fully serializes; other calendars must pin a version.
                    getattr(self.calendar, "sessions", None))
        # Preserve historical E5.9 config hashes when the new extension is unused.
        config_sha = sha256((*identity, self.delisting_schedule)
                            if self.delisting_schedule.delistings else identity)
        if self.evaluation_window is not None:
            config_sha = sha256((config_sha, self.evaluation_window))
        if self.first_entry_only:
            config_sha = sha256((config_sha, "first-entry-only-v1"))
        observation = EventRuntime(RuntimeConfig(self.settings.run_version))
        runners = tuple(StrategyRunner(s, self.calendar, max_bars=self.settings.max_strategy_bars)
                        for s in self.strategies)
        trader = TradingRuntime(self.config, self.opening_cash, self.risk)
        tickets: dict[str, AttributionTicket] = {}
        virtual = VirtualLedger()
        marks: dict[str, MarketMark] = {}
        decisions: list[DecisionRecord] = []
        equity: list[EquityPoint] = []
        realized: dict[str, Decimal] = {}
        exit_results: dict[str, list[Decimal]] = {}
        turnover: dict[str, Decimal] = {}
        fill_trace: list[FillTrace] = []
        protection_lots: tuple[ProtectionLot, ...] = ()
        entries = exits = 0
        for index, event in enumerate(events):
            # E2 strict ordering and quality gating precede every strategy or fill.
            observation.accept(event)
            if coverage is not None and index < coverage.warmup_bars:
                for runner in runners:
                    runner.accept(event, evaluate=False)
                decisions.append(DecisionRecord(event.event_id, reason_codes=("WARMUP_ONLY",)))
                continue
            now = max(event.available_at, event.received_at)
            matched_fills: list[str] = []
            protective_intents: list[str] = []
            protective_decisions: list[tuple[str, str, tuple[str, ...]]] = []
            protective_reasons: set[str] = set()
            bar = event.payload if isinstance(event.payload, Bar) else None
            split_reason: tuple[str, ...] = ()
            dividend_reason: tuple[str, ...] = ()
            delisting_reason: tuple[str, ...] = ()
            if bar is not None and event.instrument_id is not None:
                entitled = entitlements_by_time.get((event.instrument_id.key, bar.start))
                if entitled is not None:
                    session = self.calendar.session_for(event.instrument_id, bar.start)
                    if session is None or session.start != entitled.effective_at:
                        raise InvalidEvent("DIVIDEND_REQUIRES_SESSION_OPEN_ENTITLEMENT")
                    trader.record_dividend(entitled, now)
                    used_entitlements.add(entitled.action_id)
                    dividend_reason = ("DIVIDEND_ENTITLED:" + entitled.action_id,)
                payment = payments_by_time.get((event.instrument_id.key, bar.start))
                if payment is not None:
                    if payment.action_id not in used_entitlements:
                        raise InvalidEvent("DIVIDEND_PAYMENT_PRECEDES_ENTITLEMENT")
                    if any(d.action_id == payment.action_id
                           for d in trader.state.dividend_receivables):
                        trader.confirm_dividend_payment(payment.action_id, now)
                        dividend_reason += ("DIVIDEND_PAID:" + payment.action_id,)
                    else:
                        dividend_reason += ("DIVIDEND_NO_HOLDINGS:" + payment.action_id,)
                    used_payments.add(payment.action_id)
                split = schedule_by_time.get((event.instrument_id.key, bar.start))
                if split is not None:
                    session = self.calendar.session_for(event.instrument_id, bar.start)
                    if session is None or session.start != split.effective_at:
                        raise InvalidEvent("SPLIT_REQUIRES_SESSION_OPEN")
                    if split.available_at > split.effective_at:
                        raise InvalidEvent("SPLIT_TERMS_NOT_KNOWN_BEFORE_SESSION_OPEN")
                    trader.apply_split(split, now)
                    virtual = rebase_virtual_for_split(virtual, split)
                    audit_virtual_against_account(virtual, trader.state)
                    marks.pop(event.instrument_id.key, None)
                    for runner in runners:
                        runner.invalidate_instrument_history(event.instrument_id)
                    used_splits.add(split.action_id)
                    split_reason = ("SPLIT_APPLIED:" + split.action_id,)
                if bar.end > now or event.event_time < bar.end:
                    raise InvalidEvent("bar not causally available at replay observation")
                session_check = self.calendar.session_for(event.instrument_id, bar.start)
                if session_check is None or bar.end > session_check.end:
                    raise InvalidEvent("bar outside authoritative historical session")
                # Existing orders are handled BEFORE any strategy sees this bar.
                volume_used = Decimal(0)
                # A position's standing synthetic protection was armed only
                # after an earlier observed fill. No intrabar look-ahead for
                # positions established at the end of this bar.
                if self.protection_policy.enabled:
                    for lot in tuple(protection_lots):
                        rule = self.config.rules_for(lot.instrument)
                        available = bar.volume * self.fill_policy.participation - volume_used
                        candidate_exit = protective_exit(
                            lot, event, rule, self.protection_policy,
                            remaining_volume=max(available, Decimal(0)),
                        )
                        if candidate_exit is None:
                            continue
                        # An existing SELL reservation could already have
                        # executed intrabar. Without quotes there is no
                        # causal resolution; refuse an optimistic simulation.
                        if any(
                            o.intent.instrument == lot.instrument
                            and o.intent.side is Side.SELL
                            and o.status not in (
                                OrderStatus.FILLED, OrderStatus.CANCELED,
                                OrderStatus.REJECTED,
                            )
                            for o in trader.state.orders
                        ):
                            raise InvalidEvent(
                                "unresolvable protective exit vs existing SELL order"
                            )
                        exit_id = f"e5:protect:{event.event_id}:{lot.source_execution_id}"
                        protective_intent = OrderIntent(
                            exit_id, self.config.account_id, "e5:standing-protection",
                            lot.instrument, Side.SELL, candidate_exit.quantity,
                            candidate_exit.price, candidate_exit.observed_at,
                        )
                        approved = trader.submit(protective_intent)
                        if approved.decision.decision is not DecisionStatus.APPROVED:
                            raise InvalidEvent("synthetic protection denied by risk")
                        protective_intents.append(exit_id)
                        protective_decisions.append((
                            exit_id, DecisionStatus.APPROVED.value,
                            (candidate_exit.reason_code,),
                        ))
                        protective_reasons.add(candidate_exit.reason_code)
                        trader.accept_simulated(exit_id, candidate_exit.observed_at)
                        existing = trader.state.position(lot.instrument)
                        old_realized = existing.realized_pnl if existing else Decimal(0)
                        trader.fill_simulated(
                            exit_id, price=candidate_exit.price,
                            quantity=candidate_exit.quantity,
                            execution_id=exit_id, at=candidate_exit.observed_at,
                        )
                        filled = trader.state.fills[-1]
                        ticket = AttributionTicket(exit_id, lot.instrument, Side.SELL,
                                                   filled.quantity)
                        virtual = record_simulated_fill(virtual, ticket, filled)
                        protection_lots = consume_protection(
                            protection_lots, lot.source_execution_id, filled.quantity,
                        )
                        current = trader.state.position(lot.instrument)
                        realized_delta = (current.realized_pnl if current else Decimal(0)) - old_realized
                        currency = lot.instrument.currency
                        realized[currency] = realized.get(currency, Decimal(0)) + realized_delta
                        exit_results.setdefault(currency, []).append(realized_delta)
                        charge = trader.state.charges[-1]
                        turnover[currency] = turnover.get(currency, Decimal(0)) + charge.gross
                        exits += 1
                        volume_used += filled.quantity
                        fill_trace.append(FillTrace(
                            exit_id, exit_id, event.event_id, Side.SELL.value,
                            filled.quantity, filled.price, filled.fee, charge.tax,
                            realized_delta, candidate_exit.reason_code,
                        ))
                        matched_fills.append(exit_id)
                for order in tuple(trader.state.orders):
                    rule = self.config.rules_for(order.intent.instrument)
                    candidate = eligible_fill(order, event, rule, self.fill_policy,
                                              used_volume=volume_used)
                    if candidate is None:
                        continue
                    fill_id = f"e5:{event.event_id}:{candidate.intent_id}"
                    before = trader.state.position(order.intent.instrument)
                    old_realized = before.realized_pnl if before else Decimal(0)
                    trader.fill_simulated(candidate.intent_id, price=candidate.price,
                                          quantity=candidate.quantity,
                                          execution_id=fill_id, at=candidate.observed_at)
                    actual = trader.state.fills[-1]
                    volume_used += actual.quantity
                    if actual.intent_id in tickets:
                        virtual = record_simulated_fill(virtual, tickets[actual.intent_id], actual)
                    if order.intent.side is Side.BUY:
                        entries += 1
                        if self.protection_policy.enabled:
                            stop = order.intent.stop_price
                            if stop is None:
                                raise InvalidEvent("protected research requires explicit stop")
                            protection_lots += (new_protected_lot(
                                order.intent.instrument, source_execution_id=fill_id,
                                quantity=actual.quantity, entry_price=actual.price,
                                stop_price=stop, armed_at=candidate.observed_at,
                                policy=self.protection_policy,
                            ),)
                    else:
                        if self.protection_policy.enabled:
                            protection_lots = consume_oldest(
                                protection_lots, order.intent.instrument, actual.quantity,
                            )
                        exits += 1
                        after = trader.state.position(order.intent.instrument)
                        value = (after.realized_pnl if after else Decimal(0)) - old_realized
                        currency = order.intent.instrument.currency
                        realized[currency] = realized.get(currency, Decimal(0)) + value
                    charge = trader.state.charges[-1]
                    currency = order.intent.instrument.currency
                    turnover[currency] = turnover.get(currency, Decimal(0)) + charge.gross
                    realized_delta = Decimal(0)
                    if order.intent.side is Side.SELL:
                        realized_delta = value
                        exit_results.setdefault(currency, []).append(realized_delta)
                    fill_trace.append(FillTrace(
                        fill_id, candidate.intent_id, event.event_id, order.intent.side.value,
                        actual.quantity, actual.price, actual.fee, charge.tax, realized_delta,
                    ))
                    matched_fills.append(fill_id)
                marks[event.instrument_id.key] = MarketMark(
                    event.instrument_id, bar.close, now, "e5:historical-finalized-bar")
                # DAY orders must not survive the end of an explicit market session.
                session = self.calendar.session_for(event.instrument_id, bar.start)
                if session is not None and bar.end == session.end:
                    for order in tuple(trader.state.orders):
                        if (order.intent.instrument == event.instrument_id
                            and order.status in (OrderStatus.ACCEPTED,
                                                 OrderStatus.PARTIALLY_FILLED)):
                            trader.request_cancel(order.intent.intent_id, now)
                            trader.confirm_cancel(order.intent.intent_id, now)
            if bar is not None and event.instrument_id is not None:
                delisting = delist_by_time.get((event.instrument_id.key, bar.end))
                if delisting is not None:
                    position = trader.state.position(delisting.instrument)
                    payout = payout_by_id.get(delisting.action_id)
                    if position is not None and position.quantity > 0 and payout is None:
                        raise InvalidEvent("DELISTED_HOLDINGS_REQUIRE_VERIFIED_TERMINAL_SETTLEMENT")
                    if payout is not None and (position is None or position.quantity <= 0):
                        raise InvalidEvent("TERMINAL_SETTLEMENT_REQUIRES_HELD_SHARES")
                    if any(o.intent.instrument.key == delisting.instrument.key
                           and o.status not in {OrderStatus.FILLED, OrderStatus.CANCELED,
                                                OrderStatus.REJECTED}
                           for o in trader.state.orders):
                        raise InvalidEvent("DELISTING_WITH_UNRESOLVED_ORDERS")
                    trader.flag_delisting(delisting, now)
                    if payout is not None:
                        trader.resolve_delisted_cash(payout, now)
                        virtual = resolve_virtual_delisting(virtual, payout)
                        delisting_reason = ("DELISTING_PAID:" + delisting.action_id,)
                    else:
                        delisting_reason = ("DELISTING_BLOCKED:" + delisting.action_id,)
                    used_delistings.add(delisting.action_id)
            outcomes = tuple(runner.accept(event) for runner in runners)
            signals = tuple(signal for outcome in outcomes for signal in outcome.signals
                            if signal.instrument.key not in trader.state.delisted_instruments)
            allocation_signals = signals
            if self.first_entry_only and entries:
                allocation_signals = tuple(s for s in signals if s.direction is not SignalDirection.LONG)
                if len(allocation_signals) != len(signals):
                    protective_reasons.add("FIRST_ENTRY_ALREADY_FILLED")
            allocated = allocate_targets(allocation_signals, as_of=now, policy=self.allocation_policy)
            proposed = propose_simulated_intents(
                allocated.plans, state=trader.state, config=self.config,
                marks=tuple(marks.values()), as_of=now,
                max_mark_age=self.settings.max_mark_age,
            ) if allocated.plans else ()
            decision_items: list[tuple[str, str, tuple[str, ...]]] = list(protective_decisions)
            for intent in proposed:
                result = trader.submit(intent)
                decision_items.append((intent.intent_id, result.decision.decision.value,
                                       result.decision.reason_codes))
                if result.decision.decision is DecisionStatus.APPROVED:
                    plan = next(p for p in allocated.plans
                                if p.instrument.key == intent.instrument.key)
                    tickets[intent.intent_id] = ticket_for_plan(plan, intent)
                    trader.accept_simulated(intent.intent_id, now)
            reason_codes = tuple(sorted({r for outcome in outcomes for r in outcome.reason_codes}
                                        | set(allocated.reason_codes) | protective_reasons
                                        | set(split_reason) | set(dividend_reason)
                                        | set(delisting_reason)))
            decisions.append(DecisionRecord(event.event_id, tuple(s.signal_id for s in signals),
                                            tuple(protective_intents) + tuple(i.intent_id for i in proposed),
                                            tuple(decision_items), tuple(matched_fills),
                                            reason_codes))
            equity.append(_equity(trader.state, marks, now, self.settings.max_mark_age))
        if used_delistings != {d.action_id for d in self.delisting_schedule.delistings}:
            raise InvalidEvent("DELISTING_SCHEDULE_NOT_COMPLETELY_REPLAYED")
        if used_splits != {s.action_id for s in self.split_schedule.splits}:
            raise InvalidEvent("SPLIT_SCHEDULE_NOT_COMPLETELY_REPLAYED")
        if used_entitlements != {d.action_id for d in self.dividend_schedule.entitlements}:
            raise InvalidEvent("DIVIDEND_ENTITLEMENTS_NOT_COMPLETELY_REPLAYED")
        # Future payment dates may be beyond the experiment's last observation;
        # the receivable remains in equity but never enters settled buying power.
        latest = max((e.payload.end for e in events if isinstance(e.payload, Bar)),
                     default=None)
        for payment in self.dividend_schedule.payments:
            if latest is not None and payment.paid_at < latest and payment.action_id not in used_payments:
                raise InvalidEvent("DIVIDEND_PAYMENT_NOT_REPLAYED")
        audit_virtual_against_account(virtual, trader.state)
        point_end = equity[-1]
        if not point_end.complete:
            raise InvalidEvent("backtest ends without market valuation for held positions")
        start = tuple(sorted((m.currency, m.amount) for m in self.opening_cash))
        fees: dict[str, Decimal] = {}
        taxes: dict[str, Decimal] = {}
        for charge in trader.state.charges:
            fees[charge.currency] = fees.get(charge.currency, Decimal(0)) + charge.fee
            taxes[charge.currency] = taxes.get(charge.currency, Decimal(0)) + charge.tax
        dds = tuple((c, drawdown(tuple(equity), c)) for c, _ in start)
        run_sha = sha256((data_sha, config_sha, observation.state.digest,
                          trader.state.digest, decisions, equity, fill_trace))
        net = tuple((c, dict(point_end.by_currency)[c] - opening) for c, opening in start)
        factors: list[tuple[str, Decimal | None]] = []
        expectations: list[tuple[str, Decimal | None]] = []
        for currency, _ in start:
            values = exit_results.get(currency, [])
            gross_win = sum((v for v in values if v > 0), Decimal(0))
            gross_loss = sum((-v for v in values if v < 0), Decimal(0))
            factors.append((currency, gross_win / gross_loss if gross_loss else None))
            expectations.append((currency, sum(values, Decimal(0)) / len(values) if values else None))
        fx_points = tuple(
            self.fx_series.value_at(point, self.fx_policy) for point in equity
        ) if self.fx_series is not None and self.fx_policy is not None else ()
        fx_complete = bool(fx_points) and all(p.complete for p in fx_points)
        fx_net = None
        fx_dd = None
        if fx_complete and self.fx_series is not None and self.fx_policy is not None:
            first = self.fx_series.value_at(
                EquityPoint(equity[0].at, start, True), self.fx_policy,
            )
            if first.complete and first.value is not None:
                assert fx_points[-1].value is not None
                fx_net = fx_points[-1].value - first.value
                fx_dd = base_drawdown(fx_points)
        return BacktestReport(
            data_sha, config_sha, trader.state.digest, run_sha,
            len(events), start, point_end.by_currency, dds,
            entries, exits, tuple(sorted(fees.items())),
            tuple(sorted(taxes.items())), tuple(sorted(realized.items())),
            tuple(equity), tuple(decisions), tuple(fill_trace), net,
            tuple(sorted(turnover.items())), tuple(factors), tuple(expectations),
            ("Offline research; no live order or broker connection.",
             "Limit touches do not guarantee fills; strict penetration/volume assumptions.",
             "Recorded fills occur at bar observation, not historical intrabar timestamps.",
             ("E5.3 opt-in standing stops/targets use stop-first ambiguous-bar and "
              "adverse-gap assumptions; these are synthetic, not broker orders."
              if self.protection_policy.enabled else
              "Stop prices are risk plans; this fill model does not place stops."),
             "Held delistings require declared, paid and witnessed terminal cash recovery "
             "at the last historical bar; delayed payment remains unsupported.",
             "Multi-currency equity is not aggregated without a proven FX series.",
             "Run code SHA, data provider/license identifiers must be independently verified.",
             "FX-adjusted reporting is research-only; no FX buying power/fees or broker conversions.",
             "Dividend entitlement/pay dates are declared, not issuer-verified; net receivables "
             "count in research equity but not settled cash or buying power.",
             "Split-only E5.8 requires independently sourced raw unadjusted bars; "
             "pre-split feature history is invalidated and unsupported actions are rejected."
             "Incomplete FX observations suppress base-currency PnL and drawdown."
             if self.fx_policy is not None else "No verified FX series; multi-currency totals are separate."),
            fx_base_currency=self.fx_policy.base_currency if self.fx_policy else None,
            fx_data_sha256=self.fx_series.digest if self.fx_series else None,
            fx_equity=fx_points, fx_net_pnl=fx_net, fx_max_drawdown=fx_dd,
            terminal_settlements=trader.state.delisting_resolutions,
        )
