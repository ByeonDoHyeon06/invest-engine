"""Pure pre-trade risk policy for synthetic long-only simulation.

Optional E3.3 synthetic mark-to-market monitoring is available, but actual
live FX settlement and broker buying power remain separate E8 gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext

from invest_engine.domain.primitives import _decimal
from invest_engine.trading.models import (
    DecisionStatus,
    OrderIntent,
    RiskDecision,
    Side,
    TradingConfig,
)
from invest_engine.trading.money import multiply_cash


@dataclass(frozen=True, slots=True)
class RiskLimits:
    per_trade_planned_loss: Decimal = Decimal("0.0025")
    max_symbol_cost_fraction: Decimal = Decimal("0.10")
    max_total_cost_fraction: Decimal = Decimal("0.30")
    max_open_positions: int = 3
    require_stop_plan: bool = True
    max_daily_loss_fraction: Decimal = Decimal("0.01")
    mark_max_age: timedelta = timedelta(minutes=2)
    require_monitoring: bool = False
    require_account_reference: bool = False

    def __post_init__(self) -> None:
        for name in (
            "per_trade_planned_loss", "max_symbol_cost_fraction", "max_total_cost_fraction",
            "max_daily_loss_fraction"
        ):
            value = _decimal(getattr(self, name), field=name)
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not isinstance(self.mark_max_age, timedelta) or self.mark_max_age <= timedelta(0):
            raise ValueError("mark_max_age must be positive")
        if self.require_account_reference and not self.require_monitoring:
            raise ValueError("account reference requires monitoring")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be positive")


@dataclass(frozen=True, slots=True)
class Exposure:
    cash: Decimal
    symbol_cost: Decimal
    total_cost: Decimal
    unique_symbols: frozenset[str]
    reserved_cash: Decimal
    held_qty: Decimal
    reserved_sell_qty: Decimal
    equity_at_cost: Decimal


def evaluate_order(
    intent: OrderIntent,
    config: TradingConfig,
    limits: RiskLimits,
    exposure: Exposure,
    *,
    halted: bool = False,
) -> RiskDecision:
    """Risk decision uses **cost-based** exposure, not live market valuation.

    Live must replace these projections with fresh marked equity and broker
    buying power. Percentages are research policy, not safety guarantees.
    """
    if halted:
        return RiskDecision(intent.intent_id, DecisionStatus.HALTED, reason_codes=("RUNTIME_HALTED",))
    if intent.account_id != config.account_id:
        return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("ACCOUNT_MISMATCH",))
    try:
        rules = config.rules_for(intent.instrument)
        rules.validate_price(intent.limit_price)
        rules.validate_quantity(intent.quantity)
        config.cash_rules(intent.instrument.currency)
    except ValueError:
        return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("INVALID_INSTRUMENT_RULES",))
    try:
        config.validate_cost_order(intent)
    except ValueError:
        return RiskDecision(intent.intent_id, DecisionStatus.REJECTED,
                            reason_codes=("UNSUPPORTED_COST_POLICY_ORDER",))
    if intent.side is Side.SELL:
        if intent.quantity > exposure.held_qty - exposure.reserved_sell_qty:
            return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("INSUFFICIENT_POSITION",))
        return RiskDecision(intent.intent_id, DecisionStatus.APPROVED, approved_qty=intent.quantity)
    if limits.require_stop_plan and intent.stop_price is None:
        return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("STOP_PLAN_REQUIRED",))
    with localcontext() as ctx:
        ctx.prec = 64
        notional = multiply_cash(intent.limit_price, intent.quantity)
        reserve = config.buy_reservation(intent, intent.quantity)
        # E3 does not synthesize foreign exchange or cross-currency equity.
        starting_equity_at_cost = exposure.equity_at_cost
        if reserve > exposure.cash - exposure.reserved_cash:
            return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("INSUFFICIENT_BUYING_POWER",))
        if exposure.symbol_cost + notional > starting_equity_at_cost * limits.max_symbol_cost_fraction:
            return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("SYMBOL_COST_LIMIT",))
        if exposure.total_cost + notional > starting_equity_at_cost * limits.max_total_cost_fraction:
            return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("TOTAL_COST_LIMIT",))
        if intent.instrument.key not in exposure.unique_symbols and len(exposure.unique_symbols) >= limits.max_open_positions:
            return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("MAX_POSITIONS",))
        if intent.stop_price is not None:
            if intent.stop_price >= intent.limit_price:
                return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("INVALID_STOP_PLAN",))
            planned_loss = ((intent.limit_price - intent.stop_price) * intent.quantity
                            + config.planned_fee_loss(intent))
            if planned_loss > starting_equity_at_cost * limits.per_trade_planned_loss:
                return RiskDecision(intent.intent_id, DecisionStatus.REJECTED, reason_codes=("PLANNED_LOSS_LIMIT",))
        return RiskDecision(
            intent.intent_id,
            DecisionStatus.APPROVED,
            approved_qty=intent.quantity,
            reservation=reserve,
        )
