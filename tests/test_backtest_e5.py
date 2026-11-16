from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.fills import BarFillPolicy
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.strategies.contracts import (
    DataRequirement, SignalDirection, StrategyContext, StrategyManifest, StrategySignal,
)
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits

T = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)
STEP = timedelta(minutes=1)
INST = InstrumentId(Market.KR, "KRX", "KR-SYN-E5", "SYN", "KRW")


class SignalOnFirstBar:
    def __init__(self, *, exit_on: int | None = None) -> None:
        self.exit_on = exit_on
        self._manifest = StrategyManifest(
            "fixture", "1", frozenset({Market.KR}),
            (DataRequirement("market.bar", STEP),),
        )

    @property
    def manifest(self) -> StrategyManifest:
        return self._manifest

    def on_event(self, event: EventEnvelope, context: StrategyContext) -> tuple[StrategySignal, ...]:
        bar = event.payload
        n = int((bar.start-T) / STEP)
        if n != 0 and n != self.exit_on:
            return ()
        exit_now = n == self.exit_on
        return (StrategySignal(
            f"sig:{n}", "fixture", "1", INST,
            SignalDirection.EXIT if exit_now else SignalDirection.LONG,
            D("0") if exit_now else D("0.10"),
            context.as_of, context.as_of + timedelta(minutes=10),
            event.event_id, None if exit_now else D("90"),
        ),)

    def snapshot(self) -> bytes:
        return b"fixture-v1"

    def restore(self, data: bytes) -> None:
        if data != self.snapshot():
            raise ValueError("bad strategy state")


def feed(*, prices: tuple[tuple[str, str, str, str, str], ...] | None = None):
    rows = prices or (
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "1000"),
        ("101", "103", "95", "101", "1000"),
        ("101", "103", "99", "101", "1000"),
        ("101", "103", "99", "101", "1000"),
    )
    events = []
    for i, (open_, high, low, close, volume) in enumerate(rows):
        start = T + i*STEP
        bar = Bar(start, start+STEP, D(open_), D(high), D(low),
                  D(close), D(volume), interval=STEP)
        end = start+STEP
        events.append(EventEnvelope(f"bar:{i}", "market.bar", "synthetic", INST,
                                    end, end, end, i, bar))
    return tuple(events)


def make_runner(*, fee: str = "0.001", fill: BarFillPolicy | None = None,
                exit_on: int | None = None, no_trade: bool = False) -> HistoricalBacktest:
    config = TradingConfig(
        "sim", (MonetaryRules("KRW", D("1")),),
        ((INST.key, InstrumentRules(D("1"), D("1"))),),
        fee_rate=D(fee),
    )
    strategy = NoTradeStrategy(DataRequirement("market.bar", STEP)) if no_trade else SignalOnFirstBar(exit_on=exit_on)
    return HistoricalBacktest(
        calendar=StaticSessionCalendar((TradingSession(Market.KR, "KRX", T, T+timedelta(hours=1)),)),
        strategies=(strategy,), config=config,
        opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.50"),
                        max_symbol_cost_fraction=D("0.20"), max_total_cost_fraction=D("0.50")),
        fill_policy=fill,
    )


def test_no_same_bar_fill_and_equity_after_next_bar():
    report = make_runner().run(feed()[:2])
    assert report.entry_fill_count == 1
    assert report.exit_fill_count == 0
    assert report.decisions[0].signal_ids == ("sig:0",)
    assert report.decisions[0].fills == ()
    assert report.decisions[1].fills == ("e5:bar:1:allocation:" + report.decisions[0].intent_ids[0].split(":")[-1],)
    assert dict(report.by_currency_end)["KRW"] == D("100045")
    assert dict(report.total_fees)["KRW"] == D("5")
    assert report.equity[0].complete


def test_volume_limited_partial_fills_and_bar_touches_not_enough():
    report = make_runner(fill=BarFillPolicy(participation=D("0.01"))).run(feed())
    assert report.entry_fill_count == 4  # four 10-share partial fills
    assert all(x.fills == () for x in report.decisions[:1])
    assert report.run_sha256
    untouched = make_runner(fill=BarFillPolicy(spread_bps=D("0"), impact_bps=D("0"))).run(
        feed(prices=(("100", "100", "100", "100", "1000"),
                     ("100", "100", "100", "100", "1000"))))
    assert untouched.entry_fill_count == 0


def test_slippage_penetration_sensitivity_and_fees():
    regular = make_runner().run(feed()[:2])
    conservative = make_runner(fill=BarFillPolicy(spread_bps=D("400"), impact_bps=D("400"))).run(feed()[:2])
    assert regular.entry_fill_count == 1
    assert conservative.entry_fill_count == 0
    cheap = make_runner(fee="0").run(feed()[:2])
    assert dict(cheap.by_currency_end)["KRW"] > dict(regular.by_currency_end)["KRW"]


def test_deterministic_and_same_instance_refused(tmp_path: Path):
    first = make_runner()
    a = first.run(feed())
    b = make_runner().run(feed())
    assert a == b
    assert a.run_sha256 == b.run_sha256
    a.export(tmp_path)
    assert "dataset_sha256" in (tmp_path / "report.json").read_text()
    assert len((tmp_path / "decisions.jsonl").read_text().splitlines()) == 5
    with pytest.raises(RuntimeError, match="single-use"):
        first.run(feed())


def test_no_trade_baseline_and_rejected_input():
    report = make_runner(no_trade=True).run(feed())
    assert report.entry_fill_count == report.exit_fill_count == 0
    assert dict(report.by_currency_end) == {"KRW": D("100000")}
    with pytest.raises(InvalidEvent, match="unfinalized"):
        old = feed()
        make_runner().run((replace(old[0], payload=replace(old[0].payload, finalized=False)),))
    with pytest.raises(InvalidEvent, match="ordinal"):
        old = feed()
        make_runner().run((old[0], replace(old[1], ingest_ordinal=5)))


def test_exit_signals_require_next_bar_and_attribute():
    report = make_runner(exit_on=2).run(feed())
    assert report.entry_fill_count == 2
    assert report.exit_fill_count == 2
    assert report.decisions[2].signal_ids == ("sig:2",)
    assert all("bar:2" in x for x in report.decisions[2].fills)  # prior BUY, not fresh EXIT
    assert report.decisions[3].fills
    assert dict(report.by_currency_end)["KRW"] >= D("100000")
    assert dict(report.realized_exit_pnl)["KRW"] > 0


def test_unsupported_cross_currency_aggregates_nothing():
    report = make_runner(no_trade=True).run(feed())
    assert report.by_currency_start == (("KRW", D("100000")),)
    assert report.by_currency_end == (("KRW", D("100000")),)


def test_fill_policy_validates_numbers():
    with pytest.raises(ValueError):
        BarFillPolicy(participation=D("0"))
    with pytest.raises(ValueError):
        BarFillPolicy(spread_bps=D("-1"))
