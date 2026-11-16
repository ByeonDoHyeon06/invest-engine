# E2 — Deterministic Event Runtime

**Status:** Implemented and CI-verified in PR #15 (2026-11-16). **No trading/orders, no Live adapter.**

## Scope and architecture

The E2 runtime converts immutable, quality-approved `EventEnvelope[MarketPayload]` objects into immutable `RuntimeState` transitions and pure observation-dispatch commands. It does **not** execute strategies, trade, send broker requests, or calculate P&L.

Modules:
- `core/runtime.py`: `RuntimeConfig`, `RuntimeState`, pure `reduce_event`, `Subscription`, `EventRuntime` coordinator.
- `core/features.py`: feature-dependency directed acyclic graph and stable topological order; **no feature calculations yet**.
- `core/codec.py`: versioned canonical JSON codec for E0 market-event payloads.
- `core/journal.py`: SQLite WAL durable append-only journal, checkpoints, replay verification and halt marker.
- `core/replay.py`: pre-existing E0 hash-only verifier remains separate. E2 uses a stateful reducer.

## Event order and Point-in-Time rules

`EventRuntime.accept(event)` applies **one event at a time** in a single writer. No implicit event reordering. Upstream ingestion has to assign globally contiguous ordinals `0, 1, 2…`; this is different from provider-local sequence numbers.

The following conditions are **required**:
1. `event.ingest_ordinal == state.last_ordinal + 1` and `event_id` not seen before.
2. No `quality_flags`: quarantined/stale/broken feeds are excluded by the E1 QualityGate.
3. `Bar.finalized` is true; a partial bar must not be exposed as final.
4. Observation instant = `max(available_at, received_at)` and cannot precede the previous accepted observation.
5. Runtime mode is `BACKTEST` or `PAPER`; `LIVE` is explicitly rejected until E8.

`available_at` is the earliest source-visible moment, whereas `received_at` records actual receipt. Using the maximum prevents strategies seeing an event before arrival. An earlier `event_time` is allowed if receipt was delayed; it does not imply permission to rewrite historical decisions. Feed source sequence gaps are detected by E1, not guessed by E2.

The reducer returns `Transition(new_state, commands)`. `ObservationDispatch` means **intended routing only**; no callbacks or external side effects occur in the pure reducer. Subscriptions are matched by event type, market, optionally Bar interval, sorted by subscription ID.

## Determinism contract

Initial state hash seeds the runtime version and mode. Each accepted event contributes its **canonical encoded bytes** to the evolving SHA-256 digest with length-prefix encoding. Counts, seen IDs, observed timestamp and ordinal are immutable fields.

Deterministic means identical **recorded event order + code + run version + policy/config** produce identical state. It does not imply that actual asynchronous delivery or future market data are predictable. Other runtime configuration fields not currently encoded in `run_version` are the caller's responsibility; changes to economically meaningful policies must increment version and be captured in the later Experiment Manifest.

## Journal and restart policy

`SQLiteEventJournal(path)` uses SQLite WAL and `synchronous=FULL`. A successful `accept` must commit the event first; the in-memory state is published **after commit**. Periodic checkpoint inserts happen in the same transaction as the corresponding event.

On restart `EventRuntime(config, journal=journal)`:
1. checks bound run identity/version;
2. loads ordered canonical events and verifies each checksum;
3. deterministically replays all stored events;
4. verifies the latest checkpoint against independently replayed prefix state;
5. restores a persisted HALTED marker, if any.

This is deliberately **correctness-first**: restart currently replays the full journal (O(number of events)), even if a snapshot exists. Efficient snapshot+tail recovery is an E7 optimization requiring state/codec migration and corruption handling.

**Failure behavior:** bad event, duplicate, noncontiguous ordinal, clock rollback, storage failure → `RuntimeStatus.HALTED`. No new event is accepted until `resume_after_review(reviewed=True)`. The deliberate review flag is not a user-auth mechanism; the E7/E8 host must implement authorization and reconciliation. If the storage medium fails during halt recording, the in-memory process halts but the halt flag might be unavailable after restart: **an operational host must treat durable-storage faults as fatal and prevent unattended restart.**

Checksums detect accidental corruption; they are **not tamper-proof signatures** against a malicious actor with write access. Encryption, database permissions, backup, hardened deployments and authenticated audit logs are future deployment work.

## Examples (synthetic data only)

```python
from pathlib import Path
from invest_engine.core.fixtures import synthetic_ticks
from invest_engine.core.runtime import EventRuntime, RuntimeConfig
from invest_engine.core.journal import SQLiteEventJournal
from invest_engine.domain.primitives import InstrumentId, Market

instrument = InstrumentId(Market.KR, "KRX", "SYN1", "SYN", "KRW")
config = RuntimeConfig("e2-example-v1", snapshot_interval=10)

with SQLiteEventJournal(Path("synthetic-events.sqlite")) as journal:
    runtime = EventRuntime(config, journal=journal)
    for event in synthetic_ticks(instrument, count=25):
        runtime.accept(event)
    print(runtime.state.event_count, runtime.state.digest)
```

The above example writes a local synthetic-event journal; it will reject rerunning the same 0..24 inputs on an existing journal. To reopen existing state, instantiate the runtime with the journal and inspect `runtime.state`. The example never contacts any broker.

## Tests and evidence

- `PYTHONPATH=src python -m pytest -q` (local test environment: 96 passed, 3 skipped due to optional Hypothesis/PyArrow not installed).
- GitHub CI for PR #15: Python 3.12 and 3.13 each **99 passed**, with Ruff, mypy and basic secrets guard green.
- Covers 500-event repeatability, order/clock/duplicate rejection, routing, 5 payload codec roundtrips, checkpoint/tail replay, corruption detection, persisted HALTED, failed-journal write, feature DAG cycles.

## Explicitly deferred

Actual trading-state reducer, account/risk ledger, order Outbox, strategy plugins, feature computations, broker reconciliation, read-only strategy context, production logging/authentication and `LIVE` mode remain **not implemented**. E3–E8 own those features. The current SQLite journal is **not** a transactionally complete live order ledger.

## Next

E3 begins with a pure `Portfolio` and `OrderIntent/OrderState` contract plus simulated fills and risk; do not confuse `ObservationDispatch` with an order-submission command. Consult `docs/RISK_EXECUTION.md` and Issue #4.
