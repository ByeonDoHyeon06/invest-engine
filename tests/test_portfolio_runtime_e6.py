from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from typing import Callable

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.strategies.contracts import SignalDirection, StrategySignal
from invest_engine.strategies.portfolio_contracts import (
    PortfolioSignalBatch,
    PortfolioStrategyContext,
    PortfolioStrategyManifest,
    UniverseDecisionFrame,
    UniverseFrameStatus,
)
from invest_engine.strategies.portfolio_runtime import PortfolioStrategyRunner
from invest_engine.strategies.universe import UniverseFrameCoordinator


MINUTE = timedelta(minutes=1)
CHECKPOINT_INTERVAL = timedelta(minutes=30)
SESSION_START = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
SESSION_END = SESSION_START + timedelta(minutes=390)
CHECKPOINT = SESSION_START + CHECKPOINT_INTERVAL
A = InstrumentId(Market.US, "XNAS", "US-A", "AAA", "USD")
B = InstrumentId(Market.US, "XNYS", "US-B", "BBB", "USD")
C = InstrumentId(Market.US, "XNYS", "US-C", "CCC", "USD")


def calendar(*, session_end: datetime = SESSION_END) -> StaticSessionCalendar:
    return StaticSessionCalendar(
        (
            TradingSession(Market.US, A.venue, SESSION_START, session_end),
            TradingSession(Market.US, B.venue, SESSION_START, session_end),
        )
    )


