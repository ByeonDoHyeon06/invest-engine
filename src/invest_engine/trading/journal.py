"""E3 isolated simulation journal coexists with E2 market tables in SQLite.

The Event + Outbox change shares a single SQLite transaction. No network send
is retried from the outbox without explicit reconciliation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from invest_engine.core.replay import _canonical
from invest_engine.domain.errors import InvalidEvent
from invest_engine.trading.codec import decode_trade_event, encode_trade_event
from invest_engine.trading.ledger import (
    FillRecorded, OrderAccepted, OrderCanceled, OrderReconciled, OrderRejected,
    OrderReserved, OrderUnknown, TradingEvent, TradingState, reduce_trade_event,
)
from invest_engine.trading.models import OrderStatus, TradingConfig
from invest_engine.trading.policy import RiskLimits


class SQLiteTradingJournal:
    """Strict append-only simulation journal; separate from E2 observation reducer."""

    def __init__(self, path: str | Path) -> None:
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS trading_metadata (
                  key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trading_events (
                  ordinal INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
                  body TEXT NOT NULL, checksum TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trading_checkpoints (
                  ordinal INTEGER PRIMARY KEY, digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trading_outbox (
                  intent_id TEXT PRIMARY KEY, event_ordinal INTEGER NOT NULL,
                  state TEXT NOT NULL CHECK(state IN ('PENDING','ACKNOWLEDGED','UNKNOWN','CLOSED')));
            """)

    def __enter__(self) -> SQLiteTradingJournal:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _identity(config: TradingConfig, state: TradingState, limits: RiskLimits) -> str:
        # Identity pins policy & opening cash; non-breaking replay cannot silently
        # switch account, currency quantum, instrument rules or fee calculation.
        blob = json.dumps(_canonical({"config": config, "starting_cash": state.cash, "risk_limits": limits}),
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def attach(self, config: TradingConfig, state: TradingState, limits: RiskLimits) -> None:
        identity = self._identity(config, state, limits)
        row = self.connection.execute("SELECT value FROM trading_metadata WHERE key='identity'").fetchone()
        if row is not None and row[0] != identity:
            raise InvalidEvent("trading journal account/config/initial cash differs")
        if row is None:
            with self.connection:
                self.connection.execute("INSERT INTO trading_metadata(key,value) VALUES('identity',?)", (identity,))
                self.connection.execute("INSERT INTO trading_metadata(key,value) VALUES('schema','e3-v1')")
        if self.connection.execute("SELECT value FROM trading_metadata WHERE key='schema'").fetchone() != ("e3-v1",):
            raise InvalidEvent("unsupported trading journal schema")

    def _read(self) -> list[TradingEvent]:
        result = []
        for ordinal, event_id, body, checksum in self.connection.execute(
            "SELECT ordinal,event_id,body,checksum FROM trading_events ORDER BY ordinal"
        ):
            if hashlib.sha256(body.encode()).hexdigest() != checksum:
                raise InvalidEvent("trading event checksum mismatch")
            event = decode_trade_event(body.encode())
            if event.ordinal != ordinal or event.event_id != event_id:
                raise InvalidEvent("trading event identity mismatch")
            result.append(event)
        return result

    def restore(self, state: TradingState, config: TradingConfig, limits: RiskLimits) -> TradingState:
        self.attach(config, state, limits)
        checkpoints = dict(self.connection.execute("SELECT ordinal,digest FROM trading_checkpoints"))
        seen_cp: set[int] = set()
        for event in self._read():
            state = reduce_trade_event(state, event, config)
            expected = checkpoints.get(event.ordinal)
            if expected is not None:
                seen_cp.add(event.ordinal)
                if expected != state.digest:
                    raise InvalidEvent("trading checkpoint digest differs from replay")
        if set(checkpoints) != seen_cp:
            raise InvalidEvent("trading checkpoint refers to missing event")
        actual = dict(self.connection.execute(
            "SELECT intent_id,state FROM trading_outbox"
        ))
        expected: dict[str, str] = {}
        for order in state.orders:
            if order.status is OrderStatus.REJECTED and order.intent.intent_id not in actual:
                continue
            mapping = {
                OrderStatus.RESERVED: "PENDING",
                OrderStatus.ACCEPTED: "ACKNOWLEDGED",
                OrderStatus.PARTIALLY_FILLED: "ACKNOWLEDGED",
                OrderStatus.CANCEL_PENDING: "ACKNOWLEDGED",
                OrderStatus.UNKNOWN: "UNKNOWN",
                OrderStatus.FILLED: "CLOSED",
                OrderStatus.CANCELED: "CLOSED",
                OrderStatus.REJECTED: "CLOSED",
            }
            expected[order.intent.intent_id] = mapping[order.status]
        if actual != expected:
            raise InvalidEvent("outbox does not match event-replayed order states")
        if self.halt_reason() is not None:
            from dataclasses import replace
            from invest_engine.trading.ledger import TradingStatus
            state = replace(state, status=TradingStatus.HALTED)
        return state

    def commit(self, event: TradingEvent, state: TradingState, *, checkpoint: bool) -> None:
        encoded = encode_trade_event(event)
        body = encoded.decode()
        digest = hashlib.sha256(encoded).hexdigest()
        payload = event.payload
        with self.connection:
            self.connection.execute(
                "INSERT INTO trading_events(ordinal,event_id,body,checksum) VALUES(?,?,?,?)",
                (event.ordinal, event.event_id, body, digest),
            )
            if isinstance(payload, OrderReserved):
                self.connection.execute("INSERT INTO trading_outbox(intent_id,event_ordinal,state) VALUES(?,?,'PENDING')",
                                        (payload.intent.intent_id, event.ordinal))
            elif isinstance(payload, OrderAccepted):
                self.connection.execute("UPDATE trading_outbox SET state='ACKNOWLEDGED' WHERE intent_id=?", (payload.intent_id,))
            elif isinstance(payload, OrderUnknown):
                self.connection.execute("UPDATE trading_outbox SET state='UNKNOWN' WHERE intent_id=?", (payload.intent_id,))
            elif isinstance(payload, (OrderCanceled, OrderReconciled)):
                status = state.order(payload.intent_id)
                if status is not None:
                    new = "ACKNOWLEDGED" if status.status in (OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED) else "CLOSED"
                    self.connection.execute("UPDATE trading_outbox SET state=? WHERE intent_id=?", (new, payload.intent_id))
            elif isinstance(payload, FillRecorded):
                order = state.order(payload.fill.intent_id)
                if order is not None and order.status is OrderStatus.FILLED:
                    self.connection.execute(
                        "UPDATE trading_outbox SET state='CLOSED' WHERE intent_id=?",
                        (payload.fill.intent_id,),
                    )
            elif isinstance(payload, OrderRejected):
                pass
            if checkpoint:
                self.connection.execute("INSERT INTO trading_checkpoints(ordinal,digest) VALUES(?,?)",
                                        (event.ordinal, state.digest))

    def outbox(self) -> tuple[tuple[str, str], ...]:
        """Unresolved intents must be inspected, never automatically resubmitted."""
        return tuple((str(a), str(b)) for a,b in self.connection.execute(
            "SELECT intent_id,state FROM trading_outbox WHERE state IN ('PENDING','UNKNOWN') ORDER BY intent_id"
        ))

    def halt_reason(self) -> str | None:
        row = self.connection.execute("SELECT value FROM trading_metadata WHERE key='halt'").fetchone()
        return str(row[0]) if row is not None else None

    def record_halt(self, message: str) -> None:
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO trading_metadata(key,value) VALUES('halt',?)", (message,))

    def clear_halt(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM trading_metadata WHERE key='halt'")
