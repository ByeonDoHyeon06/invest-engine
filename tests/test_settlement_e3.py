"""E3.4 deterministic synthetic costs and explicit SELL proceeds confirmation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.core.replay import _canonical
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.codec import decode_trade_event, encode_trade_event
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.ledger import (
    CashSettlementConfirmed, PendingSettlement, TradingEvent, TradingStatus,
    audit_trading_state,
)
from invest_engine.trading.models import (
    DecisionStatus, OrderIntent, SellSettlementMode, Side, TradingConfig,
)
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.runtime import TradingRuntime

T = datetime(2026, 11, 16, 1, tzinfo=timezone.utc)
KR = InstrumentId(Market.KR, "KRX", "KR7005930003", "005930", "KRW")
US = InstrumentId(Market.US, "NASDAQ", "US0378331005", "AAPL", "USD")
WIDE = RiskLimits(
    per_trade_planned_loss=D("1"), max_symbol_cost_fraction=D("1"),
    max_total_cost_fraction=D("1"),
)


def configuration(
    *, tax: str = "0.0025", mode: SellSettlementMode = SellSettlementMode.EXPLICIT_CONFIRMATION,
) -> TradingConfig:
    return TradingConfig(
        "synthetic", (MonetaryRules("KRW", D("1")), MonetaryRules("USD", D("0.01"))),
        ((KR.key, InstrumentRules(D("1"), D("1"))),
         (US.key, InstrumentRules(D("0.01"), D("1")))),
        D("0.001"), D(tax), mode,
    )


def engine(*, journal: SQLiteTradingJournal | None = None,
           config: TradingConfig | None = None) -> TradingRuntime:
    return TradingRuntime(
        config or configuration(),
        (Money(D("100000"), "KRW"), Money(D("1000"), "USD")),
        WIDE, journal=journal, checkpoint_interval=2,
    )


def seed_sale(run: TradingRuntime) -> None:
    buy = OrderIntent("buy", "synthetic", "fixture", KR, Side.BUY,
                      D("10"), D("7000"), T, D("6800"))
    assert run.submit(buy).decision.decision is DecisionStatus.APPROVED
    run.accept_simulated("buy", T + timedelta(seconds=1))
    run.fill_simulated("buy", price=D("7000"), quantity=D("10"),
                       execution_id="fill-buy", at=T + timedelta(seconds=2))
    sell = OrderIntent("sell", "synthetic", "fixture", KR, Side.SELL,
                       D("4"), D("8000"), T + timedelta(seconds=3))
    assert run.submit(sell).decision.decision is DecisionStatus.APPROVED
    run.accept_simulated("sell", T + timedelta(seconds=4))
    run.fill_simulated("sell", price=D("8000"), quantity=D("4"),
                       execution_id="fill-sell", at=T + timedelta(seconds=5))


def test_sell_tax_and_unsettled_cash_are_separate_from_buying_power() -> None:
    run = engine()
    seed_sale(run)
    cash = run.state.account("KRW")
    assert cash.settled == D("29930")
    assert cash.unsettled == D("31888")
    assert cash.available == D("29930")
    assert run.state.pending_settlements == (
        PendingSettlement("fill-sell", "KRW", D("31888"), T + timedelta(seconds=5)),
    )
    charges = run.state.charges
    assert charges[0].gross == D("70000")
    assert charges[0].fee == D("70")
    assert charges[0].tax == 0
    assert charges[1].gross == D("32000")
    assert charges[1].fee == D("32")
    assert charges[1].tax == D("80")
    assert charges[1].cash_delta == D("31888")
    assert run.state.position(KR).realized_pnl == D("3860")  # type: ignore[union-attr]
    # Sale proceeds do NOT fund a new buy until explicitly confirmed.
    restricted = OrderIntent("second-buy", "synthetic", "fixture", KR,
                             Side.BUY, D("5"), D("7000"),
                             T + timedelta(seconds=6), D("6800"))
    assert run.submit(restricted).decision.reason_codes == ("INSUFFICIENT_BUYING_POWER",)
    assert run.confirm_cash_settlement("fill-sell", T + timedelta(seconds=7))
    assert run.state.account("KRW").settled == D("61818")
    assert run.state.account("KRW").unsettled == 0
    assert not run.state.pending_settlements
    assert run.submit(replace(restricted, intent_id="third-buy",
                              submitted_at=T + timedelta(seconds=8))).decision.decision is DecisionStatus.APPROVED
    audit_trading_state(run.state)


def test_settlement_confirmation_idempotent_and_replayable(tmp_path) -> None:
    path = tmp_path / "trade.sqlite"
    with SQLiteTradingJournal(path) as journal:
        run = engine(journal=journal)
        seed_sale(run)
        saved_digest = run.state.digest
        assert len(run.state.pending_settlements) == 1
    with SQLiteTradingJournal(path) as journal:
        run = engine(journal=journal)
        assert run.state.digest == saved_digest
        assert run.state.account("KRW").unsettled == D("31888")
        assert run.confirm_cash_settlement("fill-sell", T + timedelta(seconds=6))
        assert not run.confirm_cash_settlement("fill-sell", T + timedelta(seconds=6))
        settle_events = [e for e in journal._read()
                         if isinstance(e.payload, CashSettlementConfirmed)]
        assert len(settle_events) == 1
        assert decode_trade_event(encode_trade_event(settle_events[0])) == settle_events[0]
        digest = run.state.digest
    with SQLiteTradingJournal(path) as journal:
        restored = engine(journal=journal)
        assert restored.state.digest == digest
        assert restored.state.account("KRW").unsettled == 0
        assert restored.state.account("KRW").settled == D("61818")
        assert not restored.confirm_cash_settlement("fill-sell", T + timedelta(seconds=10))


def test_confirmation_of_unknown_or_premature_execution_halts() -> None:
    run = engine()
    seed_sale(run)
    with pytest.raises(InvalidEvent, match="no eligible"):
        run.confirm_cash_settlement("missing", T + timedelta(seconds=6))
    assert run.state.status is TradingStatus.HALTED
    other = engine()
    seed_sale(other)
    with pytest.raises(InvalidEvent, match="no eligible"):
        other.confirm_cash_settlement("fill-sell", T + timedelta(seconds=1))
    assert other.state.status is TradingStatus.HALTED


def test_tax_and_settlement_policy_pinned_to_journal(tmp_path) -> None:
    path = tmp_path / "pinned.sqlite"
    with SQLiteTradingJournal(path) as journal:
        run = engine(journal=journal)
        seed_sale(run)
    for altered in (
        configuration(tax="0.001"),
        configuration(mode=SellSettlementMode.IMMEDIATE),
    ):
        with SQLiteTradingJournal(path) as journal, pytest.raises(InvalidEvent, match="differs"):
            engine(journal=journal, config=altered)


def test_old_default_config_identity_compatibility() -> None:
    config = configuration(tax="0", mode=SellSettlementMode.IMMEDIATE)
    run = engine(config=config)
    old_config = _canonical(config)
    old_config.pop("sell_tax_rate")
    old_config.pop("sell_settlement_mode")
    old_limits = {
        "per_trade_planned_loss": WIDE.per_trade_planned_loss,
        "max_symbol_cost_fraction": WIDE.max_symbol_cost_fraction,
        "max_total_cost_fraction": WIDE.max_total_cost_fraction,
        "max_open_positions": WIDE.max_open_positions,
        "require_stop_plan": WIDE.require_stop_plan,
    }
    payload = _canonical({"config": old_config, "starting_cash": run.state.cash,
                          "risk_limits": old_limits})
    legacy_hash = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                               ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    assert SQLiteTradingJournal._identity(config, run.state, WIDE) == legacy_hash


def test_immediate_default_does_not_hold_sell_proceeds() -> None:
    run = engine(config=configuration(tax="0", mode=SellSettlementMode.IMMEDIATE))
    seed_sale(run)
    assert run.state.account("KRW").settled == D("61898")
    assert run.state.account("KRW").unsettled == 0
    assert run.state.pending_settlements == ()
    assert run.state.charges[-1].tax == 0


def test_usd_synthetic_cash_quantization_and_no_cross_currency_settlement() -> None:
    config = configuration(tax="0.003")
    run = engine(config=config)
    order = OrderIntent("us-buy", "synthetic", "fixture", US,
                        Side.BUY, D("1"), D("100"), T, D("99"))
    run.submit(order)
    run.accept_simulated("us-buy", T + timedelta(seconds=1))
    run.fill_simulated("us-buy", price=D("100"), quantity=D("1"),
                       execution_id="usf", at=T + timedelta(seconds=2))
    sell = OrderIntent("us-sell", "synthetic", "fixture", US,
                       Side.SELL, D("1"), D("103.21"), T + timedelta(seconds=3))
    run.submit(sell)
    run.accept_simulated("us-sell", T + timedelta(seconds=4))
    run.fill_simulated("us-sell", price=D("103.21"), quantity=D("1"),
                       execution_id="usfs", at=T + timedelta(seconds=5))
    assert run.state.charges[-1].fee == D("0.10")
    assert run.state.charges[-1].tax == D("0.31")
    assert run.state.account("USD").unsettled == D("102.80")
    assert run.state.account("KRW").unsettled == 0
    run.confirm_cash_settlement("usfs", T + timedelta(seconds=6))
    assert run.state.account("USD").settled == D("1002.70")
    assert run.state.account("KRW").settled == D("100000")


def test_invalid_rates_and_mode_rejected() -> None:
    with pytest.raises(ValueError):
        configuration(tax="-0.01")
    with pytest.raises(ValueError):
        configuration(tax="1")
    with pytest.raises(ValueError):
        configuration(tax="0.9999")
    with pytest.raises(ValueError):
        TradingConfig("synthetic", (), (), sell_settlement_mode="not-a-mode")  # type: ignore[arg-type]


def test_structural_audit_detects_tampered_balances() -> None:
    run = engine()
    seed_sale(run)
    bad = replace(run.state, cash=tuple(
        replace(b, unsettled=b.unsettled + D("1")) if b.currency == "KRW" else b
        for b in run.state.cash
    ))
    with pytest.raises(InvalidEvent, match="unsettled cash"):
        audit_trading_state(bad)
    corrupted = replace(run.state, charges=())
    with pytest.raises(InvalidEvent, match="fill or charge"):
        audit_trading_state(corrupted)


def test_codec_new_settlement_event_round_trip() -> None:
    event = TradingEvent("settle:test", 4, T + timedelta(seconds=10),
                         CashSettlementConfirmed("execution-99"))
    assert decode_trade_event(encode_trade_event(event)) == event
