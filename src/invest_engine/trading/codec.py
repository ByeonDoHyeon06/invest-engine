"""Strict, canonical E3 trading-event codec; does not modify E2 market schema."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from invest_engine.core.replay import _canonical
from invest_engine.trading.actions import (
    DelistingObserved, DelistingCashResolved, DividendEntitled, DividendPaymentConfirmed, SplitApplied,
)
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market
from invest_engine.trading.ledger import (
    AccountReconciliationReviewed, CashSettlementConfirmed, EntriesPaused, EntriesResumed, FillRecorded, OrderAccepted, OrderCanceled, OrderCancelPending,
    OrderReconciled, OrderRejected, OrderReserved, OrderUnknown, RiskObserved, TradingEvent,
)
from invest_engine.domain.primitives import Money
from invest_engine.trading.monitoring import (
    ExternalAccountReference, FxMark, MarketMark, MonitorInput,
    ReferencePosition, SessionBaseline,
)
from invest_engine.trading.models import (
    OrderIntent, OrderStatus, OrderType, Side, SimulatedFill, TimeInForce,
)


def encode_trade_event(event: TradingEvent) -> bytes:
    return json.dumps({**_canonical(event), "kind": type(event.payload).__name__}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidEvent("expected object")
    return cast(dict[str, Any], value)


def _instrument(data: dict[str, Any]) -> InstrumentId:
    return InstrumentId(
        market=Market(data["market"]), venue=data["venue"], identifier=data["identifier"],
        symbol=data["symbol"], currency=data["currency"],
        asset_class=AssetClass(data["asset_class"]),
    )


def _intent(data: dict[str, Any]) -> OrderIntent:
    return OrderIntent(
        intent_id=data["intent_id"], account_id=data["account_id"],
        strategy_ref=data["strategy_ref"], instrument=_instrument(_mapping(data["instrument"])),
        side=Side(data["side"]), quantity=Decimal(data["quantity"]),
        limit_price=Decimal(data["limit_price"]),
        submitted_at=datetime.fromisoformat(data["submitted_at"]),
        stop_price=Decimal(data["stop_price"]) if data["stop_price"] is not None else None,
        order_type=OrderType(data["order_type"]),
        time_in_force=TimeInForce(data["time_in_force"]),
    )


def _payload(name: str, data: dict[str, Any]) -> Any:
    if name == "SplitApplied":
        return SplitApplied(data["action_id"], _instrument(_mapping(data["instrument"])),
                            data["numerator"], data["denominator"],
                            datetime.fromisoformat(data["effective_at"]),
                            datetime.fromisoformat(data["available_at"]), data["source"])
    if name == "DividendEntitled":
        return DividendEntitled(data["action_id"], _instrument(_mapping(data["instrument"])),
                                Decimal(data["gross_per_share"]),
                                Decimal(data["withholding_fraction"]),
                                datetime.fromisoformat(data["effective_at"]),
                                datetime.fromisoformat(data["available_at"]), data["source"])
    if name == "DividendPaymentConfirmed":
        return DividendPaymentConfirmed(data["action_id"])
    if name == "DelistingObserved":
        return DelistingObserved(data["action_id"], _instrument(_mapping(data["instrument"])),
                                 datetime.fromisoformat(data["effective_at"]),
                                 datetime.fromisoformat(data["available_at"]), data["source"])
    if name == "DelistingCashResolved":
        return DelistingCashResolved(
            data["action_id"], _instrument(_mapping(data["instrument"])),
            Decimal(data["quantity"]), Decimal(data["net_cash"]),
            datetime.fromisoformat(data["paid_at"]),
            datetime.fromisoformat(data["available_at"]), data["source"],
            data["evidence_sha256"],
        )
    if name == "CashSettlementConfirmed":
        return CashSettlementConfirmed(data["execution_id"])
    if name == "EntriesPaused":
        return EntriesPaused(data["reason"])
    if name == "EntriesResumed":
        return EntriesResumed(data["reviewed_by"])
    if name == "OrderReserved":
        return OrderReserved(_intent(_mapping(data["intent"])), Decimal(data["reserved_cash"]))
    if name == "OrderRejected":
        return OrderRejected(_intent(_mapping(data["intent"])), tuple(data["reason_codes"]))
    if name == "OrderAccepted":
        return OrderAccepted(data["intent_id"])
    if name == "OrderCancelPending":
        return OrderCancelPending(data["intent_id"])
    if name == "OrderCanceled":
        return OrderCanceled(data["intent_id"])
    if name == "OrderUnknown":
        return OrderUnknown(data["intent_id"])
    if name == "OrderReconciled":
        return OrderReconciled(data["intent_id"], OrderStatus(data["status"]))
    if name == "RiskObserved":
        raw = _mapping(data["observation"])
        marks = tuple(MarketMark(
            _instrument(_mapping(v["instrument"])), Decimal(v["price"]),
            datetime.fromisoformat(v["available_at"]), v["source"],
        ) for v in raw["marks"])
        fx_rates = tuple(FxMark(
            v["base"], v["quote"], Decimal(v["rate"]),
            datetime.fromisoformat(v["available_at"]), v["source"],
        ) for v in raw["fx_rates"])
        baselines = tuple(SessionBaseline(
            v["currency"], v["session_id"], Decimal(v["equity"]),
            datetime.fromisoformat(v["started_at"]),
        ) for v in raw["baselines"])
        ref = None
        if raw["reference"] is not None:
            value = _mapping(raw["reference"])
            ref = ExternalAccountReference(
                value["account_id"], datetime.fromisoformat(value["as_of"]),
                tuple(Money(Decimal(v["amount"]), v["currency"]) for v in value["cash"]),
                tuple(ReferencePosition(v["instrument_key"], Decimal(v["quantity"]))
                      for v in value["positions"]),
                tuple(value["open_intent_ids"]) if value["open_intent_ids"] is not None else None,
            )
        return RiskObserved(MonitorInput(
            datetime.fromisoformat(raw["checked_at"]), raw["session_id"],
            raw["base_currency"], marks, fx_rates, baselines, ref,
        ))
    if name == "AccountReconciliationReviewed":
        return AccountReconciliationReviewed(data["reviewed_by"])
    if name == "FillRecorded":
        f = _mapping(data["fill"])
        return FillRecorded(SimulatedFill(
            f["execution_id"], f["intent_id"], Decimal(f["quantity"]),
            Decimal(f["price"]), Decimal(f["fee"]), datetime.fromisoformat(f["occurred_at"]),
        ))
    raise UnsupportedData(f"unsupported trade payload: {name}")


def decode_trade_event(data: bytes) -> TradingEvent:
    try:
        raw = _mapping(json.loads(data))
        payload = _mapping(raw["payload"])
        # Canonical form includes payload fields but not its tag. Explicit discriminators
        # are part of our E3 wire envelope; never infer a type from field shapes.
        result = TradingEvent(
            raw["event_id"], int(raw["ordinal"]),
            datetime.fromisoformat(raw["occurred_at"]),
            _payload(str(raw["kind"]), payload), int(raw["schema_version"]),
        )
        if encode_trade_event(result) != data:
            raise InvalidEvent("noncanonical persisted trading event")
        return result
    except (KeyError, ValueError, TypeError, OverflowError, InvalidOperation, json.JSONDecodeError) as exc:
        raise InvalidEvent(f"invalid trading-event encoding: {type(exc).__name__}") from exc
