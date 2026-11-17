"""Functional trading ledger; events never call an external broker or clock."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, localcontext
from enum import Enum

from invest_engine.domain.errors import InvalidEvent
from invest_engine.trading.actions import (
    DelistingObserved, DividendEntitled, DividendPaymentConfirmed, DividendReceivable,
    PositionAdjustment, SplitApplied, action_fingerprint,
)
from invest_engine.domain.primitives import InstrumentId, Money, utc_datetime
from invest_engine.trading.models import (
    OrderIntent, OrderStatus, SellSettlementMode, Side, SimulatedFill, TradingConfig,
)
from invest_engine.trading.money import multiply_cash
from invest_engine.trading.monitoring import MonitorInput, MonitorResult, evaluate_monitor
from invest_engine.trading.policy import RiskLimits
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
class TransactionCharge:
    """Per-fill cost audit; tax is synthetic, derived from pinned config."""

    execution_id: str
    currency: str
    gross: Decimal
    fee: Decimal
    tax: Decimal
    cash_delta: Decimal


@dataclass(frozen=True, slots=True)
class PendingSettlement:
    """Sale proceeds awaiting a distinct, idempotent simulated confirmation."""

    execution_id: str
    currency: str
    amount: Decimal
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class CashSettlementConfirmed:
    execution_id: str


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


@dataclass(frozen=True, slots=True)
class RiskObserved:
    observation: MonitorInput


@dataclass(frozen=True, slots=True)
class AccountReconciliationReviewed:
    reviewed_by: str


TradingPayload = (
    EntriesPaused | EntriesResumed | OrderReserved | OrderRejected | OrderAccepted | OrderCancelPending
    | OrderCanceled | OrderUnknown | OrderReconciled | FillRecorded
    | RiskObserved | AccountReconciliationReviewed | CashSettlementConfirmed
    | SplitApplied | DividendEntitled | DividendPaymentConfirmed | DelistingObserved
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
    monitoring: MonitorResult | None = None
    daily_loss_sessions: frozenset[str] = frozenset()
    reconciliation_hold: bool = False
    charges: tuple[TransactionCharge, ...] = ()
    pending_settlements: tuple[PendingSettlement, ...] = ()
    settled_execution_ids: frozenset[str] = frozenset()
    applied_corporate_ids: frozenset[str] = frozenset()
    corporate_fingerprints: tuple[tuple[str, str], ...] = ()
    position_adjustments: tuple[PositionAdjustment, ...] = ()
    dividend_receivables: tuple[DividendReceivable, ...] = ()
    paid_dividend_ids: frozenset[str] = frozenset()
    delisted_instruments: frozenset[str] = frozenset()

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


def _apply(
    state: TradingState, payload: TradingPayload, config: TradingConfig,
    limits: RiskLimits,
) -> TradingState:
    if isinstance(payload, (SplitApplied, DividendEntitled, DelistingObserved)):
        if payload.action_id in state.applied_corporate_ids:
            raise InvalidEvent("duplicate corporate action")
        if payload.instrument.key in state.delisted_instruments:
            raise InvalidEvent("instrument already delisted")
        if any(o.intent.instrument.key == payload.instrument.key and
               o.status in (OrderStatus.RESERVED, OrderStatus.ACCEPTED,
                            OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCEL_PENDING,
                            OrderStatus.UNKNOWN) for o in state.orders):
            raise InvalidEvent("corporate action with open orders requires reconciliation")
        position = state.position(payload.instrument)
        state = replace(
            state, applied_corporate_ids=state.applied_corporate_ids | {payload.action_id},
            corporate_fingerprints=(*state.corporate_fingerprints,
                                    (payload.action_id, action_fingerprint(payload))),
        )
        if isinstance(payload, SplitApplied):
            if position is None or position.quantity == 0:
                return state
            with localcontext() as ctx:
                ctx.prec = 64
                new_quantity = position.quantity * payload.numerator / payload.denominator
                rules = config.rules_for(payload.instrument)
                try:
                    rules.validate_quantity(new_quantity)
                except ValueError as exc:
                    raise InvalidEvent("fractional split shares require explicit cash-in-lieu policy") from exc
                # Conserves the original total acquisition basis exactly.
                new_cost = position.average_cost * payload.denominator / payload.numerator
            state = _set_position(state, replace(position, quantity=new_quantity,
                                                average_cost=new_cost))
            return replace(state, position_adjustments=(
                *state.position_adjustments,
                PositionAdjustment(payload.action_id, payload.instrument.key,
                                   new_quantity - position.quantity),
            ))
        if isinstance(payload, DividendEntitled):
            qty = position.quantity if position else Decimal(0)
            if qty == 0:
                return state
            money = config.cash_rules(payload.instrument.currency)
            with localcontext() as ctx:
                ctx.prec = 64
                gross = money.settle(qty * payload.gross_per_share)
                withheld = money.settle(gross * payload.withholding_fraction)
                net = gross - withheld
            return replace(state, dividend_receivables=(
                *state.dividend_receivables,
                DividendReceivable(payload.action_id, money.currency, qty,
                                   gross, withheld, net, payload.effective_at),
            ))
        return replace(state, delisted_instruments=(
            state.delisted_instruments | {payload.instrument.key}))
    if isinstance(payload, DividendPaymentConfirmed):
        pending = next((d for d in state.dividend_receivables
                        if d.action_id == payload.action_id), None)
        if pending is None or payload.action_id in state.paid_dividend_ids:
            raise InvalidEvent("dividend payment has no unpaid entitlement")
        balance = state.account(pending.currency)
        return replace(
            _set_cash(state, replace(balance, settled=balance.settled + pending.net)),
            dividend_receivables=tuple(d for d in state.dividend_receivables
                                        if d.action_id != payload.action_id),
            paid_dividend_ids=state.paid_dividend_ids | {payload.action_id},
        )
    if isinstance(payload, RiskObserved):
        evaluation = evaluate_monitor(state, payload.observation, limits)
        sessions = state.daily_loss_sessions
        if "DAILY_LOSS_LIMIT" in evaluation.reasons:
            sessions = sessions | {evaluation.session_id}
        mismatch_codes = {
            "CASH_RECONCILIATION_MISMATCH", "POSITION_RECONCILIATION_MISMATCH",
            "ORDER_RECONCILIATION_MISMATCH", "REFERENCE_ACCOUNT_MISMATCH",
        }
        return replace(
            state, monitoring=evaluation, daily_loss_sessions=sessions,
            reconciliation_hold=state.reconciliation_hold or bool(mismatch_codes.intersection(evaluation.reasons)),
        )
    if isinstance(payload, AccountReconciliationReviewed):
        if not payload.reviewed_by.strip() or not state.reconciliation_hold:
            raise InvalidEvent("reconciliation review requires active hold and reviewer")
        if state.monitoring is None or state.monitoring.reasons:
            raise InvalidEvent("healthy reconciled assessment required before review")
        if state.monitoring.preceding_ordinal + 1 != state.last_ordinal:
            raise InvalidEvent("review requires latest account assessment")
        return replace(state, reconciliation_hold=False)
    if isinstance(payload, CashSettlementConfirmed):
        pending = next(
            (p for p in state.pending_settlements if p.execution_id == payload.execution_id),
            None,
        )
        if pending is None:
            raise InvalidEvent("no pending settlement for execution")
        balance = state.account(pending.currency)
        if balance.unsettled < pending.amount:
            raise InvalidEvent("settlement exceeds unsettled cash")
        return replace(
            _set_cash(state, replace(
                balance,
                settled=balance.settled + pending.amount,
                unsettled=balance.unsettled - pending.amount,
            )),
            pending_settlements=tuple(
                p for p in state.pending_settlements if p.execution_id != pending.execution_id
            ),
            settled_execution_ids=state.settled_execution_ids | {pending.execution_id},
        )
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
            tax = (
                money.settle(gross * config.sell_tax_rate)
                if order.intent.side is Side.SELL else Decimal(0)
            )
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
                net = gross - fee - tax
                if net < 0:
                    raise InvalidEvent("synthetic costs exceed sale proceeds")
                if config.sell_settlement_mode is SellSettlementMode.EXPLICIT_CONFIRMATION:
                    state = _set_cash(state, replace(
                        balance, unsettled=balance.unsettled + net,
                    ))
                    state = replace(state, pending_settlements=(
                        *state.pending_settlements,
                        PendingSettlement(fill.execution_id, money.currency, net, fill.occurred_at),
                    ))
                else:
                    state = _set_cash(state, replace(balance, settled=balance.settled + net))
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
        cash_delta = -(gross + fee) if order.intent.side is Side.BUY else gross - fee - tax
        return replace(
            state,
            seen_fills=state.seen_fills | {fill.execution_id},
            fills=(*state.fills, fill),
            charges=(*state.charges, TransactionCharge(
                fill.execution_id, money.currency, gross, fee, tax, cash_delta,
            )),
        )
    raise InvalidEvent("unknown trade payload")


def reduce_trade_event(
    state: TradingState, event: TradingEvent, config: TradingConfig,
    limits: RiskLimits | None = None,
) -> TradingState:
    if state.status is TradingStatus.HALTED:
        raise InvalidEvent("trading state halted")
    if event.ordinal != state.last_ordinal + 1 or event.event_id in state.seen_events:
        raise InvalidEvent("noncontiguous or duplicate trading event")
    if state.observed_at is not None and event.occurred_at < state.observed_at:
        raise InvalidEvent("trade event time reversed")
    if isinstance(event.payload, (SplitApplied, DividendEntitled, DelistingObserved)):
        if (event.occurred_at < event.payload.effective_at
                or event.occurred_at < event.payload.available_at):
            raise InvalidEvent("corporate action not yet effective or available")
    updated = _apply(state, event.payload, config, limits or RiskLimits())
    audit_trading_state(updated)
    # A single codec defines both the persisted wire event and state-chain hash.
    from invest_engine.trading.codec import encode_trade_event
    blob = encode_trade_event(event)
    digest = hashlib.sha256(bytes.fromhex(state.digest) + len(blob).to_bytes(8, "big") + blob).hexdigest()
    return replace(updated, last_ordinal=event.ordinal, observed_at=event.occurred_at, digest=digest, seen_events=updated.seen_events | {event.event_id})


def audit_trading_state(state: TradingState) -> None:
    """Validate journal/position/reservation consistency after each transition.

    Internal invariant audit only; this does not prove an external broker agrees.
    """
    active = {
        OrderStatus.RESERVED, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_PENDING, OrderStatus.UNKNOWN,
    }
    orders = {order.intent.intent_id: order for order in state.orders}
    if len(orders) != len(state.orders):
        raise InvalidEvent("duplicate order records")

    reserved_by_currency: dict[str, Decimal] = {}
    reserved_sell_by_symbol: dict[str, Decimal] = {}
    for order in state.orders:
        if order.status not in active:
            if order.reserved_cash or order.reserved_qty:
                raise InvalidEvent("closed order retains reservation")
            continue
        if order.intent.side is Side.BUY:
            c = order.intent.instrument.currency
            reserved_by_currency[c] = reserved_by_currency.get(c, Decimal(0)) + order.reserved_cash
        else:
            key = order.intent.instrument.key
            reserved_sell_by_symbol[key] = (
                reserved_sell_by_symbol.get(key, Decimal(0)) + order.reserved_qty
            )

    unsettled_by_currency: dict[str, Decimal] = {}
    pending_ids: set[str] = set()
    for pending in state.pending_settlements:
        if pending.execution_id in pending_ids:
            raise InvalidEvent("duplicate pending settlement")
        pending_ids.add(pending.execution_id)
        unsettled_by_currency[pending.currency] = (
            unsettled_by_currency.get(pending.currency, Decimal(0)) + pending.amount
        )
    if pending_ids & state.settled_execution_ids:
        raise InvalidEvent("settlement pending and confirmed simultaneously")
    if not state.settled_execution_ids <= state.seen_fills:
        raise InvalidEvent("settlement of nonexistent fill")

    cash_currencies = {balance.currency for balance in state.cash}
    if not set(reserved_by_currency) <= cash_currencies or not set(unsettled_by_currency) <= cash_currencies:
        raise InvalidEvent("reservation or settlement currency not funded")
    for balance in state.cash:
        if balance.settled < 0 or balance.reserved < 0 or balance.unsettled < 0:
            raise InvalidEvent("negative ledger cash")
        if balance.available < 0:
            raise InvalidEvent("negative buying power")
        if reserved_by_currency.get(balance.currency, Decimal(0)) != balance.reserved:
            raise InvalidEvent("cash reservations do not match open orders")
        if unsettled_by_currency.get(balance.currency, Decimal(0)) != balance.unsettled:
            raise InvalidEvent("unsettled cash does not match pending sales")

    if len(state.charges) != len(state.fills) or len(state.fills) != len(state.seen_fills):
        raise InvalidEvent("fill or charge journal inconsistent")
    if {v.execution_id for v in state.charges} != state.seen_fills:
        raise InvalidEvent("missing per-fill charge")
    fills_by_order: dict[str, Decimal] = {}
    shares_by_symbol: dict[str, Decimal] = {}
    for fill in state.fills:
        order = orders.get(fill.intent_id)
        if order is None:
            raise InvalidEvent("fill references unknown order")
        fills_by_order[fill.intent_id] = (
            fills_by_order.get(fill.intent_id, Decimal(0)) + fill.quantity
        )
        key = order.intent.instrument.key
        delta = fill.quantity if order.intent.side is Side.BUY else -fill.quantity
        shares_by_symbol[key] = shares_by_symbol.get(key, Decimal(0)) + delta
    if (len({name for name, _ in state.corporate_fingerprints})
            != len(state.corporate_fingerprints)
            or {name for name, _ in state.corporate_fingerprints}
            != state.applied_corporate_ids):
        raise InvalidEvent("corporate event identity mismatch")
    if len({a.action_id for a in state.position_adjustments}) != len(state.position_adjustments):
        raise InvalidEvent("duplicate share adjustment")
    for adjustment in state.position_adjustments:
        if adjustment.action_id not in state.applied_corporate_ids:
            raise InvalidEvent("unregistered share adjustment")
        shares_by_symbol[adjustment.instrument_key] = (
            shares_by_symbol.get(adjustment.instrument_key, Decimal(0))
            + adjustment.quantity_delta
        )
    receivables = {r.action_id for r in state.dividend_receivables}
    if len(receivables) != len(state.dividend_receivables):
        raise InvalidEvent("duplicate dividend receivable")
    if (receivables & state.paid_dividend_ids
            or not (receivables | state.paid_dividend_ids) <= state.applied_corporate_ids):
        raise InvalidEvent("invalid dividend entitlement/payment state")
    if any(r.net < 0 or r.gross != r.withheld + r.net
           for r in state.dividend_receivables):
        raise InvalidEvent("invalid dividend receivable arithmetic")
    for order in state.orders:
        qty = fills_by_order.get(order.intent.intent_id, Decimal(0))
        if qty != order.filled_quantity or qty > order.intent.quantity:
            raise InvalidEvent("order fill total inconsistent")
    positions = {p.instrument.key: p for p in state.positions}
    if len(positions) != len(state.positions):
        raise InvalidEvent("duplicate position records")
    if set(shares_by_symbol) - set(positions):
        raise InvalidEvent("fill position is missing")
    for position in state.positions:
        if position.quantity != shares_by_symbol.get(position.instrument.key, Decimal(0)):
            raise InvalidEvent("position quantities do not match fills")
        if position.quantity < 0:
            raise InvalidEvent("negative long position")
        reserved = reserved_sell_by_symbol.get(position.instrument.key, Decimal(0))
        if position.reserved_sell != reserved or position.reserved_sell > position.quantity:
            raise InvalidEvent("sell reservations inconsistent")
    if set(reserved_sell_by_symbol) - set(positions):
        raise InvalidEvent("reservation on nonexistent position")
