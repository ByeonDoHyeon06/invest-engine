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
from invest_engine.core.runtime import EventRuntime, RuntimeConfig
from invest_engine.data.calendar import SessionCalendar
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Money
from invest_engine.research.fills import BarFillPolicy, eligible_fill
from invest_engine.research.report import (
    BacktestReport, DecisionRecord, EquityPoint, FillTrace, drawdown, sha256,
)
from invest_engine.strategies.allocation import (
    AllocationPolicy, allocate_targets, propose_simulated_intents,
)
from invest_engine.strategies.attribution import (
    AttributionTicket, VirtualLedger, audit_virtual_against_account,
    record_simulated_fill, ticket_for_plan,
)
from invest_engine.strategies.contracts import Strategy
from invest_engine.strategies.runtime import StrategyRunner
from invest_engine.trading.ledger import TradingState
from invest_engine.trading.models import (
    DecisionStatus, OrderStatus, SellSettlementMode, Side, TradingConfig,
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
    Stops in E4 are risk sizing plans, NOT executable stop orders in this model.
    """

    def __init__(
        self, *, calendar: SessionCalendar, strategies: tuple[Strategy, ...],
        config: TradingConfig, opening_cash: tuple[Money, ...],
        risk: RiskLimits | None = None,
        fill_policy: BarFillPolicy = BarFillPolicy(),
        allocation_policy: AllocationPolicy = AllocationPolicy(),
        settings: BacktestSettings = BacktestSettings(),
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
        self.fill_policy = fill_policy
        self.allocation_policy = allocation_policy
        self.settings = settings
        self._used = False

    def run(self, events: tuple[EventEnvelope[MarketPayload], ...]) -> BacktestReport:
        if self._used:
            raise RuntimeError("backtest instance is single-use; construct fresh strategies")
        self._used = True
        if not events:
            raise ValueError("historical market events required")
        # Input source/license and calendar are verified by the caller; no network calls.
        data_sha = sha256(tuple(canonical_bytes(e).hex() for e in events))
        config_sha = sha256((self.config, self.risk, self.fill_policy,
                             self.allocation_policy, self.settings,
                             # E4 ORB configuration differs from runtime snapshot; include both.
                             tuple((s.manifest, getattr(s, "params", None), s.snapshot().hex())
                                   for s in self.strategies),
                             # StaticSessionCalendar fully serializes, others must pin a version.
                             getattr(self.calendar, "sessions", None)))
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
        entries = exits = 0
        for event in events:
            # E2 strict ordering and quality gating precede every strategy or fill.
            observation.accept(event)
            now = max(event.available_at, event.received_at)
            matched_fills: list[str] = []
            bar = event.payload if isinstance(event.payload, Bar) else None
            if bar is not None and event.instrument_id is not None:
                if bar.end > now or event.event_time < bar.end:
                    raise InvalidEvent("bar not causally available at replay observation")
                session_check = self.calendar.session_for(event.instrument_id, bar.start)
                if session_check is None or bar.end > session_check.end:
                    raise InvalidEvent("bar outside authoritative historical session")
                # Existing orders are handled BEFORE any strategy sees this bar.
                volume_used = Decimal(0)
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
                    else:
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
            outcomes = tuple(runner.accept(event) for runner in runners)
            signals = tuple(signal for outcome in outcomes for signal in outcome.signals)
            allocated = allocate_targets(signals, as_of=now, policy=self.allocation_policy)
            proposed = propose_simulated_intents(
                allocated.plans, state=trader.state, config=self.config,
                marks=tuple(marks.values()), as_of=now,
                max_mark_age=self.settings.max_mark_age,
            ) if allocated.plans else ()
            decision_items: list[tuple[str, str, tuple[str, ...]]] = []
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
                                        | set(allocated.reason_codes)))
            decisions.append(DecisionRecord(event.event_id, tuple(s.signal_id for s in signals),
                                            tuple(i.intent_id for i in proposed),
                                            tuple(decision_items), tuple(matched_fills),
                                            reason_codes))
            equity.append(_equity(trader.state, marks, now, self.settings.max_mark_age))
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
             "Stop prices are risk plans; this fill model does not place stops.",
             "Multi-currency equity is not aggregated without a proven FX series.",
             "Run code SHA, data provider/license identifiers must be independently verified."),
        )
