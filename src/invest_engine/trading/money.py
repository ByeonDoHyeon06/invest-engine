"""Explicit trade/settlement precision. Do not assume broker rounding rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext

from invest_engine.domain.primitives import _decimal


def _increment(value: Decimal, name: str) -> Decimal:
    _decimal(value, field=name, positive=True)
    return value


@dataclass(frozen=True, slots=True)
class MonetaryRules:
    """Simulation settlement policy; configured per account currency.

    The rounding mode is intentionally explicit: not a claim about Toss fees.
    """

    currency: str
    cash_step: Decimal
    rounding: str = ROUND_HALF_UP

    def __post_init__(self) -> None:
        if not isinstance(self.currency, str) or len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            raise ValueError("currency must be an uppercase ISO 4217 code")
        _increment(self.cash_step, "cash_step")
        # This policy supports currency quantum increments, e.g. 1 KRW or 0.01 USD.
        exponent = self.cash_step.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -12:
            raise ValueError("cash_step precision exceeds supported simulation scale")
        with localcontext() as ctx:
            ctx.prec = 64
            try:
                Decimal(1).quantize(self.cash_step, rounding=self.rounding)
            except Exception as exc:
                raise ValueError("unsupported rounding mode") from exc

    def settle(self, amount: Decimal) -> Decimal:
        _decimal(amount, field="settled cash")
        with localcontext() as ctx:
            ctx.prec = 64
            units = (amount / self.cash_step).to_integral_value(rounding=self.rounding)
            return units * self.cash_step


@dataclass(frozen=True, slots=True)
class InstrumentRules:
    """A point-in-time specification for simulated limit prices and lot sizes."""

    tick_size: Decimal
    lot_size: Decimal

    def __post_init__(self) -> None:
        _increment(self.tick_size, "tick_size")
        _increment(self.lot_size, "lot_size")

    @staticmethod
    def _is_multiple(value: Decimal, step: Decimal) -> bool:
        _decimal(value, field="value", positive=True)
        with localcontext() as ctx:
            ctx.prec = 64
            return value % step == 0

    def validate_price(self, value: Decimal) -> None:
        if not self._is_multiple(value, self.tick_size):
            raise ValueError("price is not a whole tick increment")

    def validate_quantity(self, value: Decimal) -> None:
        if not self._is_multiple(value, self.lot_size):
            raise ValueError("quantity is not a whole lot increment")


def multiply_cash(price: Decimal, quantity: Decimal) -> Decimal:
    _decimal(price, field="price", positive=True)
    _decimal(quantity, field="quantity", positive=True)
    with localcontext() as ctx:
        ctx.prec = 64
        return price * quantity
