"""Opt-in US dated fee simulation; no retail invoice or broker claims."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext
from zoneinfo import ZoneInfo

from invest_engine.domain.primitives import AssetClass, Market, _decimal, utc_datetime
from invest_engine.trading.models import OrderIntent, Side, SimulatedFill, TradingConfig
from invest_engine.trading.regulatory import US_2022

D = Decimal
C = D("0.01")
ET = ZoneInfo("America/New_York")

# Primitive values only, to preserve canonical journal/config serialization.
RATE_IDENTITY = (US_2022.version, US_2022.start.isoformat(),
                 US_2022.end_exclusive.isoformat(), US_2022.sec_rate,
                 US_2022.taf_per_share, US_2022.taf_cap_per_trade, US_2022.source_urls)


def _ceil(amount: Decimal) -> Decimal:
    return amount.quantize(C, rounding=ROUND_CEILING)


@dataclass(frozen=True, slots=True)
class USDatedFeeConfig(TradingConfig):
    """2022 modeled pass-through: order commission/SEC, execution TAF.

    Same ET day only. Charge date = simulated execution's ET day proxy.
    Rate, rounding, minimum and version are journal/config identity inputs.
    Fees are not broker-certified. Do not use this policy for real orders.
    """
    commission_minimum: Decimal = D(0)
    fee_policy_version: str = "us-2022-order-commission-sec-execution-taf-v1"
    regulatory_identity: tuple[str, str, str, Decimal, Decimal, Decimal, tuple[str, ...]] = RATE_IDENTITY

    def __post_init__(self) -> None:
        TradingConfig.__post_init__(self)
        if (self.sell_tax_rate != 0 or self.regulatory_identity != RATE_IDENTITY
                or self.fee_policy_version != "us-2022-order-commission-sec-execution-taf-v1"
                or _decimal(self.commission_minimum, field="commission_minimum") < 0
                or self.commission_minimum != self.commission_minimum.quantize(C)):
            raise ValueError("INVALID_DATED_FEE_CONFIG")

    @property
    def requires_order_fill_history(self) -> bool:
        return True

    def validate_cost_order(self, intent: OrderIntent) -> None:
        inst = intent.instrument
        if (inst.market is not Market.US or inst.currency != "USD"
                or inst.asset_class not in (AssetClass.EQUITY, AssetClass.ETF)
                or self.cash_rules("USD").cash_step != C
                or intent.quantity != intent.quantity.to_integral_value()
                or intent.limit_price != intent.limit_price.quantize(C)):
            raise ValueError("UNSUPPORTED_DATED_FEE_INSTRUMENT")
        if not US_2022.covers(intent.submitted_at.astimezone(ET).date()):
            raise ValueError("UNCOVERED_DATED_FEE_ORDER")

    def commission(self, gross: Decimal) -> Decimal:
        if gross == 0:
            return D(0)
        return max(self.commission_minimum,
                   (gross * self.fee_rate).quantize(C, rounding=ROUND_HALF_UP))

    def charge_components(self, gross_before: Decimal, price: Decimal,
                          qty: Decimal, side: Side) -> tuple[Decimal, Decimal, Decimal]:
        """Incremental rounded commission, SEC and TAF for one execution."""
        with localcontext() as ctx:
            ctx.prec = 64
            gross = price * qty
            cumulative = gross_before + gross
            fee = self.commission(cumulative) - self.commission(gross_before)
            sec = D(0)
            taf = D(0)
            if side is Side.SELL:
                sec = (_ceil(cumulative * US_2022.sec_rate)
                       - _ceil(gross_before * US_2022.sec_rate))
                taf = _ceil(min(qty * US_2022.taf_per_share,
                                US_2022.taf_cap_per_trade))
            return fee, sec, taf

    def _gross_before(self, intent: OrderIntent,
                      prior_fills: tuple[SimulatedFill, ...]) -> Decimal:
        day = intent.submitted_at.astimezone(ET).date()
        if any(f.intent_id != intent.intent_id or f.occurred_at.astimezone(ET).date() != day
               for f in prior_fills):
            raise ValueError("DATED_FEE_CROSS_DAY_OR_ORDER_HISTORY")
        return sum((f.price*f.quantity for f in prior_fills), D(0))

    def buy_reservation(self, intent: OrderIntent, remaining: Decimal,
                        prior_fills: tuple[SimulatedFill, ...] = ()) -> Decimal:
        self.validate_cost_order(intent)
        if remaining == 0:
            return D(0)
        if (intent.side is not Side.BUY or remaining < 0
                or remaining != remaining.to_integral_value()):
            raise ValueError("INVALID_DATED_FEE_RESERVATION")
        with localcontext() as ctx:
            ctx.prec = 64
            before = self._gross_before(intent, prior_fills)
            max_gross = intent.limit_price * remaining
            return max_gross + self.commission(before+max_gross) - self.commission(before)

    def fill_cost(self, intent: OrderIntent, price: Decimal, quantity: Decimal,
                  at: datetime, prior_fills: tuple[SimulatedFill, ...] = (),
                  ) -> tuple[Decimal, Decimal]:
        self.validate_cost_order(intent)
        at = utc_datetime(at)
        if (at < intent.submitted_at
                or at.astimezone(ET).date() != intent.submitted_at.astimezone(ET).date()
                or not US_2022.covers(at.astimezone(ET).date())):
            raise ValueError("UNCOVERED_OR_CROSS_DAY_DATED_FEE_FILL")
        if (_decimal(price, field="fill.price", positive=True) != price.quantize(C)
                or _decimal(quantity, field="fill.quantity", positive=True)
                != quantity.to_integral_value()):
            raise ValueError("UNSUPPORTED_DATED_FEE_FILL_PRECISION")
        with localcontext() as ctx:
            ctx.prec = 64
            before = self._gross_before(intent, prior_fills)
            fee, sec, taf = self.charge_components(before, price, quantity, intent.side)
            return fee, sec+taf

    def planned_fee_loss(self, intent: OrderIntent) -> Decimal:
        """Conservative full-fill fee estimate at planned stop, not gap-risk cap.

        TAF rounding assumes one-share sell executions (upper bound here);
        actual fills use modeled execution boundaries, not this estimate.
        """
        self.validate_cost_order(intent)
        if intent.side is not Side.BUY or intent.stop_price is None:
            return D(0)
        with localcontext() as ctx:
            ctx.prec = 64
            buy = intent.limit_price * intent.quantity
            sale = intent.stop_price * intent.quantity
            return (self.commission(buy) + self.commission(sale)
                    + _ceil(sale * US_2022.sec_rate)
                    + intent.quantity * _ceil(min(US_2022.taf_per_share,
                                                  US_2022.taf_cap_per_trade)))
