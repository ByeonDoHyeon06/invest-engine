"""Golden fixture for external E3 input contract, with strict rejection rules."""
import json
from decimal import Decimal

import pytest

from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.trading.models import OrderType, TimeInForce
from invest_engine.trading.wire import decode_order_intent


FIXTURE = {
    "schema_version": "e3-sim-v1",
    "kind": "PROPOSE_ORDER_INTENT",
    "command_id": "cmd-0001",
    "account_id": "sim-account-1",
    "strategy_ref": "synthetic-fixture",
    "instrument": {"market": "KR", "venue": "KRX", "identifier": "KR7005930003", "symbol": "005930", "currency": "KRW"},
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": "10",
    "limit_price": {"currency": "KRW", "amount": "7000"},
    "time_in_force": "DAY",
    "stop_plan": {"trigger_price": {"currency": "KRW", "amount": "6800"}, "reason": "SYNTHETIC_STOP_FOR_TEST"},
    "requested_at": "2026-11-16T01:00:00Z",
    "correlation_id": "case-e3-01",
}


def test_golden_wire_intent():
    decoded = decode_order_intent(json.dumps(FIXTURE))
    assert decoded.quantity == Decimal("10")
    assert decoded.order_type is OrderType.LIMIT
    assert decoded.time_in_force is TimeInForce.DAY
    assert decoded.instrument.currency == "KRW"


@pytest.mark.parametrize("key", ["extra", "broker_token", "live_mode"])
def test_unknown_fields_rejected(key):
    record = dict(FIXTURE, **{key: "not-permitted"})
    with pytest.raises(InvalidEvent):
        decode_order_intent(json.dumps(record))


def test_float_wire_decimal_rejected():
    record = dict(FIXTURE, quantity=10.0)
    with pytest.raises(InvalidEvent):
        decode_order_intent(json.dumps(record))


def test_currency_mismatch_rejected():
    record = dict(FIXTURE, limit_price={"currency": "USD", "amount": "7000"})
    with pytest.raises(InvalidEvent, match="currency"):
        decode_order_intent(json.dumps(record))


def test_unknown_schema_version_refused():
    record = dict(FIXTURE, schema_version="e4-live-v1")
    with pytest.raises(UnsupportedData):
        decode_order_intent(json.dumps(record))
