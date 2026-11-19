"""Immutable commands and responses for simulated trade entry and execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import Enum

from invest_engine.domain.primitives import InstrumentId, _decimal, utc_datetime
from invest_engine.trading.money import InstrumentRules, MonetaryRules, multiply_cash


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"


class TimeInForce(str, Enum):
    DAY = "DAY"


class OrderStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class SellSettlementMode(str, Enum):
    """Simulated crediting of net SELL proceeds; no brokerage settlement claims."""

    IMMEDIATE = "IMMEDIATE"
    EXPLICIT_CONFIRMATION = "EXPLICIT_CONFIRMATION"


class DecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NO_ACTION = "NO_ACTION"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    account_id: str
    strategy_ref: str
    instrument: InstrumentId
    side: Side
    quantity: Decimal
    limit_price: Decimal
    submitted_at: datetime
    stop_price: Decimal | None = None
    order_type: OrderType = OrderType.LIMIT
    time_in_force: TimeInForce = TimeInForce.DAY

    def __post_init__(self) -> None:
        for name in ("intent_id", "account_id", "strategy_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonempty")
        if not isinstance(self.instrument, InstrumentId):
            raise ValueError("invalid instrument")
        if not isinstance(self.side, Side):
            raise ValueError("invalid order side")
        if not isinstance(self.order_type, OrderType) or not isinstance(self.time_in_force, TimeInForce):
            raise ValueError("unsupported order type or time in force")
        _decimal(self.quantity, field="quantity", positive=True)
        _decimal(self.limit_price, field="limit_price", positive=True)
        if self.stop_price is not None:
            _decimal(self.stop_price, field="stop_price", positive=True)
            if self.side is Side.BUY and self.stop_price >= self.limit_price:
                raise ValueError("buy stop plan must be below limit price")
        object.__setattr__(self, "submitted_at", utc_datetime(self.submitted_at))


@dataclass(frozen=True, slots=True)
class RiskDecision:
    intent_id: str
    decision: DecisionStatus
    approved_qty: Decimal = Decimal(0)
    reservation: Decimal = Decimal(0)
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SimulatedFill:
    execution_id: str
    intent_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.execution_id or not self.intent_id:
            raise ValueError("execution id and intent id are required")
        _decimal(self.quantity, field="fill.quantity", positive=True)
        _decimal(self.price, field="fill.price", positive=True)
        _decimal(self.fee, field="fill.fee")
        if self.fee < 0:
            raise ValueError("fee must be nonnegative")
        object.__setattr__(self, "occurred_at", utc_datetime(self.occurred_at))


@dataclass(frozen=True, slots=True)
class TradingConfig:
    account_id: str
    settlement_rules: tuple[MonetaryRules, ...]
    instrument_rules: tuple[tuple[str, InstrumentRules], ...]
    fee_rate: Decimal = Decimal("0.001")  # synthetic fixture only, not Toss fee
    sell_tax_rate: Decimal = Decimal("0")  # optional synthetic SELL levy
    sell_settlement_mode: SellSettlementMode = SellSettlementMode.IMMEDIATE

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("account id required")
        _decimal(self.fee_rate, field="fee_rate")
        if self.fee_rate < 0 or self.fee_rate > 1:
            raise ValueError("fee_rate must be within [0, 1]")
        _decimal(self.sell_tax_rate, field="sell_tax_rate")
        if self.sell_tax_rate < 0 or self.sell_tax_rate >= 1:
            raise ValueError("sell_tax_rate must be within [0, 1)")
        if self.fee_rate + self.sell_tax_rate >= 1:
            raise ValueError("combined synthetic sell costs must be below proceeds")
        if not isinstance(self.sell_settlement_mode, SellSettlementMode):
            raise ValueError("invalid sell settlement mode")
        if len({v.currency for v in self.settlement_rules}) != len(self.settlement_rules):
            raise ValueError("duplicate settlement currency rules")
        if len({key for key, _ in self.instrument_rules}) != len(self.instrument_rules):
            raise ValueError("duplicate instrument rules")

    def cash_rules(self, currency: str) -> MonetaryRules:
        for value in self.settlement_rules:
            if value.currency == currency:
                return value
        raise ValueError(f"unsupported settlement currency: {currency}")

    def rules_for(self, instrument: InstrumentId) -> InstrumentRules:
        for key, value in self.instrument_rules:
            if key == instrument.key:
                return value
        raise ValueError(f"unsupported instrument: {instrument.key}")

    @property
    def requires_order_fill_history(self) -> bool:
        return False

    def validate_cost_order(self, intent: OrderIntent) -> None:
        """Optional cost policy guard. Legacy percentage policy is unrestricted."""

    def buy_reservation(self, intent: OrderIntent, remaining: Decimal,
                        prior_fills: tuple[SimulatedFill, ...] = ()) -> Decimal:
        if remaining == 0:
            return Decimal(0)
        with localcontext() as ctx:
            ctx.prec = 64
            gross = multiply_cash(intent.limit_price, remaining)
            return self.cash_rules(intent.instrument.currency).settle(
                gross + gross * self.fee_rate)

    def fill_cost(self, intent: OrderIntent, price: Decimal, quantity: Decimal,
                  at: datetime, prior_fills: tuple[SimulatedFill, ...] = (),
                  ) -> tuple[Decimal, Decimal]:
        """Commission and sale levy in settlement currency."""
        with localcontext() as ctx:
            ctx.prec = 64
            gross = multiply_cash(price, quantity)
            money = self.cash_rules(intent.instrument.currency)
            return (money.settle(gross * self.fee_rate),
                    money.settle(gross * self.sell_tax_rate)
                    if intent.side is Side.SELL else Decimal(0))

    def planned_fee_loss(self, intent: OrderIntent) -> Decimal:
        """Legacy planned loss is price-only; opt-in policies may extend it."""
        return Decimal(0)
