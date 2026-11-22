from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.research.fills import BarFillPolicy
from invest_engine.research.portfolio_backtest import HistoricalPortfolioBacktest
from invest_engine.strategies.allocation import AllocationPolicy
from invest_engine.strategies.contracts import SignalDirection, StrategySignal
from invest_engine.strategies.portfolio_contracts import (
    PortfolioSignalBatch,
    PortfolioStrategyContext,
    PortfolioStrategyManifest,
    UniverseCheckpointKind,
    UniverseDecisionFrame,
    UniverseFrameStatus,
)
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits


MINUTE = timedelta(minutes=1)
CHECKPOINT_INTERVAL = timedelta(minutes=30)
SESSION_START = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
SESSION_END = SESSION_START + timedelta(minutes=390)
FIRST_CHECKPOINT = SESSION_START + CHECKPOINT_INTERVAL
FLATTEN = SESSION_END - CHECKPOINT_INTERVAL
A = InstrumentId(Market.US, "XNAS", "US-A", "AAA", "USD")
B = InstrumentId(Market.US, "XNYS", "US-B", "BBB", "USD")


class TwoSymbolRoundTripStrategy:
    def __init__(
        self,
        selections_by_slot: dict[int, tuple[str, ...]] | None = None,
        *,
        target_fraction: D = D("0.10"),
        max_gross_target_fraction: D | None = None,
        checkpoint_interval: timedelta = CHECKPOINT_INTERVAL,
    ) -> None:
        self.target_fraction = target_fraction
        self._manifest = PortfolioStrategyManifest(
            "two-symbol-round-trip",
            "1.0.0",
            frozenset({Market.US}),
            MINUTE,
            checkpoint_interval,
            2,
            max_gross_target_fraction or target_fraction * 2,
        )
        self.calls: list[str] = []
        self.selections_by_slot = selections_by_slot

    @property
    def manifest(self) -> PortfolioStrategyManifest:
        return self._manifest

    def on_frame(
        self,
        frame: UniverseDecisionFrame,
        context: PortfolioStrategyContext,
    ) -> PortfolioSignalBatch:
        self.calls.append(frame.frame_id)
        is_flatten = frame.kind is UniverseCheckpointKind.FLATTEN
        selected = (
            frozenset(instrument.key for instrument in frame.instruments)
            if self.selections_by_slot is None
            else frozenset(self.selections_by_slot.get(frame.slot_index, ()))
        )
        signals = tuple(
            StrategySignal(
                signal_id=f"signal:{frame.frame_id}:{instrument.key}",
                strategy_id=self.manifest.strategy_id,
                strategy_version=self.manifest.version,
                instrument=instrument,
                direction=(
                    SignalDirection.EXIT
                    if is_flatten or instrument.key not in selected
                    else SignalDirection.LONG
                ),
                target_fraction=(
                    D(0)
                    if is_flatten or instrument.key not in selected
                    else self.target_fraction
                ),
                generated_at=frame.as_of,
                expires_at=frame.as_of + timedelta(minutes=5),
                trigger_event_id=trigger.event_id,
                stop_price=(
                    None
                    if is_flatten or instrument.key not in selected
                    else trigger.bar.close * D("0.99")
                ),
            )
            for instrument, trigger in zip(
                frame.instruments,
                frame.trigger_bars,
                strict=True,
            )
        )
        return PortfolioSignalBatch(
            frame.frame_id,
            self.manifest.strategy_id,
            self.manifest.version,
            frame.as_of,
            signals,
        )

    def snapshot(self) -> bytes:
        return repr(
            (
                self.selections_by_slot,
                self.target_fraction,
                self.manifest.max_gross_target_fraction,
            )
        ).encode("utf-8")

    def restore(self, data: bytes) -> None:
        if data != self.snapshot():
            raise ValueError("unexpected strategy snapshot")


def calendar() -> StaticSessionCalendar:
    return StaticSessionCalendar(
        (
            TradingSession(Market.US, A.venue, SESSION_START, SESSION_END),
            TradingSession(Market.US, B.venue, SESSION_START, SESSION_END),
        )
    )


