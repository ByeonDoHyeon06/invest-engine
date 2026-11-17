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


def test_real_orb_plugin_causal_integration_21_synthetic_sessions():
    """E2→E4 ORB/ATR/volume→E3 risk/fill, requiring twenty past sessions."""
    from invest_engine.strategies.orb import ORBLongStrategy

    sessions = tuple(TradingSession(Market.KR, "KRX", T+timedelta(days=d),
                                    T+timedelta(days=d, hours=1)) for d in range(21))
    events = []
    for day, session in enumerate(sessions):
        for minute in range(7):
            start = session.start + minute*STEP
            breakout = day == 20 and minute == 5
            after = day == 20 and minute == 6
            bar = Bar(start, start+STEP, D("99"), D("105") if after else D("102") if breakout else D("100"),
                      D("95"), D("100") if after else D("101") if breakout else D("99"),
                      D("1000") if after else D("30") if breakout else D("10"), interval=STEP)
            end = start + STEP
            events.append(EventEnvelope(f"orb:{day}:{minute}", "market.bar", "synthetic",
                                        INST, end, end, end, len(events), bar))
    cfg = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                        ((INST.key, InstrumentRules(D("1"), D("1"))),), fee_rate=D("0.001"))
    result = HistoricalBacktest(
        calendar=StaticSessionCalendar(sessions), strategies=(ORBLongStrategy(),),
        config=cfg, opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5"),
                        max_symbol_cost_fraction=D("0.2"), max_total_cost_fraction=D("0.5")),
    ).run(tuple(events))
    assert result.decisions[-2].signal_ids
    assert result.decisions[-2].fills == ()
    assert result.decisions[-1].fills
    assert result.entry_fill_count == 1


def protection_runner(*, reward: str | None = "1.5", adverse: str = "0",
                      participation: str = "0.05", exit_on: int | None = None) -> HistoricalBacktest:
    """Opt-in OHLCV protection: no live stop order or brokerage assumption."""
    from invest_engine.research.protection import ProtectionPolicy

    config = TradingConfig(
        "sim", (MonetaryRules("KRW", D("1")),),
        ((INST.key, InstrumentRules(D("1"), D("1"))),), fee_rate=D("0.001"),
    )
    return HistoricalBacktest(
        calendar=StaticSessionCalendar((TradingSession(Market.KR, "KRX", T, T+timedelta(hours=1)),)),
        strategies=(SignalOnFirstBar(exit_on=exit_on),), config=config,
        opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5"),
                        max_symbol_cost_fraction=D("0.2"), max_total_cost_fraction=D("0.5")),
        fill_policy=BarFillPolicy(participation=D(participation)),
        protection_policy=ProtectionPolicy(
            enabled=True, reward_multiple=D(reward) if reward is not None else None,
            adverse_bps=D(adverse)),
    )


def test_e5_protection_collision_stop_first_and_reproducible():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "1000"),
        ("101", "120", "80", "101", "1000"),
    ))
    result = protection_runner().run(events)
    assert result.entry_fill_count == 1
    assert result.exit_fill_count == 1
    assert result.fills[-1].reason_code == "STOP_FIRST_COLLISION"
    assert result.fills[-1].price == D("90")  # not favorable 115 target
    assert dict(result.by_currency_end) == {"KRW": D("99490")}
    assert result.decisions[1].fills and result.decisions[2].fills
    assert protection_runner().run(events).run_sha256 == result.run_sha256


def test_e5_gap_below_stop_is_not_filled_at_favorable_stop():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "1000"),
        ("70", "80", "60", "70", "1000"),
    ))
    normal = protection_runner().run(events)
    adverse = protection_runner(adverse="100").run(events)
    assert normal.fills[-1].price == D("70")
    assert normal.fills[-1].reason_code == "GAP_BELOW_STOP"
    assert adverse.fills[-1].price == D("69")  # 69.3 -> floor to one KRW tick
    assert dict(adverse.net_pnl)["KRW"] < dict(normal.net_pnl)["KRW"]


def test_e5_only_target_reached_conservative_no_price_improvement():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "1000"),
        ("116", "120", "98", "117", "1000"),
    ))
    result = protection_runner().run(events)
    assert result.fills[-1].reason_code == "TARGET_TRIGGERED"
    assert result.fills[-1].price == D("115")  # no generous gap-open improvement
    assert dict(result.net_pnl)["KRW"] > 0


def test_e5_protection_begins_after_entry_observation_not_same_bar():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "70", "101", "100000"),  # full entry at observation; no protection yet
        ("101", "103", "91", "101", "1000"),
    ))
    result = protection_runner().run(events)
    assert result.entry_fill_count == 1
    assert result.exit_fill_count == 0
    assert all(not v.reason_code.startswith("STOP_") for v in result.fills)


