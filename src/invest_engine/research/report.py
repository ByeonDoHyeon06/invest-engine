"""Deterministic audit trail and currency-separated research metrics."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from invest_engine.domain.primitives import InstrumentId

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from invest_engine.research.fx import FxEquityPoint


def json_value(value: Any) -> Any:
    if isinstance(value, timedelta):
        return {"microseconds": (value.days * 86400 + value.seconds) * 1000000 + value.microseconds}
    if isinstance(value, (Decimal, datetime, Enum)):
        return str(value.value if isinstance(value, Enum) else value.isoformat() if isinstance(value, datetime) else value)
    if isinstance(value, InstrumentId):
        return json_value(asdict(value))
    if is_dataclass(value) and not isinstance(value, type):
        return json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(json_value(v) for v in value)
    return value


def canonical_json(value: object) -> bytes:
    return json.dumps(json_value(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


@dataclass(frozen=True, slots=True)
class EquityPoint:
    at: datetime
    by_currency: tuple[tuple[str, Decimal], ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    event_id: str
    signal_ids: tuple[str, ...] = ()
    intent_ids: tuple[str, ...] = ()
    decisions: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    fills: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FillTrace:
    execution_id: str
    intent_id: str
    market_event_id: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal
    realized_pnl: Decimal
    reason_code: str = "LIMIT_FILLED"


@dataclass(frozen=True, slots=True)
class BacktestReport:
    dataset_sha256: str
    config_sha256: str
    state_digest: str
    run_sha256: str
    event_count: int
    by_currency_start: tuple[tuple[str, Decimal], ...]
    by_currency_end: tuple[tuple[str, Decimal], ...]
    max_drawdown: tuple[tuple[str, Decimal], ...]
    entry_fill_count: int
    exit_fill_count: int
    total_fees: tuple[tuple[str, Decimal], ...]
    total_taxes: tuple[tuple[str, Decimal], ...]
    realized_exit_pnl: tuple[tuple[str, Decimal], ...]
    equity: tuple[EquityPoint, ...]
    decisions: tuple[DecisionRecord, ...]
    fills: tuple[FillTrace, ...]
    net_pnl: tuple[tuple[str, Decimal], ...]
    turnover: tuple[tuple[str, Decimal], ...]
    profit_factor: tuple[tuple[str, Decimal | None], ...]
    exit_fill_expectancy: tuple[tuple[str, Decimal | None], ...]
    notes: tuple[str, ...]
    fx_base_currency: str | None = None
    fx_data_sha256: str | None = None
    fx_equity: tuple[FxEquityPoint, ...] = ()
    fx_net_pnl: Decimal | None = None
    fx_max_drawdown: Decimal | None = None

    def export(self, directory: str | Path) -> None:
        """Write reproducible artifacts for research; caller controls private storage."""
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        for name, records in (
            ("decisions.jsonl", self.decisions),
            ("equity.jsonl", self.equity),
            ("fills.jsonl", self.fills),
        ):
            data = b"".join(canonical_json(record) + b"\n" for record in records)
            (output / name).write_bytes(data)
        if self.fx_base_currency is not None:
            (output / "fx_equity.jsonl").write_bytes(b"".join(
                canonical_json(item) + b"\n" for item in self.fx_equity
            ))
        (output / "report.json").write_bytes(canonical_json(self))


def drawdown(points: tuple[EquityPoint, ...], currency: str) -> Decimal:
    peak: Decimal | None = None
    worst = Decimal(0)
    for p in points:
        if not p.complete:
            continue
        value = dict(p.by_currency).get(currency)
        if value is None:
            continue
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            worst = max(worst, (peak-value)/peak)
    return worst


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()
