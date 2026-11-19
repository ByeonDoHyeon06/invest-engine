"""Local durable offline research journal. No order or model deployment access.

SQLite serializes writers. Every read/reopen replays the canonical hash-linked
command history and verifies the stored head. This detects corruption, not a
privileged rewrite of the entire database. No external timestamps or signatures.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from invest_engine.research.candidates import (
    ArmEvidence, Candidate, EvaluationPolicy, ResearchPlan, ResearchRegistry, ResearchWindow,
)
from invest_engine.research.report import canonical_json, sha256

ROOT = "0" * 64


def _duration(raw: dict[str, Any]) -> timedelta:
    return timedelta(microseconds=raw["microseconds"])


def _plan(raw: dict[str, Any]) -> ResearchPlan:
    windows = tuple(ResearchWindow(
        **{**w, "start": datetime.fromisoformat(w["start"]),
           "end": datetime.fromisoformat(w["end"])}) for w in raw["windows"])
    candidates = tuple(Candidate(
        **{**c, "training_cutoff": datetime.fromisoformat(c["training_cutoff"])})
        for c in raw["candidates"])
    p = raw["policy"]
    policy = EvaluationPolicy(p["min_exit_fills"], Decimal(p["max_drawdown"]),
                              Decimal(p["min_mean_excess"]), _duration(p["embargo"]))
    return ResearchPlan(raw["plan_id"], datetime.fromisoformat(raw["registered_at"]),
                        windows, candidates, tuple(raw["costs"]), policy,
                        _duration(raw["label_horizon"]),
                        tuple((pair[0], pair[1]) for pair in raw["baseline_config_sha256"]))


def _arm(raw: dict[str, Any]) -> ArmEvidence:
    return ArmEvidence(**{**raw, **{
        key: Decimal(raw[key]) for key in ("opening_cash", "net_pnl", "max_drawdown")
    }})


def _apply(
    states: dict[str, ResearchRegistry], plan_id: str, kind: str, body: bytes,
) -> ResearchRegistry:
    raw = json.loads(body)
    if kind == "register":
        plan = _plan(raw)
        if canonical_json(plan) != body or plan.plan_id != plan_id:
            raise ValueError("NONCANONICAL_RESEARCH_PLAN")
        if plan_id in states:
            raise ValueError("PLAN_ID_ALREADY_REGISTERED")
        for existing in states.values():
            for old in existing.plan.windows:
                for new in plan.windows:
                    if old.split != "test" and new.split != "test":
                        continue
                    same_digest = old.data_sha256 == new.data_sha256
                    overlap = (old.instrument_key == new.instrument_key
                               and old.start < new.end and new.start < old.end)
                    if same_digest or overlap:
                        raise ValueError("HOLDOUT_ALREADY_RESERVED_OR_EXPOSED")
        return ResearchRegistry(plan)
    if plan_id not in states:
        raise ValueError("UNREGISTERED_PLAN")
    state = states[plan_id]
    if kind == "record":
        arm = _arm(raw)
        if canonical_json(arm) != body:
            raise ValueError("NONCANONICAL_ARM_EVIDENCE")
        if any(previous.run_sha256 == arm.run_sha256
               for key, other in states.items() if key != plan_id
               for previous in other.evidence):
            raise ValueError("CROSS_PLAN_RUN_IDENTITY_REUSED")
        return state.record(arm)
    if body != b"null":
        raise ValueError("INVALID_COMMAND_BODY")
    if kind == "lock":
        return state.lock_validation()
    if kind == "finalize":
        return state.finalize_test()
    raise ValueError("UNKNOWN_RESEARCH_COMMAND")


class ResearchJournal:
    """Single local database: globally reserve test intervals before evaluation.

    A failed registration/record/lock/finalize leaves no partial event. Never
    delete historical rows to reclaim holdout. Fresh databases, aliases, external
    access to data and operator-supplied evidence are not controlled here.
    """

    def __init__(self, path: str | Path) -> None:
        self._db = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        try:
            self._db.execute("PRAGMA busy_timeout=30000")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("BEGIN IMMEDIATE")
            self._db.execute("""CREATE TABLE IF NOT EXISTS research_events (
                seq INTEGER PRIMARY KEY, plan_id TEXT NOT NULL, kind TEXT NOT NULL,
                body BLOB NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL
            )""")
            self._db.execute("""CREATE TABLE IF NOT EXISTS research_head (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                seq INTEGER NOT NULL, digest TEXT NOT NULL
            )""")
            self._db.execute("INSERT OR IGNORE INTO research_head VALUES (1, 0, ?)", (ROOT,))
            self._db.commit()
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ResearchJournal:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _replay(self) -> tuple[dict[str, ResearchRegistry], int, str]:
        # One SQL statement obtains a consistent head + history snapshot.
        rows = self._db.execute(
            """SELECT h.seq, h.digest, e.seq, e.plan_id, e.kind,
                      e.body, e.previous, e.digest
               FROM research_head h LEFT JOIN research_events e ON 1=1
               WHERE h.singleton=1 ORDER BY e.seq"""
        ).fetchall()
        if not rows:
            raise ValueError("RESEARCH_HEAD_MISSING")
        states: dict[str, ResearchRegistry] = {}
        seq, previous = 0, ROOT
        for head_seq, head_digest, n, plan_id, kind, body, link, digest in rows:
            if n is None:
                continue
            if (n != seq+1 or previous != link or not isinstance(body, bytes)
                    or sha256((n, plan_id, kind, body.hex(), link)) != digest):
                raise ValueError("RESEARCH_JOURNAL_INTEGRITY")
            try:
                next_state = _apply(states, plan_id, kind, body)
            except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                raise ValueError("RESEARCH_JOURNAL_INVALID_HISTORY") from exc
            if states.get(plan_id) is next_state:
                raise ValueError("RESEARCH_JOURNAL_DUPLICATE_COMMAND")
            states[plan_id] = next_state
            seq, previous = n, digest
        if (seq, previous) != (rows[0][0], rows[0][1]):
            raise ValueError("RESEARCH_HEAD_MISMATCH")
        return states, seq, previous

    def get(self, plan_id: str) -> ResearchRegistry:
        states, _, _ = self._replay()
        if plan_id not in states:
            raise ValueError("UNREGISTERED_PLAN")
        return states[plan_id]

    def _commit(self, plan_id: str, kind: str, payload: object) -> ResearchRegistry:
        body = canonical_json(payload)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            states, seq, previous = self._replay()
            if kind == "register" and plan_id in states:
                if isinstance(payload, ResearchPlan) and states[plan_id].plan == payload:
                    self._db.commit()
                    return states[plan_id]
                raise ValueError("PLAN_ID_ALREADY_REGISTERED")
            next_state = _apply(states, plan_id, kind, body)
            if next_state is not states.get(plan_id):
                n = seq + 1
                digest = sha256((n, plan_id, kind, body.hex(), previous))
                self._db.execute("INSERT INTO research_events VALUES (?,?,?,?,?,?)",
                                 (n, plan_id, kind, body, previous, digest))
                self._db.execute("UPDATE research_head SET seq=?,digest=? WHERE singleton=1",
                                 (n, digest))
            self._db.commit()
            return next_state
        except BaseException:
            self._db.rollback()
            raise

    def register(self, plan: ResearchPlan) -> ResearchRegistry:
        return self._commit(plan.plan_id, "register", plan)

    def record(self, plan_id: str, arm: ArmEvidence) -> ResearchRegistry:
        return self._commit(plan_id, "record", arm)

    def lock_validation(self, plan_id: str) -> ResearchRegistry:
        return self._commit(plan_id, "lock", None)

    def finalize_test(self, plan_id: str) -> ResearchRegistry:
        return self._commit(plan_id, "finalize", None)