def test_e5_volume_limited_protection_partial_across_bars():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "100000"),  # enough to fully fill BUY
        ("101", "103", "85", "90", "20"),
        ("89", "95", "80", "89", "20"),
        ("89", "96", "78", "88", "2000"),
    ))
    result = protection_runner(participation="0.10").run(events)
    assert result.entry_fill_count == 1
    assert result.exit_fill_count == 3
    assert tuple(x.quantity for x in result.fills[1:]) == (D("2"), D("2"), D("96"))
    assert result.fills[1].price == D("90")
    assert result.fills[2].price == D("89")
    assert result.fills[3].price == D("89")  # open gap below stop in final bar
    assert dict(result.by_currency_end)["KRW"] < D("100000")


def test_e5_protection_policy_validation_and_explicit_sell_conflict():
    from invest_engine.research.protection import ProtectionPolicy

    with pytest.raises(ValueError):
        ProtectionPolicy(enabled=True, reward_multiple=D("-1"))
    with pytest.raises(ValueError):
        ProtectionPolicy(enabled=True, adverse_bps=D("10000"))
    with pytest.raises(ValueError):
        ProtectionPolicy(enabled=True, adverse_bps=D("NaN"))


def test_e5_rejects_unresolvable_intrabar_competing_sell():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "100000"),  # full entry
        ("101", "103", "95", "101", "1000"),  # strategy EXIT proposed at close
        ("100", "103", "80", "100", "1000"),  # existing SELL and stop both eligible
    ))
    with pytest.raises(InvalidEvent, match="unresolvable protective exit"):
        protection_runner(exit_on=2).run(events)


def test_e5_no_target_when_reward_multiple_not_configured():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "100000"),
        ("115", "125", "91", "119", "1000"),
    ))
    result = protection_runner(reward=None).run(events)
    assert result.exit_fill_count == 0  # high >= 115 is NOT an automatic target


def test_e5_filled_strategy_exit_releases_protection_before_later_stop():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "100000"),
        ("101", "103", "95", "101", "1000"),
        ("101", "103", "99", "101", "100000"),
        ("89", "95", "80", "89", "1000"),
    ))
    result = protection_runner(exit_on=2).run(events)
    assert result.entry_fill_count == 1
    assert result.exit_fill_count == 1
    assert result.fills[-1].reason_code == "LIMIT_FILLED"
    assert all(x.reason_code != "GAP_BELOW_STOP" for x in result.fills)
    assert dict(result.net_pnl)["KRW"] > 0


def test_e5_target_touch_only_not_assumed_filled():
    events = feed(prices=(
        ("100", "100", "100", "100", "1000"),
        ("101", "103", "95", "101", "100000"),
        ("110", "115", "91", "114", "1000"),  # exactly touches target=115
    ))
    result = protection_runner().run(events)
    assert result.exit_fill_count == 0
    assert all(x.reason_code != "TARGET_TRIGGERED" for x in result.fills)


def test_optional_multicurrency_fx_reporting_and_strict_miss():
    from invest_engine.research.fx import FxObservation, FxReportingPolicy, FxSeries

    inst_usd = InstrumentId(Market.US, "XNAS", "US-SYN-E5", "SYNU", "USD")
    cfg = TradingConfig("sim", (
        MonetaryRules("KRW", D("1")), MonetaryRules("USD", D("0.01")),
    ), ((INST.key, InstrumentRules(D("1"), D("1"))),
        (inst_usd.key, InstrumentRules(D("0.01"), D("1")))), fee_rate=D("0.001"))
    calendar = StaticSessionCalendar((TradingSession(Market.KR, "KRX", T,
                                              T + timedelta(hours=1)),))
    one, two = T + STEP, T + STEP*2
    fx = FxSeries((FxObservation("usd1", "USD", "KRW", D("1300"),
                        one, one, one, "synthetic"),
                   FxObservation("usd2", "USD", "KRW", D("1400"),
                        two, two, two, "synthetic")))

    def run(series: FxSeries, max_age: timedelta):
        return HistoricalBacktest(calendar=calendar,
            strategies=(NoTradeStrategy(DataRequirement("market.bar", STEP)),),
            config=cfg, opening_cash=(Money(D("100000"), "KRW"),
                                      Money(D("100"), "USD")),
            fx_series=series, fx_policy=FxReportingPolicy("KRW", max_age)).run(feed()[:2])

    report = run(fx, timedelta(minutes=2))
    assert report.fx_base_currency == "KRW"
    assert [x.value for x in report.fx_equity] == [D("230000"), D("240000")]
    assert report.fx_net_pnl == D("10000")
    assert report.fx_max_drawdown == 0
    assert report.fx_data_sha256 == fx.digest
    assert run(fx, timedelta(minutes=2)).run_sha256 == report.run_sha256
    incomplete = run(FxSeries((fx.observations[1],)), timedelta(minutes=2))
    assert incomplete.fx_net_pnl is None
    assert incomplete.fx_max_drawdown is None
    assert incomplete.fx_equity[0].value is None
    assert incomplete.by_currency_end == report.by_currency_end
