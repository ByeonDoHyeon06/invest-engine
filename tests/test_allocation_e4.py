from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.strategies.allocation import (
    AllocationPolicy, allocate_targets, propose_simulated_intents,
)
from invest_engine.strategies.contracts import SignalDirection, StrategySignal
from invest_engine.trading.models import DecisionStatus, TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.monitoring import MarketMark
from invest_engine.trading.runtime import TradingRuntime

T = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
KR = InstrumentId(Market.KR, "KRX", "KR-SYN-0001", "005930", "KRW")
US = InstrumentId(Market.US, "XNAS", "US-SYN-0001", "AAPL", "USD")


def signal(name: str, sid: str, *, symbol=KR, target="0.02", direction=SignalDirection.LONG):
    return StrategySignal(sid, name, "1.0.0", symbol, direction, D(target), T,
                          T + timedelta(minutes=5), sid + ":event",
                          D("95") if direction is SignalDirection.LONG else None)


def sim():
    cfg = TradingConfig("sim-account", (MonetaryRules("KRW", D("1")), MonetaryRules("USD", D("0.01"))),
                        ((KR.key, InstrumentRules(D("1"), D("1"))),
                         (US.key, InstrumentRules(D("0.01"), D("1")))))
    return TradingRuntime(cfg, (Money(D("1000000"), "KRW"), Money(D("1000"), "USD"))), cfg


def test_same_symbol_signals_do_not_create_duplicate_orders():
    allocations = allocate_targets((signal("orb", "s1"), signal("ema", "s2")), as_of=T)
    assert len(allocations.plans) == 1
    assert allocations.plans[0].target_fraction == D("0.04")
    assert len(allocations.plans[0].strategy_targets) == 2
    eng, config = sim()
    marks = (MarketMark(KR, D("100"), T, "fixture"),)
    proposed = propose_simulated_intents(allocations.plans, state=eng.state, config=config, marks=marks, as_of=T)
    assert len(proposed) == 1
    assert proposed[0].quantity == D("400")
    assert proposed == propose_simulated_intents(allocations.plans, state=eng.state, config=config, marks=marks, as_of=T)
    assert eng.submit(proposed[0]).decision.decision is DecisionStatus.APPROVED
    assert propose_simulated_intents(allocations.plans, state=eng.state, config=config, marks=marks, as_of=T) == ()


def test_exit_overrides_long():
    r = allocate_targets((signal("orb", "s1"), signal("exit", "s2", target="0", direction=SignalDirection.EXIT)), as_of=T)
    assert r.plans[0].target_fraction == 0
    assert r.reason_codes == ("EXIT_TAKES_PRECEDENCE",)


def test_capped_or_overbudget_rejected():
    r = allocate_targets((signal("a", "s1", target="0.2"),), as_of=T)
    assert r.plans[0].target_fraction == D("0.10")
    assert "SYMBOL_TARGET_CAPPED" in r.reason_codes
    policy = AllocationPolicy(max_currency_fraction=D("0.01"))
    assert allocate_targets((signal("a", "s1"),), as_of=T, policy=policy).reason_codes == ("CURRENCY_TARGET_EXCEEDED",)


def test_cross_currency_does_not_auto_convert():
    r = allocate_targets((signal("a", "s1"), signal("b", "s2", symbol=US)), as_of=T)
    assert len(r.plans) == 2
    eng, cfg = sim()
    proposals = propose_simulated_intents(r.plans, state=eng.state, config=cfg,
                                         marks=(MarketMark(KR, D("100"), T, "fixture"),
                                                MarketMark(US, D("100"), T, "fixture")), as_of=T)
    assert proposals[0].quantity == D("200")
    assert len(proposals) == 1  # USD 1,000 cannot buy even one 100 USD lot at 2% target
    assert proposals[0].instrument.currency == "KRW"
    assert eng.state.account("USD").settled == D("1000")


def test_stale_or_missing_mark_no_order():
    r = allocate_targets((signal("a", "s1"),), as_of=T)
    eng, cfg = sim()
    assert propose_simulated_intents(r.plans, state=eng.state, config=cfg, marks=(), as_of=T) == ()
    assert propose_simulated_intents(r.plans, state=eng.state, config=cfg,
                                    marks=(MarketMark(KR, D("100"), T - timedelta(minutes=4), "fixture"),), as_of=T) == ()


def test_duplicate_signal_and_policy_validation():
    with pytest.raises(ValueError):
        allocate_targets((signal("a", "s1"), signal("b", "s1")), as_of=T)
    with pytest.raises(ValueError):
        AllocationPolicy(max_symbol_fraction=D("1.1"))


def test_proposal_can_size_against_explicit_marked_currency_equity():
    allocations = allocate_targets(
        (signal("portfolio", "usd-1", symbol=US, target="0.10"),),
        as_of=T,
    )
    engine, config = sim()
    marks = (MarketMark(US, D("100"), T, "fixture"),)

    legacy = propose_simulated_intents(
        allocations.plans,
        state=engine.state,
        config=config,
        marks=marks,
        as_of=T,
    )
    marked = propose_simulated_intents(
        allocations.plans,
        state=engine.state,
        config=config,
        marks=marks,
        as_of=T,
        target_equity_by_currency=(("USD", D("2500")),),
    )

    assert legacy[0].quantity == D("1")
    assert marked[0].quantity == D("2")


@pytest.mark.parametrize(
    "equity",
    (
        (("USD", D("2500")), ("USD", D("2500"))),
        (("KRW", D("2500")),),
        (("EUR", D("2500")), ("USD", D("2500"))),
        (("USD", 2500),),
        (("USD", D("NaN")),),
        (("USD", D("0")),),
        (("USD", D("-1")),),
    ),
)
def test_marked_equity_requires_unique_supported_positive_currency_rows(equity):
    allocations = allocate_targets(
        (signal("portfolio", "usd-1", symbol=US, target="0.10"),),
        as_of=T,
    )
    engine, config = sim()

    with pytest.raises(ValueError):
        propose_simulated_intents(
            allocations.plans,
            state=engine.state,
            config=config,
            marks=(MarketMark(US, D("100"), T, "fixture"),),
            as_of=T,
            target_equity_by_currency=equity,
        )


def test_omitted_marked_equity_preserves_legacy_proposal():
    allocations = allocate_targets(
        (signal("portfolio", "usd-1", symbol=US, target="0.10"),),
        as_of=T,
    )
    engine, config = sim()
    kwargs = {
        "state": engine.state,
        "config": config,
        "marks": (MarketMark(US, D("100"), T, "fixture"),),
        "as_of": T,
    }

    assert propose_simulated_intents(
        allocations.plans,
        **kwargs,
    ) == propose_simulated_intents(
        allocations.plans,
        target_equity_by_currency=None,
        **kwargs,
    )
