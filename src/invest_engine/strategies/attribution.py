"""Pure, replayable research-only strategy attribution for simulated fills.

Virtual fractional shares attribute a shared order to multiple strategies;
these are not transferable positions or a live broker subaccount ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext

from invest_engine.domain.primitives import InstrumentId, _decimal
from invest_engine.trading.actions import SplitApplied
from invest_engine.strategies.allocation import AllocationPlan
from invest_engine.trading.ledger import TradingState
from invest_engine.trading.models import OrderIntent, Side, SimulatedFill


@dataclass(frozen=True, slots=True)
class AttributionTicket:
    """Immutable allocation intent saved alongside an eventual simulated order."""

    intent_id: str
    instrument: InstrumentId
    side: Side
    ordered_quantity: Decimal
    strategy_weights: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent id required")
        _decimal(self.ordered_quantity, field="ticket.ordered_qty", positive=True)
        if not isinstance(self.side, Side):
            raise ValueError("invalid ticket side")
        if len({name for name, _ in self.strategy_weights}) != len(self.strategy_weights):
            raise ValueError("duplicate strategy in ticket")
        for name, weight in self.strategy_weights:
            if not name.strip():
                raise ValueError("strategy name must not be empty")
            _decimal(weight, field="ticket.weight", positive=True)
        if self.side is Side.BUY and not self.strategy_weights:
            raise ValueError("BUY ticket must contain strategy allocation")
        if self.side is Side.SELL and self.strategy_weights:
            raise ValueError("SELL attribution uses existing holdings, not target weights")


def ticket_for_plan(plan: AllocationPlan, intent: OrderIntent) -> AttributionTicket:
    if (plan.instrument != intent.instrument or plan.as_of != intent.submitted_at
        or (intent.side is Side.BUY and plan.target_fraction <= 0)
        or (intent.side is Side.SELL and plan.target_fraction != 0)):
        raise ValueError("intent and allocation plan mismatch")
    weights = plan.strategy_targets if intent.side is Side.BUY else ()
    return AttributionTicket(intent.intent_id, intent.instrument, intent.side,
                             intent.quantity, weights)


@dataclass(frozen=True, slots=True)
class VirtualPosition:
    strategy_id: str
    instrument: InstrumentId
    quantity: Decimal = Decimal(0)
    average_cost: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class VirtualLedger:
    positions: tuple[VirtualPosition, ...] = ()
    applied: tuple[tuple[str, AttributionTicket, SimulatedFill], ...] = ()
    filled_by_intent: tuple[tuple[str, Decimal], ...] = ()

    def position(self, strategy_id: str, instrument: InstrumentId) -> VirtualPosition | None:
        return next((p for p in self.positions if p.strategy_id == strategy_id
                     and p.instrument.key == instrument.key), None)

    def instrument_quantity(self, instrument: InstrumentId) -> Decimal:
        return sum((p.quantity for p in self.positions if p.instrument.key == instrument.key), Decimal(0))


def _shares(total: Decimal, weights: tuple[tuple[str, Decimal], ...]) -> tuple[tuple[str, Decimal], ...]:
    """High-precision split with last-strategy remainder to conserve exact total."""
    if not weights:
        raise ValueError("cannot split fill without strategy weights")
    with localcontext() as ctx:
        ctx.prec = 64
        total_weight = sum((w for _, w in weights), Decimal(0))
        if total_weight <= 0:
            raise ValueError("invalid allocation weights")
        remaining = total
        allocated: list[tuple[str, Decimal]] = []
        for name, weight in weights[:-1]:
            share = total * weight / total_weight
            allocated.append((name, share))
            remaining -= share
        allocated.append((weights[-1][0], remaining))
        return tuple(allocated)


def record_simulated_fill(
    state: VirtualLedger, ticket: AttributionTicket, fill: SimulatedFill,
) -> VirtualLedger:
    """Pure accounting reducer. Never imports or calls a broker.

    Duplicate identical execution IDs are idempotent; conflicting use of an ID
    or an order quantity overrun is rejected. Sell shares are attributed pro rata
    from current virtual positions, ignoring long target signals.
    """
    if fill.intent_id != ticket.intent_id:
        raise ValueError("fill intent and ticket do not match")
    previous = next((record for record in state.applied if record[0] == fill.execution_id), None)
    if previous is not None:
        if previous[1] != ticket or previous[2] != fill:
            raise ValueError("conflicting duplicate execution id")
        return state
    filled = dict(state.filled_by_intent)
    already = filled.get(ticket.intent_id, Decimal(0))
    if already + fill.quantity > ticket.ordered_quantity:
        raise ValueError("fill exceeds original intent quantity")
    positions = {(p.strategy_id, p.instrument.key): p for p in state.positions}
    if ticket.side is Side.BUY:
        quantity_shares = _shares(fill.quantity, ticket.strategy_weights)
    else:
        held = tuple(sorted(
            ((p.strategy_id, p.quantity) for p in state.positions
             if p.instrument.key == ticket.instrument.key and p.quantity > 0),
            key=lambda row: row[0],
        ))
        if fill.quantity > sum((v for _, v in held), Decimal(0)):
            raise ValueError("SELL quantity exceeds allocated virtual positions")
        quantity_shares = _shares(fill.quantity, held)
    fee_shares = dict(_shares(fill.fee, quantity_shares))
    with localcontext() as ctx:
        ctx.prec = 64
        for name, quantity in quantity_shares:
            key = (name, ticket.instrument.key)
            existing = positions.get(key, VirtualPosition(name, ticket.instrument))
            fee = fee_shares[name]
            if ticket.side is Side.BUY:
                new_quantity = existing.quantity + quantity
                new_cost = (existing.quantity * existing.average_cost +
                            quantity * fill.price + fee) / new_quantity
                positions[key] = replace(existing, quantity=new_quantity, average_cost=new_cost)
            else:
                if quantity > existing.quantity:
                    raise ValueError("strategy cannot sell unallocated shares")
                realized = quantity * (fill.price - existing.average_cost) - fee
                remaining = existing.quantity - quantity
                positions[key] = replace(
                    existing, quantity=remaining,
                    average_cost=existing.average_cost if remaining > 0 else Decimal(0),
                    realized_pnl=existing.realized_pnl + realized,
                )
    filled[ticket.intent_id] = already + fill.quantity
    return VirtualLedger(
        positions=tuple(sorted(positions.values(), key=lambda p: (p.instrument.key, p.strategy_id))),
        applied=state.applied + ((fill.execution_id, ticket, fill),),
        filled_by_intent=tuple(sorted(filled.items())),
    )


def audit_virtual_against_account(virtual: VirtualLedger, account: TradingState) -> None:
    """Require complete attribution; pre-existing manual holdings cause mismatch."""
    keys = {p.instrument.key for p in account.positions if p.quantity > 0}
    keys.update(p.instrument.key for p in virtual.positions if p.quantity > 0)
    instruments = {p.instrument.key: p.instrument for p in account.positions}
    instruments.update({p.instrument.key: p.instrument for p in virtual.positions})
    for key in keys:
        inst = instruments[key]
        actual = account.position(inst)
        actual_qty = actual.quantity if actual else Decimal(0)
        if virtual.instrument_quantity(inst) != actual_qty:
            raise ValueError(f"virtual attribution mismatch for {key}")


def rebase_virtual_for_split(state: VirtualLedger, split: "SplitApplied") -> VirtualLedger:
    """Conserve every virtual holding's acquisition basis after an E3-approved split.

    No synthetic fills, cash, or realized PnL are created. Historical tickets
    remain immutable; future sells take shares from the rebased positions.
    """
    with localcontext() as ctx:
        ctx.prec = 64
        positions = tuple(
            replace(p, quantity=p.quantity * split.numerator / split.denominator,
                    average_cost=p.average_cost * split.denominator / split.numerator)
            if p.instrument == split.instrument and p.quantity > 0 else p
            for p in state.positions
        )
    return replace(state, positions=positions)
