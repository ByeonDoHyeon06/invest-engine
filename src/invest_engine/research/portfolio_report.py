"""Deterministic shared-account execution and position-cycle reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from invest_engine.domain.primitives import InstrumentId, _decimal, utc_datetime
from invest_engine.research.report import BacktestReport, canonical_json
from invest_engine.strategies.portfolio_contracts import UniverseFrameStatus
from invest_engine.trading.models import Side


@dataclass(frozen=True, slots=True)
class PortfolioSessionWindow:
    session_id: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("portfolio session id is required")
        start = utc_datetime(self.start, field="portfolio_session.start")
        end = utc_datetime(self.end, field="portfolio_session.end")
        if start >= end:
            raise ValueError("portfolio session window must be positive")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)


@dataclass(frozen=True, slots=True)
class PortfolioExecutionRecord:
    execution_id: str
    intent_id: str
    source_frame_id: str
    market_event_id: str
    instrument: InstrumentId
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal
    realized_pnl: Decimal
    occurred_at: datetime
    position_before: Decimal
    position_after: Decimal
    session_id: str

    def __post_init__(self) -> None:
        identities = (
            self.execution_id,
            self.intent_id,
            self.source_frame_id,
            self.market_event_id,
            self.session_id,
        )
        if not all(isinstance(value, str) and value.strip() for value in identities):
            raise ValueError("portfolio execution identity fields are required")
        if not isinstance(self.instrument, InstrumentId) or not isinstance(self.side, Side):
            raise ValueError("portfolio execution instrument and side are required")
        quantity = _decimal(self.quantity, field="portfolio_execution.quantity", positive=True)
        _decimal(self.price, field="portfolio_execution.price", positive=True)
        fee = _decimal(self.fee, field="portfolio_execution.fee")
        tax = _decimal(self.tax, field="portfolio_execution.tax")
        _decimal(self.realized_pnl, field="portfolio_execution.realized_pnl")
        before = _decimal(self.position_before, field="portfolio_execution.position_before")
        after = _decimal(self.position_after, field="portfolio_execution.position_after")
        if fee < 0 or tax < 0 or before < 0 or after < 0:
            raise ValueError("portfolio execution costs and positions cannot be negative")
        expected = before + quantity if self.side is Side.BUY else before - quantity
        if expected != after:
            raise ValueError("portfolio execution position transition is inconsistent")
        if self.side is Side.BUY and self.realized_pnl != 0:
            raise ValueError("BUY execution cannot realize portfolio PnL")
        object.__setattr__(
            self,
            "occurred_at",
            utc_datetime(self.occurred_at, field="portfolio_execution.occurred_at"),
        )


@dataclass(frozen=True, slots=True)
class UniverseDecisionRecord:
    as_of: datetime
    status: UniverseFrameStatus
    frame_id: str | None = None
    missing_instrument_keys: tuple[str, ...] = ()
    selected_instrument_keys: tuple[str, ...] = ()
    signal_ids: tuple[str, ...] = ()
    intent_ids: tuple[str, ...] = ()
    canceled_intent_ids: tuple[str, ...] = ()
    decisions: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    fills: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "as_of",
            utc_datetime(self.as_of, field="universe_decision.as_of"),
        )
        if not isinstance(self.status, UniverseFrameStatus):
            raise ValueError("universe decision status is required")


@dataclass(frozen=True, slots=True)
class PositionCycle:
    instrument: InstrumentId
    session_id: str
    opened_at: datetime
    closed_at: datetime
    entry_fill_ids: tuple[str, ...]
    exit_fill_ids: tuple[str, ...]
    entry_quantity: Decimal
    exit_quantity: Decimal
    turnover: Decimal
    fees: Decimal
    taxes: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioSessionSummary:
    session_id: str
    start: datetime
    end: datetime
    completed_cycle_count: int
    entry_fill_count: int
    exit_fill_count: int
    turnover: Decimal
    fees: Decimal
    taxes: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    time_in_market: timedelta


@dataclass(frozen=True, slots=True)
class PortfolioSymbolSummary:
    instrument: InstrumentId
    completed_cycle_count: int
    turnover: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioExecutionSummary:
    cycles: tuple[PositionCycle, ...]
    sessions: tuple[PortfolioSessionSummary, ...]
    symbols: tuple[PortfolioSymbolSummary, ...]
    largest_positive_symbol_pnl_share: Decimal | None


@dataclass(frozen=True, slots=True)
class PortfolioBacktestReport:
    account_report: BacktestReport
    universe_decisions: tuple[UniverseDecisionRecord, ...]
    executions: tuple[PortfolioExecutionRecord, ...]
    cycles: tuple[PositionCycle, ...]
    sessions: tuple[PortfolioSessionSummary, ...]
    symbols: tuple[PortfolioSymbolSummary, ...]
    largest_positive_symbol_pnl_share: Decimal | None
    blocked_checkpoint_count: int
    run_sha256: str
    notes: tuple[str, ...]

    def export(self, directory: str | Path) -> None:
        """Write deterministic portfolio and unchanged account artifacts."""
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        self.account_report.export(output / "account")
        for name, records in (
            ("universe_decisions.jsonl", self.universe_decisions),
            ("executions.jsonl", self.executions),
            ("cycles.jsonl", self.cycles),
            ("sessions.jsonl", self.sessions),
            ("symbols.jsonl", self.symbols),
        ):
            data = b"".join(canonical_json(record) + b"\n" for record in records)
            (output / name).write_bytes(data)
        (output / "report.json").write_bytes(canonical_json(self))


@dataclass(slots=True)
class _CycleBuilder:
    instrument: InstrumentId
    session_id: str
    opened_at: datetime
    entry_fill_ids: list[str]
    exit_fill_ids: list[str]
    entry_quantity: Decimal = Decimal(0)
    exit_quantity: Decimal = Decimal(0)
    turnover: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    taxes: Decimal = Decimal(0)
    net_pnl: Decimal = Decimal(0)


@dataclass(slots=True)
class _SessionBuilder:
    window: PortfolioSessionWindow
    completed_cycle_count: int = 0
    entry_fill_count: int = 0
    exit_fill_count: int = 0
    turnover: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    taxes: Decimal = Decimal(0)
    net_pnl: Decimal = Decimal(0)


def _union_duration(cycles: tuple[PositionCycle, ...]) -> timedelta:
    if not cycles:
        return timedelta(0)
    intervals = sorted((cycle.opened_at, cycle.closed_at) for cycle in cycles)
    current_start, current_end = intervals[0]
    duration = timedelta(0)
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        duration += current_end - current_start
        current_start, current_end = start, end
    return duration + current_end - current_start


def summarize_portfolio_executions(
    executions: tuple[PortfolioExecutionRecord, ...],
    session_windows: tuple[PortfolioSessionWindow, ...],
) -> PortfolioExecutionSummary:
    """Reconstruct exact flat-to-long-to-flat cycles from immutable fills."""
    if not isinstance(executions, tuple) or not isinstance(session_windows, tuple):
        raise ValueError("portfolio report inputs must be immutable tuples")
    if tuple(sorted(session_windows, key=lambda item: item.start)) != session_windows:
        raise ValueError("portfolio session windows must be sorted")
    if len({item.session_id for item in session_windows}) != len(session_windows):
        raise ValueError("portfolio session ids must be unique")
    windows = {item.session_id: item for item in session_windows}
    session_builders = {
        item.session_id: _SessionBuilder(item) for item in session_windows
    }
    seen_ids: set[str] = set()
    last_at: datetime | None = None
    last_position: dict[str, Decimal] = {}
    open_cycles: dict[str, _CycleBuilder] = {}
    completed: list[PositionCycle] = []

    for execution in executions:
        if execution.execution_id in seen_ids:
            raise ValueError("duplicate portfolio execution id")
        if last_at is not None and execution.occurred_at < last_at:
            raise ValueError("portfolio executions must be chronological")
        seen_ids.add(execution.execution_id)
        last_at = execution.occurred_at
        window = windows.get(execution.session_id)
        if window is None or not window.start <= execution.occurred_at <= window.end:
            raise ValueError("portfolio execution is outside its declared session")
        key = execution.instrument.key
        active = open_cycles.get(key)
        if active is not None and active.session_id != execution.session_id:
            raise ValueError("position cycle cannot cross session boundary")
        if execution.position_before != last_position.get(key, Decimal(0)):
            raise ValueError("portfolio execution position transition is not contiguous")
        last_position[key] = execution.position_after

        session = session_builders[execution.session_id]
        gross = execution.quantity * execution.price
        session.turnover += gross
        session.fees += execution.fee
        session.taxes += execution.tax
        session.net_pnl += execution.realized_pnl
        if execution.side is Side.BUY:
            session.entry_fill_count += 1
            if active is None:
                active = _CycleBuilder(
                    execution.instrument,
                    execution.session_id,
                    execution.occurred_at,
                    [],
                    [],
                )
                open_cycles[key] = active
            active.entry_fill_ids.append(execution.execution_id)
            active.entry_quantity += execution.quantity
        else:
            session.exit_fill_count += 1
            if active is None:
                raise ValueError("SELL execution has no open position cycle")
            active.exit_fill_ids.append(execution.execution_id)
            active.exit_quantity += execution.quantity
        if active is None:
            raise AssertionError("position cycle builder missing")
        active.turnover += gross
        active.fees += execution.fee
        active.taxes += execution.tax
        active.net_pnl += execution.realized_pnl

        if execution.position_after == 0:
            cycle = PositionCycle(
                active.instrument,
                active.session_id,
                active.opened_at,
                execution.occurred_at,
                tuple(active.entry_fill_ids),
                tuple(active.exit_fill_ids),
                active.entry_quantity,
                active.exit_quantity,
                active.turnover,
                active.fees,
                active.taxes,
                active.net_pnl + active.fees + active.taxes,
                active.net_pnl,
            )
            completed.append(cycle)
            session.completed_cycle_count += 1
            del open_cycles[key]

    if open_cycles:
        raise ValueError("portfolio report contains an open position cycle")

    completed_tuple = tuple(completed)
    sessions = tuple(
        PortfolioSessionSummary(
            builder.window.session_id,
            builder.window.start,
            builder.window.end,
            builder.completed_cycle_count,
            builder.entry_fill_count,
            builder.exit_fill_count,
            builder.turnover,
            builder.fees,
            builder.taxes,
            builder.net_pnl + builder.fees + builder.taxes,
            builder.net_pnl,
            _union_duration(
                tuple(
                    cycle
                    for cycle in completed_tuple
                    if cycle.session_id == builder.window.session_id
                )
            ),
        )
        for builder in session_builders.values()
    )
    cycles_by_instrument: dict[str, list[PositionCycle]] = {}
    for cycle in completed_tuple:
        cycles_by_instrument.setdefault(cycle.instrument.key, []).append(cycle)
    symbols = tuple(
        PortfolioSymbolSummary(
            instrument=instrument_cycles[0].instrument,
            completed_cycle_count=len(instrument_cycles),
            turnover=sum(
                (cycle.turnover for cycle in instrument_cycles),
                start=Decimal(0),
            ),
            gross_pnl=sum(
                (cycle.gross_pnl for cycle in instrument_cycles),
                start=Decimal(0),
            ),
            net_pnl=sum(
                (cycle.net_pnl for cycle in instrument_cycles),
                start=Decimal(0),
            ),
        )
        for _, instrument_cycles in sorted(cycles_by_instrument.items())
    )
    positive_pnl = tuple(symbol.net_pnl for symbol in symbols if symbol.net_pnl > 0)
    positive_total = sum(positive_pnl, start=Decimal(0))
    concentration = (
        max(positive_pnl) / positive_total if positive_total > 0 else None
    )
    return PortfolioExecutionSummary(
        completed_tuple,
        sessions,
        symbols,
        concentration,
    )
