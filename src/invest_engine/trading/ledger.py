"""Functional trading ledger; events never call an external broker or clock."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, localcontext
from enum import Enum

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Money, utc_datetime
from invest_engine.trading.models import (
    OrderIntent, OrderStatus, Side, SimulatedFill, TradingConfig,
)
from invest_engine.trading.money import multiply_cash
from invest_engine.trading.policy import Exposure


class TradingStatus(str, Enum):
    RUNNING = "RUNNING"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class CashLedger:
    currency: str
    settled: Decimal
    reserved: Decimal = Decimal(0)
    unsettled: Decimal = Decimal(0)

    @property
    def available(self) -> Decimal:
        return self.settled - self.reserved


@dataclass(frozen=True, slots=True)
class Position:
    instrument: InstrumentId
    quantity: Decimal
    average_cost: Decimal
    reserved_sell: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class OrderRecord:
    intent: OrderIntent
    status: OrderStatus
    filled_quantity: Decimal = Decimal(0)
    reserved_cash: Decimal = Decimal(0)
    reserved_qty: Decimal = Decimal(0)
    reason_codes: tuple[str, ...] = ()

    @property
    def remaining(self) -> Decimal:
        return self.intent.quantity - self.filled_quantity


@dataclass(frozen=True, slots=True)
class EntriesPaused:
    reason: str


@dataclass(frozen=True, slots=True)
class EntriesResumed:
    reviewed_by: str


@dataclass(frozen=True, slots=True)
class OrderReserved:
    intent: OrderIntent
    reserved_cash: Decimal


@dataclass(frozen=True, slots=True)
class OrderRejected:
    intent: OrderIntent
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrderAccepted:
    intent_id: str


@dataclass(frozen=True, slots=True)
class OrderCancelPending:
    intent_id: str


@dataclass(frozen=True, slots=True)
class OrderCanceled:
    intent_id: str


@dataclass(frozen=True, slots=True)
class OrderUnknown:
    intent_id: str


@dataclass(frozen=True, slots=True)
class OrderReconciled:
    intent_id: str
    status: OrderStatus  # ACCEPTED or CANCELED / REJECTED only in E3


@dataclass(frozen=True, slots=True)
class FillRecorded:
    fill: SimulatedFill


TradingPayload = (
    EntriesPaused | EntriesResumed | OrderReserved | OrderRejected | OrderAccepted | OrderCancelPending
    | OrderCanceled | OrderUnknown | OrderReconciled | FillRecorded
)


@dataclass(frozen=True, slots=True)
class TradingEvent:
    event_id: str
    ordinal: int
    occurred_at: datetime
    payload: TradingPayload
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.event_id.strip() or self.ordinal < 0:
            raise InvalidEvent("invalid trading event id/ordinal")
        if self.schema_version != 1:
            raise InvalidEvent("unsupported trade event schema")
        object.__setattr__(self, "occurred_at", utc_datetime(self.occurred_at))


@dataclass(frozen=True, slots=True)
class TradingState:
    account_id: str
    cash: tuple[CashLedger, ...]
    positions: tuple[Position, ...] = ()
    orders: tuple[OrderRecord, ...] = ()
    seen_fills: frozenset[str] = frozenset()
    fills: tuple[SimulatedFill, ...] = ()
    seen_events: frozenset[str] = frozenset()
    last_ordinal: int = -1
    observed_at: datetime | None = None
    status: TradingStatus = TradingStatus.RUNNING
    entry_pause_reason: str | None = None
    digest: str = ""

    def account(self, currency: str) -> CashLedger:
        for balance in self.cash:
            if balance.currency == currency:
                return balance
        raise InvalidEvent(f"currency not funded: {currency}")

    def position(self, instrument: InstrumentId) -> Position | None:
        for position in self.positions:
            if position.instrument.key == instrument.key:
                return position
        return None

    def order(self, intent_id: str) -> OrderRecord | None:
        for order in self.orders:
            if order.intent.intent_id == intent_id:
                return order
        return None


def initial_trading_state(account_id: str, cash: tuple[Money, ...]) -> TradingState:
    if not account_id.strip() or not cash:
        raise ValueError("account id and cash are required")
    if len({x.currency for x in cash}) != len(cash):
        raise ValueError("duplicate starting currencies")
    for entry in cash:
        if entry.amount < 0:
            raise ValueError("starting balance cannot be negative")
    seed = hashlib.sha256(f"invest-engine:e3:account:{account_id}".encode()).hexdigest()
    return TradingState(
        account_id,
        tuple(sorted((CashLedger(x.currency, x.amount) for x in cash), key=lambda x: x.currency)),
        digest=seed,
    )


def exposure_for(state: TradingState, currency: str, instrument: InstrumentId) -> Exposure:
    cash = state.account(currency)
    positions = [p for p in state.positions if p.instrument.currency == currency]
    pending_buy = [
        o for o in state.orders
        if o.intent.instrument.currency == currency
        and o.intent.side is Side.BUY
        and o.status not in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED)
    ]
    symbols = frozenset(
        [p.instrument.key for p in positions if p.quantity > 0]
        + [o.intent.instrument.key for o in pending_buy]
    )
    held = state.position(instrument)
    with localcontext() as ctx:
        ctx.prec = 64
        total = sum((p.quantity * p.average_cost for p in positions), Decimal(0))
        total += sum((o.remaining * o.intent.limit_price for o in pending_buy), Decimal(0))
        symbol_cost = sum(
            (p.quantity * p.average_cost for p in positions if p.instrument.key == instrument.key),
            Decimal(0),
        )
        symbol_cost += sum(
            (o.remaining * o.intent.limit_price for o in pending_buy if o.intent.instrument.key == instrument.key),
            Decimal(0),
        )
    return Exposure(
        cash=cash.settled,
        symbol_cost=symbol_cost,
        total_cost=total,
        unique_symbols=symbols,
        reserved_cash=cash.reserved,
        held_qty=held.quantity if held else Decimal(0),
        reserved_sell_qty=held.reserved_sell if held else Decimal(0),
        equity_at_cost=cash.settled + sum(
            (p.quantity * p.average_cost for p in positions), Decimal(0)
        ),
    )


def _set_cash(state: TradingState, value: CashLedger) -> TradingState:
    return replace(state, cash=tuple(sorted(
        (x if x.currency != value.currency else value for x in state.cash),
        key=lambda x: x.currency,
    )))


def _set_order(state: TradingState, updated: OrderRecord) -> TradingState:
    if state.order(updated.intent.intent_id) is None:
        values = (*state.orders, updated)
    else:
        values = tuple(o if o.intent.intent_id != updated.intent.intent_id else updated for o in state.orders)
    return replace(state, orders=tuple(sorted(values, key=lambda x: x.intent.intent_id)))


def _set_position(state: TradingState, updated: Position) -> TradingState:
    values = tuple(p for p in state.positions if p.instrument.key != updated.instrument.key)
    return replace(state, positions=tuple(sorted((*values, updated), key=lambda x: x.instrument.key)))


def _release_reservation(state: TradingState, order: OrderRecord) -> TradingState:
    if order.intent.side is Side.BUY:
        balance = state.account(order.intent.instrument.currency)
        if balance.reserved < order.reserved_cash:
            raise InvalidEvent("missing reserved cash")
        return _set_cash(state, replace(balance, reserved=balance.reserved-order.reserved_cash))
    position = state.position(order.intent.instrument)
    if position is None or position.reserved_sell < order.reserved_qty:
        raise InvalidEvent("missing reserved sell shares")
    return _set_position(state, replace(position, reserved_sell=position.reserved_sell-order.reserved_qty))


def _apply(state: TradingState, payload: TradingPayload, config: TradingConfig) -> TradingState:
    if isinstance(payload, EntriesPaused):
        if not payload.reason.strip() or state.entry_pause_reason is not None:
            raise InvalidEvent("invalid new entry pause")
        return replace(state, entry_pause_reason=payload.reason)
    if isinstance(payload, EntriesResumed):
        if state.entry_pause_reason is None or not payload.reviewed_by.strip():
            raise InvalidEvent("invalid entry resume authorization")
        if any(o.status is OrderStatus.UNKNOWN for o in state.orders):
            raise InvalidEvent("unknown broker status prevents entry resume")
        return replace(state, entry_pause_reason=None)
    if isinstance(payload, (OrderReserved, OrderRejected)):
        intent = payload.intent
        if intent.account_id != state.account_id:
            raise InvalidEvent("account mismatch")
        if state.order(intent.intent_id) is not None:
            raise InvalidEvent("duplicate order intent")
        if isinstance(payload, OrderRejected):
            return _set_order(state, OrderRecord(intent, OrderStatus.REJECTED, reason_codes=payload.reason_codes))
        config.rules_for(intent.instrument).validate_price(intent.limit_price)
        config.rules_for(intent.instrument).validate_quantity(intent.quantity)
        cash_rules = config.cash_rules(intent.instrument.currency)
        balance = state.account(intent.instrument.currency)
        if intent.side is Side.BUY:
            with localcontext() as ctx:
                ctx.prec = 64
                notional = multiply_cash(intent.limit_price, intent.quantity)
                expected = cash_rules.settle(notional + notional * config.fee_rate)
            if payload.reserved_cash != expected or balance.available < expected:
                raise InvalidEvent("invalid cash reservation")
            state = _set_cash(state, replace(balance, reserved=balance.reserved + expected))
            record = OrderRecord(intent, OrderStatus.RESERVED, reserved_cash=expected)
        else:
            if payload.reserved_cash != 0:
                raise InvalidEvent("sell must not reserve cash")
            position = state.position(intent.instrument)
            if position is None or position.quantity - position.reserved_sell < intent.quantity:
                raise InvalidEvent("insufficient unreserved shares")
            state = _set_position(state, replace(position, reserved_sell=position.reserved_sell+intent.quantity))
            record = OrderRecord(intent, OrderStatus.RESERVED, reserved_qty=intent.quantity)
        return _set_order(state, record)

    intent_id = payload.fill.intent_id if isinstance(payload, FillRecorded) else payload.intent_id
    order = state.order(intent_id)
    if order is None:
        raise InvalidEvent("unknown order intent")
    if isinstance(payload, OrderAccepted):
        if order.status not in (OrderStatus.RESERVED, OrderStatus.UNKNOWN):
            raise InvalidEvent("cannot acknowledge order in its current status")
        return _set_order(state, replace(order, status=OrderStatus.ACCEPTED))
    if isinstance(payload, OrderUnknown):
        if order.status not in (OrderStatus.RESERVED, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCEL_PENDING):
            raise InvalidEvent("cannot declare order unknown in current status")
        return _set_order(state, replace(order, status=OrderStatus.UNKNOWN))
    if isinstance(payload, OrderReconciled):
        if order.status is not OrderStatus.UNKNOWN or payload.status not in (OrderStatus.ACCEPTED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            raise InvalidEvent("invalid unknown order reconciliation")
        if payload.status in (OrderStatus.CANCELED, OrderStatus.REJECTED):
            state = _release_reservation(state, order)
            return _set_order(state, replace(order, status=payload.status, reserved_cash=Decimal(0), reserved_qty=Decimal(0)))
        return _set_order(state, replace(order, status=(OrderStatus.PARTIALLY_FILLED if order.filled_quantity else OrderStatus.ACCEPTED)))
    if isinstance(payload, OrderCancelPending):
        if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED):
            raise InvalidEvent("cannot request cancel from this order status")
        return _set_order(state, replace(order, status=OrderStatus.CANCEL_PENDING))
    if isinstance(payload, OrderCanceled):
        if order.status not in (OrderStatus.CANCEL_PENDING, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED):
            raise InvalidEvent("cannot cancel from this order status")
        state = _release_reservation(state, order)
        return _set_order(state, replace(order, status=OrderStatus.CANCELED, reserved_cash=Decimal(0), reserved_qty=Decimal(0)))
    if isinstance(payload, FillRecorded):
        fill = payload.fill
        if fill.execution_id in state.seen_fills:
            raise InvalidEvent("duplicate fill event")
        if order.status not in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCEL_PENDING):
            raise InvalidEvent("cannot fill order in its current status")
        config.rules_for(order.intent.instrument).validate_quantity(fill.quantity)
        config.rules_for(order.intent.instrument).validate_price(fill.price)
        if fill.quantity > order.remaining:
            raise InvalidEvent("fill exceeds order remainder")
        if order.intent.side is Side.BUY and fill.price > order.intent.limit_price:
            raise InvalidEvent("buy execution exceeds limit")
        if order.intent.side is Side.SELL and fill.price < order.intent.limit_price:
            raise InvalidEvent("sell execution below limit")
        money = config.cash_rules(order.intent.instrument.currency)
        with localcontext() as ctx:
            ctx.prec = 64
            gross = multiply_cash(fill.price, fill.quantity)
            fee = money.settle(gross * config.fee_rate)
            if fee != fill.fee:
                raise InvalidEvent("fee does not match simulated policy")
            old = state.position(order.intent.instrument)
            if order.intent.side is Side.BUY:
                balance = state.account(money.currency)
                remaining_qty = order.remaining-fill.quantity
                outstanding_gross = (
                    multiply_cash(order.intent.limit_price, remaining_qty)
                    if remaining_qty > 0 else Decimal(0)
                )
                next_reserved = money.settle(outstanding_gross * (1 + config.fee_rate)) if remaining_qty > 0 else Decimal(0)
                paid = gross + fee
                if balance.reserved < order.reserved_cash or balance.settled - paid < next_reserved + (balance.reserved - order.reserved_cash):
                    raise InvalidEvent("cash would overdraw after fill")
                state = _set_cash(state, replace(balance, settled=balance.settled-paid, reserved=balance.reserved-order.reserved_cash+next_reserved))
                prior_qty = old.quantity if old else Decimal(0)
                prior_total = prior_qty * old.average_cost if old else Decimal(0)
                avg = (prior_total+gross+fee)/(prior_qty+fill.quantity)
                state = _set_position(state, Position(
                    order.intent.instrument, prior_qty+fill.quantity, avg,
                    reserved_sell=old.reserved_sell if old else Decimal(0),
                    realized_pnl=old.realized_pnl if old else Decimal(0),
                ))
                next_order = replace(order, reserved_cash=next_reserved)
            else:
                if old is None or old.quantity < fill.quantity or old.reserved_sell < fill.quantity:
                    raise InvalidEvent("insufficient shares for fill")
                balance = state.account(money.currency)
                net = gross-fee
                state = _set_cash(state, replace(balance, settled=balance.settled+net))
                remaining_qty = old.quantity-fill.quantity
                gain = net - old.average_cost * fill.quantity
                state = _set_position(state, replace(old, quantity=remaining_qty, reserved_sell=old.reserved_sell-fill.quantity, realized_pnl=old.realized_pnl+gain))
                next_order = replace(order, reserved_qty=order.reserved_qty-fill.quantity)
        updated_qty = order.filled_quantity + fill.quantity
        new_status = (
            OrderStatus.FILLED if updated_qty == order.intent.quantity
            else OrderStatus.CANCEL_PENDING if order.status is OrderStatus.CANCEL_PENDING
            else OrderStatus.PARTIALLY_FILLED
        )
        updated = replace(next_order, filled_quantity=updated_qty, status=new_status)
        state = _set_order(state, updated)
        return replace(
            state, seen_fills=state.seen_fills | {fill.execution_id}, fills=(*state.fills, fill)
        )
    raise InvalidEvent("unknown trade payload")


def reduce_trade_event(state: TradingState, event: TradingEvent, config: TradingConfig) -> TradingState:
    if state.status is TradingStatus.HALTED:
        raise InvalidEvent("trading state halted")
    if event.ordinal != state.last_ordinal + 1 or event.event_id in state.seen_events:
        raise InvalidEvent("noncontiguous or duplicate trading event")
    if state.observed_at is not None and event.occurred_at < state.observed_at:
        raise InvalidEvent("trade event time reversed")
    updated = _apply(state, event.payload, config)
    # A single codec defines both the persisted wire event and state-chain hash.
    from invest_engine.trading.codec import encode_trade_event
    blob = encode_trade_event(event)
    digest = hashlib.sha256(bytes.fromhex(state.digest) + len(blob).to_bytes(8, "big") + blob).hexdigest()
    return replace(updated, last_ordinal=event.ordinal, observed_at=event.occurred_at, digest=digest, seen_events=updated.seen_events | {event.event_id})
