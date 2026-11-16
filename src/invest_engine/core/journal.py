"""SQLite WAL append-only event journal and verified checkpoint storage.

The journal is a local research/runtime foundation, not yet a broker-safe ledger.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from invest_engine.core.codec import decode_event
from invest_engine.core.replay import canonical_bytes
from invest_engine.core.runtime import (
    EventJournalProtocol,
    RuntimeConfig,
    RuntimeState,
    initial_state,
    reduce_event,
)
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import EventEnvelope, MarketPayload


def _state_blob(state: RuntimeState) -> str:
    return json.dumps({
        "run_version": state.run_version,
        "mode": state.mode.value,
        "last_ordinal": state.last_ordinal,
        "observed_at": (
            state.observed_at.isoformat(timespec="microseconds")
            if state.observed_at else None
        ),
        "event_count": state.event_count,
        "digest": state.digest,
        "seen_ids": sorted(state.seen_ids),
        "counts": list(state.counts),
        "status": state.status.value,
        "halt_reason": state.halt_reason,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class SQLiteEventJournal(EventJournalProtocol):
    """Exactly-once local journal append with snapshot in the same SQLite commit."""

    def __init__(self, path: Path | str) -> None:
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    ordinal INTEGER PRIMARY KEY,
                    event_id TEXT UNIQUE NOT NULL,
                    json TEXT NOT NULL,
                    checksum TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    ordinal INTEGER PRIMARY KEY,
                    json TEXT NOT NULL,
                    checksum TEXT NOT NULL
                );
            """)

    def __enter__(self) -> SQLiteEventJournal:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def attach(self, config: RuntimeConfig) -> None:
        identity = json.dumps([config.run_version, config.mode.value], separators=(",", ":"))
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'runtime_identity'"
        ).fetchone()
        if row is not None and row[0] != identity:
            raise InvalidEvent("journal belongs to a different runtime version or mode")
        if row is None:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO metadata(key,value) VALUES('runtime_identity',?)", (identity,)
                )

    def events(self) -> tuple[EventEnvelope[MarketPayload], ...]:
        records: list[EventEnvelope[MarketPayload]] = []
        for ordinal, event_id, body, checksum in self.connection.execute(
            "SELECT ordinal,event_id,json,checksum FROM events ORDER BY ordinal"
        ):
            binary = body.encode("utf-8")
            if hashlib.sha256(binary).hexdigest() != checksum:
                raise InvalidEvent("journal event checksum mismatch")
            event = decode_event(binary)
            if event.ingest_ordinal != ordinal or event.event_id != event_id:
                raise InvalidEvent("journal envelope index mismatch")
            records.append(event)
        return tuple(records)

    def commit_event(
        self,
        event: EventEnvelope[MarketPayload],
        state: RuntimeState,
        *,
        snapshot: bool,
    ) -> None:
        binary = canonical_bytes(event)
        body = binary.decode("utf-8")
        checksum = hashlib.sha256(binary).hexdigest()
        with self.connection:
            self.connection.execute(
                "INSERT INTO events(ordinal,event_id,json,checksum) VALUES (?,?,?,?)",
                (event.ingest_ordinal, event.event_id, body, checksum),
            )
            if snapshot:
                encoded = _state_blob(state)
                self.connection.execute(
                    "INSERT INTO checkpoints(ordinal,json,checksum) VALUES (?,?,?)",
                    (state.last_ordinal, encoded, hashlib.sha256(encoded.encode()).hexdigest()),
                )

    def verify_snapshot(self, state: RuntimeState) -> None:
        latest = self.connection.execute(
            "SELECT ordinal,json,checksum FROM checkpoints ORDER BY ordinal DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            return
        ordinal, body, checksum = latest
        if hashlib.sha256(body.encode()).hexdigest() != checksum:
            raise InvalidEvent("snapshot checksum mismatch")
        if ordinal > state.last_ordinal:
            raise InvalidEvent("snapshot is ahead of journal")
        reconstructed = initial_state(RuntimeConfig(state.run_version, state.mode))
        for event in self.events():
            if event.ingest_ordinal > ordinal:
                break
            reconstructed = reduce_event(reconstructed, event).state
        if _state_blob(reconstructed) != body:
            raise InvalidEvent("snapshot differs from replayed journal state")

    def halt_reason(self) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'halt_reason'"
        ).fetchone()
        return str(row[0]) if row is not None else None

    def record_halt(self, reason: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('halt_reason',?)",
                (reason,),
            )

    def clear_halt(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM metadata WHERE key = 'halt_reason'")
