"""Strict E3 order intent JSON boundary, matching documented synthetic fixture.

This is a *simulation command* parser. It never accepts broker credentials,
account tokens or a live mode selector.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market
from invest_engine.trading.models import OrderIntent, OrderType, Side, TimeInForce

SCHEMA_VERSION = "e3-sim-v1"


def _object(value: object, required: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidEvent("expected JSON object")
    if set(value) != required:
        raise InvalidEvent(f"unexpected or missing fields: {sorted(set(value) ^ required)}")
    return cast(dict[str, Any], value)


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise InvalidEvent("decimal wire value must be a string")
    return Decimal(value)


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise InvalidEvent("timestamp must be RFC3339 string")
    if not (value.endswith("Z") or value.endswith("+00:00")):
        raise InvalidEvent("timestamp must be UTC")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decode_order_intent(data: str | bytes) -> OrderIntent:
    try:
        raw = _object(json.loads(data), frozenset({
            "schema_version", "kind", "command_id", "account_id", "strategy_ref",
            "instrument", "side", "order_type", "quantity", "limit_price",
            "time_in_force", "stop_plan", "requested_at", "correlation_id",
        }))
        if raw["schema_version"] != SCHEMA_VERSION or raw["kind"] != "PROPOSE_ORDER_INTENT":
            raise UnsupportedData("unsupported simulation command schema")
        instrument = _object(raw["instrument"], frozenset({
            "market", "venue", "identifier", "symbol", "currency",
        }))
        inst = InstrumentId(Market(instrument["market"]), instrument["venue"],
                            instrument["identifier"], instrument["symbol"],
                            instrument["currency"], AssetClass.EQUITY)
        price = _object(raw["limit_price"], frozenset({"currency", "amount"}))
        if price["currency"] != inst.currency:
            raise InvalidEvent("order price currency does not match instrument")
        stop: Decimal | None = None
        if raw["stop_plan"] is not None:
            stop_plan = _object(raw["stop_plan"], frozenset({"trigger_price", "reason"}))
            stop_price = _object(stop_plan["trigger_price"], frozenset({"currency", "amount"}))
            if stop_price["currency"] != inst.currency:
                raise InvalidEvent("stop currency does not match instrument")
            if not isinstance(stop_plan["reason"], str) or not stop_plan["reason"].strip():
                raise InvalidEvent("stop reason is required")
            stop = _decimal(stop_price["amount"])
        if not isinstance(raw["correlation_id"], str):
            raise InvalidEvent("correlation_id must be string")
        return OrderIntent(
            intent_id=raw["command_id"], account_id=raw["account_id"],
            strategy_ref=raw["strategy_ref"], instrument=inst,
            side=Side(raw["side"]), quantity=_decimal(raw["quantity"]),
            limit_price=_decimal(price["amount"]),
            submitted_at=_datetime(raw["requested_at"]), stop_price=stop,
            order_type=OrderType(raw["order_type"]),
            time_in_force=TimeInForce(raw["time_in_force"]),
        )
    except (InvalidEvent, UnsupportedData):
        raise
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise InvalidEvent(f"malformed E3 intent wire data: {type(exc).__name__}") from exc