def bar_event(
    instrument: InstrumentId,
    event_id: str,
    end: datetime,
    ordinal: int,
) -> EventEnvelope[Bar]:
    bar = Bar(
        end - MINUTE,
        end,
        D("100"),
        D("101"),
        D("99"),
        D("100"),
        D("1000"),
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


class FixturePortfolioStrategy:
    def __init__(self) -> None:
        self._manifest = PortfolioStrategyManifest(
            "fixture-portfolio",
            "1.0.0",
            frozenset({Market.US}),
            MINUTE,
            CHECKPOINT_INTERVAL,
            2,
            D("0.20"),
        )
        self.calls = 0
        self.last_context: PortfolioStrategyContext | None = None
        self.state = b"initial"
        self.snapshot_calls = 0
        self.restore_calls = 0

    @property
    def manifest(self) -> PortfolioStrategyManifest:
        return self._manifest

    def on_frame(
        self,
        frame: UniverseDecisionFrame,
        context: PortfolioStrategyContext,
    ) -> PortfolioSignalBatch:
        self.calls += 1
        self.last_context = context
        signals = tuple(
            StrategySignal(
                f"signal:{frame.frame_id}:{instrument.key}",
                self.manifest.strategy_id,
                self.manifest.version,
                instrument,
                SignalDirection.LONG,
                D("0.10"),
                frame.as_of,
                frame.as_of + timedelta(minutes=5),
                trigger.event_id,
                trigger.bar.close * D("0.99"),
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
        self.snapshot_calls += 1
        return self.state

    def restore(self, data: bytes) -> None:
        self.restore_calls += 1
        self.state = data


class MutatingPortfolioStrategy(FixturePortfolioStrategy):
    def __init__(
        self,
        mutation: Callable[[PortfolioSignalBatch], PortfolioSignalBatch],
    ) -> None:
        super().__init__()
        self.mutation = mutation

    def on_frame(
        self,
        frame: UniverseDecisionFrame,
        context: PortfolioStrategyContext,
    ) -> PortfolioSignalBatch:
        return self.mutation(super().on_frame(frame, context))


class OneLongPortfolioStrategy(FixturePortfolioStrategy):
    def __init__(self) -> None:
        super().__init__()
        self._manifest = replace(self._manifest, max_long_positions=1)


def configured_runner(
    strategy: FixturePortfolioStrategy | None = None,
    *,
    source_calendar: StaticSessionCalendar | None = None,
) -> tuple[PortfolioStrategyRunner, FixturePortfolioStrategy]:
    fixture = strategy or FixturePortfolioStrategy()
    coordinator = UniverseFrameCoordinator(source_calendar or calendar(), (B, A))
    return PortfolioStrategyRunner(fixture, coordinator), fixture


def feed_complete_checkpoint(runner: PortfolioStrategyRunner) -> None:
    runner.accept(bar_event(B, "bar:b:1000", CHECKPOINT, 0))
    runner.accept(bar_event(A, "bar:a:1000", CHECKPOINT, 1))


def test_complete_frame_dispatches_once_with_read_only_causal_context() -> None:
    runner, strategy = configured_runner()
    feed_complete_checkpoint(runner)

    result = runner.evaluate(CHECKPOINT)

    assert result.frame_outcome.status is UniverseFrameStatus.COMPLETE
    assert result.batch is not None
    assert strategy.calls == 1
    assert strategy.last_context is not None
    assert all(bar.known_at <= CHECKPOINT for bar in strategy.last_context.bars)
    assert not any(
        hasattr(runner, name)
        for name in ("allocation", "trading_state", "account", "broker")
    )
    assert not hasattr(runner, "snapshot")
    strategy.restore(b"strategy-owned")
    assert strategy.snapshot() == b"strategy-owned"


def test_incomplete_and_no_action_frames_do_not_call_strategy() -> None:
    incomplete_runner, incomplete_strategy = configured_runner()
    incomplete_runner.accept(bar_event(A, "bar:a:1000", CHECKPOINT, 0))
    incomplete = incomplete_runner.evaluate(CHECKPOINT)
    assert incomplete.frame_outcome.status is UniverseFrameStatus.DATA_UNAVAILABLE
    assert incomplete.batch is None
    assert incomplete_strategy.calls == 0

    outside = SESSION_START + timedelta(minutes=15)
    no_action_runner, no_action_strategy = configured_runner()
    no_action_runner.accept(bar_event(A, "bar:a:0945", outside, 0))
    no_action_runner.accept(bar_event(B, "bar:b:0945", outside, 1))
    no_action = no_action_runner.evaluate(outside)
    assert no_action.frame_outcome.status is UniverseFrameStatus.NO_ACTION
    assert no_action.batch is None
    assert no_action_strategy.calls == 0


def _replace_child(
    batch: PortfolioSignalBatch,
    index: int = 0,
    **changes: object,
) -> PortfolioSignalBatch:
    signals = list(batch.signals)
    signals[index] = replace(signals[index], **changes)
    return replace(batch, signals=tuple(signals))


def _append_foreign_child(batch: PortfolioSignalBatch) -> PortfolioSignalBatch:
    foreign = replace(
        batch.signals[0],
        signal_id="signal:foreign",
        instrument=C,
        trigger_event_id="bar:c:1000",
    )
    return replace(batch, signals=(*batch.signals, foreign))


def _expire_child_without_constructor_revalidation(
    batch: PortfolioSignalBatch,
) -> PortfolioSignalBatch:
    expired = replace(batch.signals[0])
    object.__setattr__(expired, "expires_at", CHECKPOINT)
    return replace(batch, signals=(expired, *batch.signals[1:]))


def _increase_gross_target(batch: PortfolioSignalBatch) -> PortfolioSignalBatch:
    return replace(
        batch,
        signals=tuple(
            replace(signal, target_fraction=D("0.11"))
            for signal in batch.signals
        ),
    )


def _exit_second_member(batch: PortfolioSignalBatch) -> PortfolioSignalBatch:
    return _replace_child(
        batch,
        index=1,
        direction=SignalDirection.EXIT,
        target_fraction=D(0),
        stop_price=None,
    )


def test_batch_must_match_frame_manifest_time_members_and_triggers() -> None:
    mutations: tuple[
        tuple[str, Callable[[PortfolioSignalBatch], PortfolioSignalBatch]], ...
    ] = (
        ("frame id", lambda batch: replace(batch, frame_id="wrong-frame")),
        ("strategy id", lambda batch: replace(batch, strategy_id="wrong-strategy")),
        ("strategy version", lambda batch: replace(batch, strategy_version="9.9.9")),
        (
            "batch generated time",
            lambda batch: replace(batch, generated_at=CHECKPOINT + MINUTE),
        ),
        ("signal order", lambda batch: replace(batch, signals=tuple(reversed(batch.signals)))),
        ("missing member", lambda batch: replace(batch, signals=batch.signals[:1])),
        ("extra member", _append_foreign_child),
        (
            "child trigger",
            lambda batch: _replace_child(batch, trigger_event_id="foreign-trigger"),
        ),
        (
            "child strategy id",
            lambda batch: _replace_child(batch, strategy_id="wrong-strategy"),
        ),
        (
            "child strategy version",
            lambda batch: _replace_child(batch, strategy_version="9.9.9"),
        ),
        (
            "child generated time",
            lambda batch: _replace_child(
                batch,
                generated_at=CHECKPOINT - MINUTE,
            ),
        ),
        ("child expiry", _expire_child_without_constructor_revalidation),
    )

    for label, mutation in mutations:
        strategy = MutatingPortfolioStrategy(mutation)
        runner, _ = configured_runner(strategy)
        feed_complete_checkpoint(runner)
        with pytest.raises(InvalidEvent, match="portfolio strategy batch"):
            runner.evaluate(CHECKPOINT)
        assert runner.halt_reason is not None, label
        with pytest.raises(InvalidEvent, match="halted"):
            runner.evaluate(CHECKPOINT)


def test_batch_rejects_excess_long_count_and_gross_target() -> None:
    strategies: tuple[tuple[str, FixturePortfolioStrategy], ...] = (
        ("long count", OneLongPortfolioStrategy()),
        ("gross target", MutatingPortfolioStrategy(_increase_gross_target)),
    )
    for label, strategy in strategies:
        runner, _ = configured_runner(strategy)
        feed_complete_checkpoint(runner)
        with pytest.raises(InvalidEvent, match="portfolio strategy batch"):
            runner.evaluate(CHECKPOINT)
        assert runner.halt_reason is not None, label


def test_exit_targets_and_valid_two_long_batch_pass() -> None:
    valid_runner, _ = configured_runner()
    feed_complete_checkpoint(valid_runner)
    valid = valid_runner.evaluate(CHECKPOINT)
    assert valid.batch is not None
    assert len(
        [
            signal
            for signal in valid.batch.signals
            if signal.direction is SignalDirection.LONG
        ]
    ) == 2
    assert sum(
        (signal.target_fraction for signal in valid.batch.signals),
        D(0),
    ) == D("0.20")

    exit_runner, _ = configured_runner(
        MutatingPortfolioStrategy(_exit_second_member)
    )
    feed_complete_checkpoint(exit_runner)
    exit_result = exit_runner.evaluate(CHECKPOINT)
    assert exit_result.batch is not None
    assert exit_result.batch.signals[1].direction is SignalDirection.EXIT
    assert exit_result.batch.signals[1].target_fraction == 0

    with pytest.raises(ValueError, match="exit target"):
        replace(
            valid.batch.signals[0],
            direction=SignalDirection.EXIT,
        )


def test_runner_invalidation_delegates_without_resetting_strategy_or_stream() -> None:
    runner, strategy = configured_runner()
    strategy.state = b"preserve-me"
    feed_complete_checkpoint(runner)
    assert runner.evaluate(CHECKPOINT).batch is not None
    coordinator = runner.coordinator
    audit_before = (
        coordinator.last_ordinal,
        coordinator.last_known,
        coordinator.finalized_watermark,
    )
    strategy_before = (
        strategy.state,
        strategy.calls,
        strategy.snapshot_calls,
        strategy.restore_calls,
    )

    runner.invalidate_instrument_history(A)

    assert all(
        item.instrument.key != A.key for item in coordinator.observations
    )
    assert any(
        item.instrument.key == B.key for item in coordinator.observations
    )
    assert (
        coordinator.last_ordinal,
        coordinator.last_known,
        coordinator.finalized_watermark,
    ) == audit_before
    assert (
        strategy.state,
        strategy.calls,
        strategy.snapshot_calls,
        strategy.restore_calls,
    ) == strategy_before
