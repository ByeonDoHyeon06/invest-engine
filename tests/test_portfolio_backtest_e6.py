from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
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
    def __init__(self) -> None:
        self._manifest = PortfolioStrategyManifest(
            "two-symbol-round-trip",
            "1.0.0",
            frozenset({Market.US}),
            MINUTE,
            CHECKPOINT_INTERVAL,
            2,
            D("0.20"),
        )
        self.calls: list[str] = []

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
        signals = tuple(
            StrategySignal(
                signal_id=f"signal:{frame.frame_id}:{instrument.key}",
                strategy_id=self.manifest.strategy_id,
                strategy_version=self.manifest.version,
                instrument=instrument,
                direction=(
                    SignalDirection.EXIT if is_flatten else SignalDirection.LONG
                ),
                target_fraction=D(0) if is_flatten else D("0.10"),
                generated_at=frame.as_of,
                expires_at=frame.as_of + timedelta(minutes=5),
                trigger_event_id=trigger.event_id,
                stop_price=None if is_flatten else trigger.bar.close * D("0.99"),
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
        return b"two-symbol-round-trip-v1"

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
    return EventEnvelope(
        event_id,
        "market.bar",
        "fixture",
        instrument,
        end,
        end,
        end,
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
        risk=RiskLimits(
            per_trade_planned_loss=D("0.0025"),
            max_symbol_cost_fraction=D("0.10"),
            max_total_cost_fraction=D("0.20"),
            max_open_positions=2,
            require_monitoring=True,
            mark_max_age=timedelta(minutes=2),
        ),
        fill_policy=BarFillPolicy(),
        allocation_policy=AllocationPolicy(
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