def bar_event(
    instrument: InstrumentId,
    event_id: str,
    end: datetime,
    ordinal: int,
    *,
    price: str,
    low: str | None = None,
    high: str | None = None,
    volume: str = "10000",
    known_at: datetime | None = None,
) -> EventEnvelope[Bar]:
    close = D(price)
    bar = Bar(
        end - MINUTE,
        end,
        close,
        D(high) if high is not None else close,
        D(low) if low is not None else close,
        close,
        D(volume),
        interval=MINUTE,
    )
    observed_at = known_at or end
    return EventEnvelope(
        event_id,
        "market.bar",
        "fixture",
        instrument,
        end,
        observed_at,
        observed_at,
        ordinal,
        bar,
    )


def happy_path_events() -> tuple[EventEnvelope[Bar], ...]:
    rows = (
        bar_event(A, "trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(
            A,
            "entry-fill:a",
            FIRST_CHECKPOINT + MINUTE,
            2,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(
            B,
            "entry-fill:b",
            FIRST_CHECKPOINT + MINUTE,
            3,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "flatten:a", FLATTEN, 4, price="105"),
        bar_event(B, "flatten:b", FLATTEN, 5, price="105"),
        bar_event(
            A,
            "exit-fill:a",
            FLATTEN + MINUTE,
            6,
            price="105",
            low="104",
            high="107",
        ),
        bar_event(
            B,
            "exit-fill:b",
            FLATTEN + MINUTE,
            7,
            price="105",
            low="104",
            high="107",
        ),
        bar_event(A, "session-end:a", SESSION_END, 8, price="105"),
        bar_event(B, "session-end:b", SESSION_END, 9, price="105"),
    )
    return rows


def make_backtest(
    strategy: TwoSymbolRoundTripStrategy | None = None,
    *,
    risk: RiskLimits | None = None,
    allocation_policy: AllocationPolicy | None = None,
) -> tuple[HistoricalPortfolioBacktest, TwoSymbolRoundTripStrategy]:
    selected = strategy or TwoSymbolRoundTripStrategy()
    config = TradingConfig(
        "portfolio-sim",
        (MonetaryRules("USD", D("0.01")),),
        (
            (A.key, InstrumentRules(D("0.01"), D("1"))),
            (B.key, InstrumentRules(D("0.01"), D("1"))),
        ),
        fee_rate=D(0),
    )
    runner = HistoricalPortfolioBacktest(
        calendar=calendar(),
        instruments=(B, A),
        strategy=selected,
        config=config,
        opening_cash=(Money(D("100000"), "USD"),),
        risk=risk
        or RiskLimits(
                per_trade_planned_loss=D("0.0025"),
                max_symbol_cost_fraction=D("0.10"),
                max_total_cost_fraction=D("0.20"),
                max_open_positions=2,
                require_monitoring=True,
                mark_max_age=timedelta(minutes=2),
            ),
        fill_policy=BarFillPolicy(),
        allocation_policy=allocation_policy
        or AllocationPolicy(
                max_symbol_fraction=D("0.10"),
                max_currency_fraction=D("0.20"),
            ),
    )
    return runner, selected


def test_two_symbols_share_one_monitored_account_and_fill_only_later() -> None:
    backtest, strategy = make_backtest()

    report = backtest.run(happy_path_events())

    complete = tuple(
        decision
        for decision in report.universe_decisions
        if decision.status is UniverseFrameStatus.COMPLETE
    )
    assert len(strategy.calls) == len(complete) == 2
    assert report.account_report.by_currency_start == (("USD", D("100000")),)
    assert report.account_report.entry_fill_count == 2
    assert report.account_report.exit_fill_count == 2
    assert {row.market_event_id for row in report.executions} == {
        "entry-fill:a",
        "entry-fill:b",
        "exit-fill:a",
        "exit-fill:b",
    }
    assert not {"trigger:a", "trigger:b", "flatten:a", "flatten:b"}.intersection(
        row.market_event_id for row in report.executions
    )
    entry_notional = sum(
        (
            execution.quantity * execution.price
            for execution in report.executions
            if execution.side.value == "BUY"
        ),
        D(0),
    )
    assert entry_notional / D("100000") == D("0.20")
    assert len(report.cycles) == 2
    assert all(cycle.entry_quantity == cycle.exit_quantity == D("100") for cycle in report.cycles)
    assert report.account_report.by_currency_end == (("USD", D("101000")),)


def test_flatten_checkpoint_is_scheduled_outside_rebalance_grid() -> None:
    checkpoint_interval = timedelta(minutes=60)
    first_checkpoint = SESSION_START + checkpoint_interval
    flatten = SESSION_END - checkpoint_interval
    backtest, strategy = make_backtest(
        TwoSymbolRoundTripStrategy(checkpoint_interval=checkpoint_interval)
    )
    events = (
        bar_event(A, "trigger:a", first_checkpoint, 0, price="100"),
        bar_event(B, "trigger:b", first_checkpoint, 1, price="100"),
        bar_event(
            A,
            "entry-fill:a",
            first_checkpoint + MINUTE,
            2,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(
            B,
            "entry-fill:b",
            first_checkpoint + MINUTE,
            3,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "flatten:a", flatten, 4, price="105"),
        bar_event(B, "flatten:b", flatten, 5, price="105"),
        bar_event(
            A,
            "exit-fill:a",
            flatten + MINUTE,
            6,
            price="105",
            low="104",
            high="107",
        ),
        bar_event(
            B,
            "exit-fill:b",
            flatten + MINUTE,
            7,
            price="105",
            low="104",
            high="107",
        ),
        bar_event(A, "session-end:a", SESSION_END, 8, price="105"),
        bar_event(B, "session-end:b", SESSION_END, 9, price="105"),
    )

    report = backtest.run(events)

    assert len(strategy.calls) == 2
    assert report.account_report.entry_fill_count == 2
    assert report.account_report.exit_fill_count == 2
    assert report.account_report.by_currency_end == (("USD", D("101000")),)


def test_portfolio_replay_is_deterministic_and_single_use() -> None:
    first, _ = make_backtest()
    second, _ = make_backtest()

    first_config = first.config_digest()
    second_config = second.config_digest()
    first_report = first.run(happy_path_events())
    second_report = second.run(happy_path_events())

    assert first_config == second_config
    assert first_report.account_report.run_sha256 == (
        second_report.account_report.run_sha256
    )
    assert first_report.run_sha256 == second_report.run_sha256
    assert first_report == second_report
    with pytest.raises(RuntimeError, match="single-use"):
        first.run(happy_path_events())


def test_entry_expiry_processes_last_eligible_bar_then_cancels_remainder() -> None:
    strategy = TwoSymbolRoundTripStrategy({1: (A.key,)})
    backtest, _ = make_backtest(strategy)
    events: list[EventEnvelope[Bar]] = [
        bar_event(A, "trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "trigger:b", FIRST_CHECKPOINT, 1, price="100"),
    ]
    for minute in range(1, 6):
        events.append(
            bar_event(
                A,
                f"partial-entry:a:{minute}",
                FIRST_CHECKPOINT + minute * MINUTE,
                len(events),
                price="100",
                low="98",
                high="101",
                volume="200",
            )
        )
    events.extend(
        (
            bar_event(A, "flatten:a", FLATTEN, 7, price="105"),
            bar_event(B, "flatten:b", FLATTEN, 8, price="105"),
            bar_event(
                A,
                "exit-fill:a",
                FLATTEN + MINUTE,
                9,
                price="105",
                low="104",
                high="107",
            ),
            bar_event(A, "session-end:a", SESSION_END, 10, price="105"),
            bar_event(B, "session-end:b", SESSION_END, 11, price="105"),
        )
    )

    report = backtest.run(tuple(events))

    assert report.account_report.entry_fill_count == 5
    assert report.account_report.exit_fill_count == 1
    assert len(report.cycles) == 1
    assert report.cycles[0].entry_quantity == D("50")
    assert report.cycles[0].exit_quantity == D("50")
    entry_decision = next(
        decision
        for decision in report.universe_decisions
        if decision.as_of == FIRST_CHECKPOINT
    )
    assert len(entry_decision.canceled_intent_ids) == 1
    assert "ENTRY_EXPIRED" in entry_decision.reason_codes


def test_bar_starting_at_expiry_cannot_fill_canceled_entry() -> None:
    strategy = TwoSymbolRoundTripStrategy({1: (A.key,)})
    backtest, _ = make_backtest(strategy)
    expiry = FIRST_CHECKPOINT + timedelta(minutes=5)
    events = (
        bar_event(A, "trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(A, "last-eligible:no-cross", expiry, 2, price="100"),
        bar_event(
            A,
            "starts-at-expiry:cross",
            expiry + MINUTE,
            3,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "flatten:a", FLATTEN, 4, price="105"),
        bar_event(B, "flatten:b", FLATTEN, 5, price="105"),
        bar_event(A, "session-end:a", SESSION_END, 6, price="105"),
        bar_event(B, "session-end:b", SESSION_END, 7, price="105"),
    )

    report = backtest.run(events)

    assert report.account_report.entry_fill_count == 0
    assert report.executions == ()
    entry_decision = next(
        decision
        for decision in report.universe_decisions
        if decision.as_of == FIRST_CHECKPOINT
    )
    assert entry_decision.canceled_intent_ids == entry_decision.intent_ids


def test_later_checkpoint_cancels_replaceable_buy_before_new_targets() -> None:
    second_checkpoint = FIRST_CHECKPOINT + CHECKPOINT_INTERVAL
    strategy = TwoSymbolRoundTripStrategy(
        {1: (A.key,), 2: (B.key,)}
    )
    backtest, _ = make_backtest(strategy)
    events = (
        bar_event(A, "first-trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "first-trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(A, "second-trigger:a", second_checkpoint, 2, price="100"),
        bar_event(B, "second-trigger:b", second_checkpoint, 3, price="100"),
        bar_event(
            B,
            "second-entry-fill:b",
            second_checkpoint + MINUTE,
            4,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "flatten:a", FLATTEN, 5, price="105"),
        bar_event(B, "flatten:b", FLATTEN, 6, price="105"),
        bar_event(
            B,
            "exit-fill:b",
            FLATTEN + MINUTE,
            7,
            price="105",
            low="104",
            high="107",
        ),
        bar_event(A, "session-end:a", SESSION_END, 8, price="105"),
        bar_event(B, "session-end:b", SESSION_END, 9, price="105"),
    )

    report = backtest.run(events)

    first = next(
        decision
        for decision in report.universe_decisions
        if decision.as_of == FIRST_CHECKPOINT
    )
    second = next(
        decision
        for decision in report.universe_decisions
        if decision.as_of == second_checkpoint
    )
    assert first.canceled_intent_ids == first.intent_ids
    assert "REPLACED_ENTRY_CANCELED" in first.reason_codes
    assert second.intent_ids
    assert second.decisions[0][1] == "APPROVED"
    assert {execution.instrument for execution in report.executions} == {B}


def test_incomplete_checkpoint_records_data_unavailable_without_strategy_or_order() -> None:
    strategy = TwoSymbolRoundTripStrategy({1: (A.key,)})
    backtest, _ = make_backtest(strategy)
    events = (
        bar_event(A, "incomplete-trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(A, "flatten:a", FLATTEN, 1, price="100"),
        bar_event(B, "flatten:b", FLATTEN, 2, price="100"),
        bar_event(A, "session-end:a", SESSION_END, 3, price="100"),
        bar_event(B, "session-end:b", SESSION_END, 4, price="100"),
    )

    report = backtest.run(events)

    unavailable = next(
        decision
        for decision in report.universe_decisions
        if decision.as_of == FIRST_CHECKPOINT
    )
    assert unavailable.status is UniverseFrameStatus.DATA_UNAVAILABLE
    assert unavailable.missing_instrument_keys == (B.key,)
    assert unavailable.signal_ids == ()
    assert unavailable.intent_ids == ()
    assert len(strategy.calls) == 1  # only the complete final flatten frame


def test_delayed_bar_behind_finalized_watermark_fails_replay() -> None:
    backtest, _ = make_backtest(TwoSymbolRoundTripStrategy({1: (A.key,)}))
    events = (
        bar_event(A, "trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(
            A,
            "clock-advance:a",
            FIRST_CHECKPOINT + MINUTE,
            1,
            price="100",
        ),
        bar_event(
            B,
            "delayed-trigger:b",
            FIRST_CHECKPOINT,
            2,
            price="100",
            known_at=FIRST_CHECKPOINT + 2 * MINUTE,
        ),
    )

    with pytest.raises(InvalidEvent, match="watermark"):
        backtest.run(events)


def test_unresolved_exit_at_replacement_checkpoint_invalidates_arm() -> None:
    second_checkpoint = FIRST_CHECKPOINT + CHECKPOINT_INTERVAL
    third_checkpoint = second_checkpoint + CHECKPOINT_INTERVAL
    strategy = TwoSymbolRoundTripStrategy(
        {1: (A.key,), 2: (B.key,), 3: (B.key,)}
    )
    backtest, _ = make_backtest(strategy)
    events = (
        bar_event(A, "first-trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "first-trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(
            A,
            "first-entry-fill:a",
            FIRST_CHECKPOINT + MINUTE,
            2,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "second-trigger:a", second_checkpoint, 3, price="100"),
        bar_event(B, "second-trigger:b", second_checkpoint, 4, price="100"),
        bar_event(
            B,
            "second-entry-fill:b",
            second_checkpoint + MINUTE,
            5,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "third-trigger:a", third_checkpoint, 6, price="100"),
        bar_event(B, "third-trigger:b", third_checkpoint, 7, price="100"),
        bar_event(
            B,
            "third-clock-advance:b",
            third_checkpoint + MINUTE,
            8,
            price="100",
        ),
    )

    with pytest.raises(InvalidEvent, match="unresolved EXIT"):
        backtest.run(events)


def test_unresolved_final_inventory_invalidates_session() -> None:
    strategy = TwoSymbolRoundTripStrategy({1: (A.key,)})
    backtest, _ = make_backtest(strategy)
    events = (
        bar_event(A, "trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(
            A,
            "entry-fill:a",
            FIRST_CHECKPOINT + MINUTE,
            2,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "incomplete-flatten:a", FLATTEN, 3, price="100"),
        bar_event(A, "session-end:a", SESSION_END, 4, price="100"),
        bar_event(B, "session-end:b", SESSION_END, 5, price="100"),
    )

    with pytest.raises(InvalidEvent, match="final inventory"):
        backtest.run(events)


def test_multiple_buys_reobserve_after_state_change_and_share_total_cap() -> None:
    strategy = TwoSymbolRoundTripStrategy(
        target_fraction=D("0.15"),
        max_gross_target_fraction=D("0.30"),
    )
    backtest, _ = make_backtest(
        strategy,
        risk=RiskLimits(
            per_trade_planned_loss=D("0.0025"),
            max_symbol_cost_fraction=D("0.20"),
            max_total_cost_fraction=D("0.20"),
            max_open_positions=2,
            require_monitoring=True,
            mark_max_age=timedelta(minutes=2),
        ),
        allocation_policy=AllocationPolicy(
            max_symbol_fraction=D("0.15"),
            max_currency_fraction=D("0.30"),
        ),
    )
    expiry = FIRST_CHECKPOINT + timedelta(minutes=5)
    events = (
        bar_event(A, "trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(A, "expiry:a", expiry, 2, price="100"),
        bar_event(A, "flatten:a", FLATTEN, 3, price="100"),
        bar_event(B, "flatten:b", FLATTEN, 4, price="100"),
        bar_event(A, "session-end:a", SESSION_END, 5, price="100"),
        bar_event(B, "session-end:b", SESSION_END, 6, price="100"),
    )

    report = backtest.run(events)

    decision = next(
        item
        for item in report.universe_decisions
        if item.as_of == FIRST_CHECKPOINT
    )
    assert tuple(row[1] for row in decision.decisions) == (
        "APPROVED",
        "REJECTED",
    )
    assert decision.decisions[1][2] == ("TOTAL_COST_LIMIT",)
    assert "MARK_RECHECK_AFTER_STATE_CHANGE" not in decision.decisions[1][2]


def test_rotation_cannot_spend_pending_sale_proceeds() -> None:
    second_checkpoint = FIRST_CHECKPOINT + CHECKPOINT_INTERVAL
    strategy = TwoSymbolRoundTripStrategy({1: (A.key,), 2: (B.key,)})
    backtest, _ = make_backtest(
        strategy,
        risk=RiskLimits(
            per_trade_planned_loss=D("0.0025"),
            max_symbol_cost_fraction=D("0.10"),
            max_total_cost_fraction=D("0.10"),
            max_open_positions=2,
            require_monitoring=True,
            mark_max_age=timedelta(minutes=2),
        ),
    )
    events = (
        bar_event(A, "first-trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "first-trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(
            A,
            "first-entry-fill:a",
            FIRST_CHECKPOINT + MINUTE,
            2,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "second-trigger:a", second_checkpoint, 3, price="100"),
        bar_event(B, "second-trigger:b", second_checkpoint, 4, price="100"),
        bar_event(B, "second-clock:b", second_checkpoint + MINUTE, 5, price="100"),
        bar_event(
            A,
            "pending-exit-fill:a",
            second_checkpoint + MINUTE,
            6,
            price="100",
            low="99",
            high="102",
        ),
        bar_event(A, "flatten:a", FLATTEN, 7, price="100"),
        bar_event(B, "flatten:b", FLATTEN, 8, price="100"),
        bar_event(A, "session-end:a", SESSION_END, 9, price="100"),
        bar_event(B, "session-end:b", SESSION_END, 10, price="100"),
    )

    report = backtest.run(events)

    rotation = next(
        item
        for item in report.universe_decisions
        if item.as_of == second_checkpoint
    )
    assert tuple(row[1] for row in rotation.decisions) == (
        "APPROVED",
        "REJECTED",
    )
    assert rotation.decisions[1][2] == ("TOTAL_COST_LIMIT",)
    assert all(execution.instrument == A for execution in report.executions)


def test_stale_held_symbol_mark_blocks_new_exposure_without_zero_valuation() -> None:
    second_checkpoint = FIRST_CHECKPOINT + CHECKPOINT_INTERVAL
    strategy = TwoSymbolRoundTripStrategy({1: (A.key,), 2: (B.key,)})
    backtest, _ = make_backtest(strategy)
    events = (
        bar_event(A, "first-trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "first-trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(
            A,
            "first-entry-fill:a",
            FIRST_CHECKPOINT + MINUTE,
            2,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(B, "incomplete-second:b", second_checkpoint, 3, price="100"),
        bar_event(
            B,
            "second-clock:b",
            second_checkpoint + MINUTE,
            4,
            price="100",
        ),
        bar_event(A, "flatten:a", FLATTEN, 5, price="105"),
        bar_event(B, "flatten:b", FLATTEN, 6, price="105"),
        bar_event(
            A,
            "exit-fill:a",
            FLATTEN + MINUTE,
            7,
            price="105",
            low="104",
            high="107",
        ),
        bar_event(A, "session-end:a", SESSION_END, 8, price="105"),
        bar_event(B, "session-end:b", SESSION_END, 9, price="105"),
    )

    report = backtest.run(events)

    blocked = next(
        item
        for item in report.universe_decisions
        if item.as_of == second_checkpoint
    )
    assert blocked.status is UniverseFrameStatus.DATA_UNAVAILABLE
    assert blocked.missing_instrument_keys == (A.key,)
    assert blocked.intent_ids == ()
    stale_points = tuple(
        point for point in report.account_report.equity if point.at == second_checkpoint
    )
    assert stale_points
    assert all(not point.complete and point.by_currency == () for point in stale_points)


def daily_loss_events() -> tuple[EventEnvelope[Bar], ...]:
    second_checkpoint = FIRST_CHECKPOINT + CHECKPOINT_INTERVAL
    third_checkpoint = second_checkpoint + CHECKPOINT_INTERVAL
    return (
        bar_event(A, "first-trigger:a", FIRST_CHECKPOINT, 0, price="100"),
        bar_event(B, "first-trigger:b", FIRST_CHECKPOINT, 1, price="100"),
        bar_event(
            A,
            "first-entry-fill:a",
            FIRST_CHECKPOINT + MINUTE,
            2,
            price="100",
            low="98",
            high="101",
        ),
        bar_event(A, "loss-trigger:a", second_checkpoint, 3, price="90"),
        bar_event(B, "loss-trigger:b", second_checkpoint, 4, price="100"),
        bar_event(
            A,
            "loss-exit-fill:a",
            second_checkpoint + MINUTE,
            5,
            price="90",
            low="89",
            high="92",
        ),
        bar_event(A, "rebound-trigger:a", third_checkpoint, 6, price="100"),
        bar_event(B, "rebound-trigger:b", third_checkpoint, 7, price="100"),
        bar_event(
            A,
            "rebound-clock:a",
            third_checkpoint + MINUTE,
            8,
            price="100",
            low="99",
            high="102",
        ),
        bar_event(A, "flatten:a", FLATTEN, 9, price="100"),
        bar_event(B, "flatten:b", FLATTEN, 10, price="100"),
        bar_event(A, "session-end:a", SESSION_END, 11, price="100"),
        bar_event(B, "session-end:b", SESSION_END, 12, price="100"),
    )


def daily_loss_backtest() -> HistoricalPortfolioBacktest:
    strategy = TwoSymbolRoundTripStrategy(
        {
            1: (A.key,),
            2: (A.key, B.key),
            3: (B.key,),
        }
    )
    backtest, _ = make_backtest(strategy)
    return backtest


def test_daily_loss_latch_replaces_longs_with_complete_exit_targets() -> None:
    report = daily_loss_backtest().run(daily_loss_events())
    second_checkpoint = FIRST_CHECKPOINT + CHECKPOINT_INTERVAL
    loss_decision = next(
        item
        for item in report.universe_decisions
        if item.as_of == second_checkpoint
    )

    assert set(loss_decision.selected_instrument_keys) == {A.key, B.key}
    assert "DAILY_LOSS_LIMIT" in loss_decision.reason_codes
    assert "DAILY_LOSS_EXIT_OVERRIDE" in loss_decision.reason_codes
    assert tuple(row[1] for row in loss_decision.decisions) == ("APPROVED",)
    loss_exit = next(
        execution
        for execution in report.executions
        if execution.source_frame_id == loss_decision.frame_id
    )
    assert loss_exit.instrument == A
    assert loss_exit.side.value == "SELL"
    assert loss_exit.price == D("90")


def test_daily_loss_latch_survives_later_rebound_within_session() -> None:
    report = daily_loss_backtest().run(daily_loss_events())
    third_checkpoint = FIRST_CHECKPOINT + 2 * CHECKPOINT_INTERVAL
    rebound = next(
        item
        for item in report.universe_decisions
        if item.as_of == third_checkpoint
    )

    assert rebound.selected_instrument_keys == (B.key,)
    assert "DAILY_LOSS_EXIT_OVERRIDE" in rebound.reason_codes
    assert rebound.intent_ids == ()
    assert report.account_report.by_currency_end == (("USD", D("99000")),)
