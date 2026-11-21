from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import TradingSession
from invest_engine.domain.events import Bar
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.strategies.contracts import BarObservation, SignalDirection, StrategySignal
from invest_engine.strategies.portfolio_contracts import (
    PortfolioSignalBatch,
    PortfolioStrategyContext,
    PortfolioStrategyManifest,
    UniverseCheckpointKind,
    UniverseDecisionFrame,
    UniverseFrameOutcome,
    UniverseFrameStatus,
)


MINUTE = timedelta(minutes=1)
CHECKPOINT = timedelta(minutes=30)
T = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
SESSION_START = T - CHECKPOINT
SESSION_END = SESSION_START + timedelta(minutes=390)
A = InstrumentId(Market.US, "XNAS", "US-A", "AAA", "USD")
B = InstrumentId(Market.US, "XNYS", "US-B", "BBB", "USD")


def observation(instrument: InstrumentId, event_id: str, *,
                start: datetime = T-MINUTE, end: datetime = T,
                known_at: datetime = T) -> BarObservation:
    session = TradingSession(instrument.market, instrument.venue, SESSION_START, SESSION_END)
    bar = Bar(start, end, D("100"), D("101"), D("99"), D("100"), D("1000"),
              interval=MINUTE)
    return BarObservation(event_id, instrument, bar, known_at, session)


def frame() -> UniverseDecisionFrame:
    return UniverseDecisionFrame(
        "frame:1", T, SESSION_START, SESSION_END, 1,
        UniverseCheckpointKind.REBALANCE, (A, B),
        (observation(A, "bar:a"), observation(B, "bar:b")),
    )


def signal(instrument: InstrumentId, event_id: str, signal_id: str,
           direction: SignalDirection = SignalDirection.EXIT) -> StrategySignal:
    return StrategySignal(
        signal_id, "fixture-portfolio", "1.0.0", instrument, direction,
        D("0.10") if direction is SignalDirection.LONG else D(0),
        T, T+timedelta(minutes=5), event_id,
        D("99") if direction is SignalDirection.LONG else None,
    )


def test_universe_frame_requires_sorted_exact_one_to_one_trigger_bars():
    valid = frame()
    assert valid.instruments == (A, B)
    assert tuple(item.event_id for item in valid.trigger_bars) == ("bar:a", "bar:b")

    with pytest.raises(ValueError, match="sorted"):
        replace(valid, instruments=(B, A), trigger_bars=tuple(reversed(valid.trigger_bars)))
    with pytest.raises(ValueError, match="unique"):
        replace(valid, instruments=(A, A), trigger_bars=(valid.trigger_bars[0],) * 2)
    with pytest.raises(ValueError, match="one trigger"):
        replace(valid, trigger_bars=valid.trigger_bars[:1])
    with pytest.raises(ValueError, match="instrument"):
        replace(valid, trigger_bars=tuple(reversed(valid.trigger_bars)))
    with pytest.raises(ValueError, match="exact one-minute"):
        replace(valid, trigger_bars=(observation(A, "bar:a", start=T-2*MINUTE),
                                     valid.trigger_bars[1]))
    with pytest.raises(ValueError, match="future"):
        replace(valid, trigger_bars=(observation(A, "bar:a", known_at=T+MINUTE),
                                     valid.trigger_bars[1]))
    with pytest.raises(ValueError, match="session"):
        replace(valid, session_start=T)
    with pytest.raises(ValueError, match="slot"):
        replace(valid, slot_index=0)
    with pytest.raises(ValueError, match="kind"):
        replace(valid, kind="REBALANCE")


def test_frame_outcome_keeps_complete_unavailable_and_no_action_distinct():
    current = frame()
    complete = UniverseFrameOutcome(UniverseFrameStatus.COMPLETE, T, current)
    unavailable = UniverseFrameOutcome(
        UniverseFrameStatus.DATA_UNAVAILABLE, T,
        missing_instrument_keys=(B.key,), reason_codes=("UNIVERSE_FRAME_INCOMPLETE",),
    )
    no_action = UniverseFrameOutcome(
        UniverseFrameStatus.NO_ACTION, T,
        reason_codes=("NO_ACTION_EARLY_CLOSE",),
    )
    assert complete.frame == current
    assert unavailable.frame is None and unavailable.missing_instrument_keys == (B.key,)
    assert no_action.frame is None and not no_action.missing_instrument_keys

    with pytest.raises(ValueError, match="complete"):
        UniverseFrameOutcome(UniverseFrameStatus.COMPLETE, T)
    with pytest.raises(ValueError, match="missing"):
        UniverseFrameOutcome(UniverseFrameStatus.COMPLETE, T, current, (B.key,))
    with pytest.raises(ValueError, match="missing"):
        UniverseFrameOutcome(UniverseFrameStatus.DATA_UNAVAILABLE, T)
    with pytest.raises(ValueError, match="sorted"):
        UniverseFrameOutcome(UniverseFrameStatus.DATA_UNAVAILABLE, T,
                             missing_instrument_keys=(B.key, A.key))
    with pytest.raises(ValueError, match="reason"):
        UniverseFrameOutcome(UniverseFrameStatus.NO_ACTION, T)


def test_portfolio_manifest_rejects_invalid_intervals_and_limits():
    valid = PortfolioStrategyManifest(
        "fixture-portfolio", "1.0.0", frozenset({Market.US}),
        MINUTE, CHECKPOINT, 2, D("0.20"),
    )
    assert valid.checkpoint_interval == 30 * valid.bar_interval

    invalid = (
        {"strategy_id": ""},
        {"markets": frozenset()},
        {"bar_interval": timedelta(0)},
        {"checkpoint_interval": timedelta(minutes=29, seconds=30)},
        {"max_long_positions": 0},
        {"max_gross_target_fraction": D(0)},
        {"max_gross_target_fraction": D("1.01")},
    )
    for change in invalid:
        with pytest.raises(ValueError):
            replace(valid, **change)


def test_portfolio_context_rejects_future_history_and_filters_bars():
    current = frame()
    context = PortfolioStrategyContext(T, current, current.trigger_bars)
    assert context.bars_for(A, MINUTE) == (current.trigger_bars[0],)
    assert context.bars_for(B, timedelta(minutes=5)) == ()

    future = observation(A, "future-known", known_at=T+MINUTE)
    with pytest.raises(ValueError, match="future"):
        PortfolioStrategyContext(T, current, (future,))
    with pytest.raises(ValueError, match="frame"):
        PortfolioStrategyContext(T+MINUTE, current, current.trigger_bars)
    with pytest.raises(ValueError, match="tuple"):
        PortfolioStrategyContext(T, current, list(current.trigger_bars))  # type: ignore[arg-type]


def test_signal_batch_requires_identity_and_immutable_unique_signals():
    signals = (
        signal(A, "bar:a", "sig:a", SignalDirection.LONG),
        signal(B, "bar:b", "sig:b"),
    )
    batch = PortfolioSignalBatch("frame:1", "fixture-portfolio", "1.0.0", T, signals)
    assert batch.signals == signals

    with pytest.raises(ValueError, match="identity"):
        replace(batch, frame_id="")
    with pytest.raises(ValueError, match="identity"):
        replace(batch, strategy_id=" ")
    with pytest.raises(ValueError, match="tuple"):
        replace(batch, signals=list(signals))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate"):
        replace(batch, signals=(signals[0], signals[0]))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(batch, generated_at=T.replace(tzinfo=None))
