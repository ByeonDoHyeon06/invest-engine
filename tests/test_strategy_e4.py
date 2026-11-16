from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.features.technical import atr, ema
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement, StrategyManifest
from invest_engine.strategies.runtime import StrategyRunner

T = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
ONE = timedelta(minutes=1)


def setup(kr_instrument: InstrumentId) -> tuple[StrategyRunner, InstrumentId]:
    sessions = (TradingSession(Market.KR, "KRX", T, T + timedelta(hours=8)),)
    return StrategyRunner(NoTradeStrategy(DataRequirement("market.bar", ONE, warmup=3)),
                          StaticSessionCalendar(sessions)), kr_instrument


def bar_event(inst: InstrumentId, n: int, *, price: str = "7000") -> EventEnvelope[Bar]:
    start = T + ONE * n
    bar = Bar(start, start + ONE, D(price), D(price), D(price), D(price), D("20"), interval=ONE)
    end = start + ONE
    return EventEnvelope(f"bar-{n}", "market.bar", "synthetic", inst,
                         end, end, end, n, bar)


def test_no_trade_warmup_and_as_of(kr_instrument: InstrumentId) -> None:
    runner, inst = setup(kr_instrument)
    assert runner.accept(bar_event(inst, 0)).reason_codes == ("WARMUP_INCOMPLETE",)
    assert runner.accept(bar_event(inst, 1)).reason_codes == ("WARMUP_INCOMPLETE",)
    assert runner.accept(bar_event(inst, 2)).reason_codes == ("NO_ACTION",)
    with pytest.raises(InvalidEvent):
        runner.accept(bar_event(inst, 2))


def test_replay_determinism(kr_instrument: InstrumentId) -> None:
    a, inst = setup(kr_instrument)
    b, _ = setup(kr_instrument)
    inputs = [bar_event(inst, n) for n in range(30)]
    assert [a.accept(x) for x in inputs] == [b.accept(x) for x in inputs]


def test_context_protects_future_bars(kr_instrument: InstrumentId) -> None:
    runner, inst = setup(kr_instrument)
    bad = replace(bar_event(inst, 0), payload=replace(bar_event(inst, 0).payload, finalized=False))
    with pytest.raises(InvalidEvent, match="unfinalized"):
        runner.accept(bad)
    assert runner._last_ordinal == -1


def test_unavailable_session_is_no_trade(kr_instrument: InstrumentId) -> None:
    r = StrategyRunner(NoTradeStrategy(DataRequirement("market.bar", ONE)),
                       StaticSessionCalendar(()))
    assert r.accept(bar_event(kr_instrument, 0)).reason_codes == ("SESSION_UNAVAILABLE",)


def test_manifest_strict() -> None:
    with pytest.raises(ValueError):
        DataRequirement("market.bar", None)
    with pytest.raises(ValueError):
        StrategyManifest("s", "1", frozenset({Market.KR}),
                         (DataRequirement("market.bar", ONE), DataRequirement("market.bar", ONE)))


def test_feature_ema_atr_on_explicit_bars(kr_instrument: InstrumentId) -> None:
    bars = [bar_event(kr_instrument, i, price=str(100+i)).payload for i in range(4)]
    assert ema(bars, 3) == D("102")
    assert atr(bars, 2) == D("1")
    with pytest.raises(ValueError):
        ema(bars, 5)
    with pytest.raises(ValueError):
        atr(bars[:2], 2)


def test_immutable_manifest(kr_instrument: InstrumentId) -> None:
    r, _ = setup(kr_instrument)
    with pytest.raises(FrozenInstanceError):
        r.strategy.manifest.version = "2.0"  # type: ignore[misc]


def test_registry_versioned_plugins():
    from invest_engine.strategies.registry import StrategyRegistry

    strategy = NoTradeStrategy(DataRequirement("market.bar", ONE))
    registry = StrategyRegistry((strategy,))
    assert registry.get("no-trade", "1.0.0") is strategy
    assert registry.manifests() == (("no-trade", "1.0.0"),)
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(strategy)
    with pytest.raises(KeyError, match="unknown"):
        registry.get("orb", "0")
