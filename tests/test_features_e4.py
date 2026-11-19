"""As-of technical-feature and fail-closed plugin contract checks."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.features.registry import FeatureDefinition, FeatureKind, FeatureRegistry
from invest_engine.strategies.contracts import BarObservation, DataRequirement, StrategyManifest
from invest_engine.strategies.runtime import StrategyRunner

T = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
STEP = timedelta(minutes=1)
INST = InstrumentId(Market.KR, "KRX", "kr-syn", "SYN", "KRW")
SESS = TradingSession(Market.KR, "KRX", T, T + timedelta(hours=2))


def event(n: int, *, finalized=True):
    start = T + STEP*n
    bar = Bar(start, start+STEP, D("99"), D("102"), D("98"), D(str(100+n)), D(str(n+5)), interval=STEP, finalized=finalized)
    return EventEnvelope(str(n), "market.bar", "fixture", INST, start+STEP,
                         start+STEP, start+STEP, n, bar)


def test_feature_registry_uses_only_as_of_available_observations():
    b0 = event(0)
    b1 = event(1)
    b2 = event(2)
    bars = tuple(BarObservation(e.event_id, INST, e.payload, e.received_at, SESS) for e in (b0,b1,b2))
    definitions = (
        FeatureDefinition("ema2", FeatureKind.EMA, STEP, 2),
        FeatureDefinition("atr2", FeatureKind.ATR, STEP, 2),
        FeatureDefinition("volume2", FeatureKind.MEDIAN_VOLUME, STEP, 2),
    )
    reg = FeatureRegistry(definitions)
    before = reg.compute(INST, b1.received_at, bars)
    assert {x.name for x in before} == {"ema2", "volume2"}
    after = reg.compute(INST, b2.received_at, bars)
    assert {x.name for x in after} == {"ema2", "atr2", "volume2"}
    assert {x.name: x.value for x in after}["volume2"] == D("6.5")
    assert all(x.as_of == b2.received_at for x in after)
    assert "2" not in before[0].source_event_ids


def test_duplicate_bars_and_noncanonical_strategy_signal_halt():
    class BadStrategy:
        manifest = StrategyManifest("bad", "v1", frozenset({Market.KR}), (DataRequirement("market.bar", STEP),))
        def on_event(self, e, c):
            return []  # contract violation, list is mutable
    bad = StrategyRunner(BadStrategy(), StaticSessionCalendar((SESS,)))
    with pytest.raises(InvalidEvent, match="immutable"):
        bad.accept(event(0))
    assert bad.halt_reason is not None
    with pytest.raises(InvalidEvent, match="halted"):
        bad.accept(event(1))

    class ValidStrategy:
        manifest = StrategyManifest("ok", "v1", frozenset({Market.KR}), (DataRequirement("market.bar", STEP),))
        def on_event(self, e, c):
            return ()
    runner = StrategyRunner(ValidStrategy(), StaticSessionCalendar((SESS,)))
    runner.accept(event(0))
    with pytest.raises(InvalidEvent, match="duplicate bar"):
        runner.accept(replace(event(0), event_id="different", ingest_ordinal=1))
    assert runner.halt_reason is not None


def test_unfinalized_bar_never_appears_in_feature_store():
    reg = FeatureRegistry((FeatureDefinition("ema1", FeatureKind.EMA, STEP, 1),))
    invalid = event(0, finalized=False)
    obs = BarObservation(invalid.event_id, INST, invalid.payload, invalid.available_at, SESS)
    with pytest.raises(ValueError, match="unfinalized"):
        reg.compute(INST, invalid.available_at, (obs,))


def test_recursive_cache_matches_reference_on_prefixes_revisions_and_trim():
    from decimal import ROUND_DOWN, localcontext
    from invest_engine.features.technical import atr, ema

    observations = []
    for i in range(80):
        start = T + STEP*i
        price = D("90") + D(i % 11) / D("7")
        bar = Bar(start, start+STEP, price, price+D("0.43"), price-D("0.19"),
                  price, D(i+5), interval=STEP)
        observations.append(BarObservation(str(i), INST, bar, bar.end, SESS))
    reg = FeatureRegistry((
        FeatureDefinition("ema7", FeatureKind.EMA, STEP, 7),
        FeatureDefinition("atr7", FeatureKind.ATR, STEP, 7),
    ))

    def check(history, now):
        expected = {"ema7": ema([b.bar for b in history], 7),
                    "atr7": atr([b.bar for b in history], 7)}
        actual = reg.compute(INST, now, tuple(history))
        assert {v.name: v.value for v in actual} == expected
        assert all(v.source_event_ids == tuple(b.event_id for b in history) for v in actual)

    for end in range(8, 81):
        check(observations[:end], observations[end-1].known_at)
    check(observations, observations[-1].known_at)
    check(observations[5:], observations[-1].known_at)
    check(observations[:20], observations[19].known_at)
    corrected = list(observations)
    corrected[5] = replace(corrected[5], bar=replace(corrected[5].bar, volume=D("999")))
    check(corrected, corrected[-1].known_at)
    with localcontext() as ctx:
        ctx.rounding = ROUND_DOWN
        check(corrected, corrected[-1].known_at)
    check(corrected, corrected[-1].known_at)


def test_recursive_cache_does_not_accept_overlapping_suffix():
    reg = FeatureRegistry((FeatureDefinition("atr2", FeatureKind.ATR, STEP, 2),))
    es = [event(i) for i in range(3)]
    bars = tuple(BarObservation(e.event_id, INST, e.payload, e.received_at, SESS) for e in es)
    reg.compute(INST, bars[-1].known_at, bars)
    duplicate = replace(bars[-1], event_id="duplicate")
    with pytest.raises(ValueError, match="overlaps"):
        reg.compute(INST, bars[-1].known_at, (*bars, duplicate))
