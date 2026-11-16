from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

import pytest

from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.trading.money import InstrumentRules, MonetaryRules, multiply_cash
from invest_engine.trading.models import OrderIntent, Side, SimulatedFill, TradingConfig

D = Decimal
NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
KR = InstrumentId(Market.KR, "KRX", "KR7005930003", "005930", "KRW")


def test_cash_quantization_and_policy_explicit():
    kr = MonetaryRules("KRW", D("1"))
    usd = MonetaryRules("USD", D("0.01"))
    assert kr.settle(D("1.5")) == D("2")
    assert usd.settle(D("0.015")) == D("0.02")
    assert MonetaryRules("KRW", D("1"), rounding=ROUND_DOWN).settle(D("1.9")) == D("1")


def test_instrument_tick_and_lot_rules():
    rule = InstrumentRules(D("5"), D("1"))
    rule.validate_price(D("7000"))
    rule.validate_quantity(D("10"))
    with pytest.raises(ValueError, match="tick"):
        rule.validate_price(D("7001"))
    with pytest.raises(ValueError, match="lot"):
        rule.validate_quantity(D("1.5"))


def test_money_cannot_be_float_or_nan():
    with pytest.raises(ValueError):
        MonetaryRules("USD", D("NaN"))
    with pytest.raises(ValueError):
        multiply_cash(7.01, D("1"))  # type: ignore[arg-type]


def test_order_and_fill_are_strict():
    order = OrderIntent("order-1", "sim", "fixture", KR, Side.BUY, D("10"), D("7000"), NOW, D("6800"))
    assert order.instrument.currency == "KRW"
    with pytest.raises(ValueError, match="stop"):
        OrderIntent("order-2", "sim", "fixture", KR, Side.BUY, D("10"), D("7000"), NOW, D("8000"))
    with pytest.raises(ValueError, match="fee"):
        SimulatedFill("fill1", "order-1", D("1"), D("7000"), D("-1"), NOW)


def test_config_requires_explicit_currency_and_instrument():
    conf = TradingConfig("sim", (MonetaryRules("KRW", D("1")),), ((KR.key, InstrumentRules(D("5"), D("1"))),))
    assert conf.rules_for(KR).lot_size == D("1")
    with pytest.raises(ValueError):
        conf.cash_rules("USD")
