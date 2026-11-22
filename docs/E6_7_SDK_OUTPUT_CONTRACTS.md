# E6.7a — Expected SDK returns, example outputs and acceptance fixtures

**STATUS: PROPOSED PUBLIC CONTRACT, NOT EXECUTABLE.** This document specifies the intended **observable behavior**, not a real run or benchmark. All values under **ILLUSTRATIVE FIXTURE OUTPUT** are invented *toy test-fixture examples*, **not computed from AAPL/Alpaca, broker accounts, historic research, or the current engine**. No rates of return, trading fills, or broker permission may be inferred. Exact types, field names and serialized formats must be checked/locked in E6.7a before coding. See [23 usage examples](E6_7_SDK_EXAMPLES.md), [SDK spec](E6_7_UNIFIED_SDK.md), [public grammar](E6_7_PUBLIC_DX_GRAMMAR.md), [ADR-0034](adr/0034-unified-sdk.md), [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59).

## 1. Read the output examples correctly

Every code example in `E6_7_SDK_EXAMPLES.md` is followed by a short **Expected contract** explanation: returned type, key fields, and one toy-fixture observable outcome when useful. The type/field shape is **proposed normative API behavior**; numbers/IDs/time in comments are **non-normative fictional fixture data**. Python class `repr` or exact `print` formatting is **not** specified; the fenced snippets here show a **canonical conceptual JSON-like projection**, not an actual terminal transcript. Any stable JSON export requires independent versioned schema tests.

The user-visible DX should answer five questions: *What object do I get? When can it be used? What can it contain? What do I do when it is blocked? Can this trigger actual broker orders?* Return types are intentionally predictable across basic/advanced settings; no branching into a second Spec/prepare/run API.

## 2. Proposed type/field matrix

| Expression | Intended type | Observables and lifecycle | Side effect boundary |
|---|---|---|---|
| `Engine()` | `Engine` | inert facade; no automatic position or connection | no I/O |
| `sources.local/dataset/alpaca/manual(...)` | `MarketSource` descriptor (typed capabilities) | `kind`, `capabilities`, source identity/provenance *when available* | creation inert, never broker order permission |
| `engine.simulation(...)` | `SimulationPlan` (configured builder, not an executed run) | `inspect()` optional, `historical()` or `paper()` terminal | no provider connect or run on construction |
| `simulation.inspect()` | `PlanPreview` | `effective_config`, `blockers`, `capabilities`, `config_hash` if safely computable | optional local config/manifest read; no network, strategy execution or holdout |
| `simulation.historical()` | `SimulationResult` | shared finite fields plus synthetic `fills`, `equity`, `portfolio` | bounded local historical synthetic fills only |
| `simulation.paper()` | `AsyncContextManager[PaperSession]` | on entry `PaperSession`; `events()` emits `PaperEvent`, `status` is session state, `result` terminal-only | permitted read-only provider I/O on entry or caller-owned `ingest`, synthetic ledger only |
| `engine.research(...)` | `ResearchResult` | shared finite fields plus `review`, `best_candidate` (possibly `None`) and candidate lineage | registered historical study only; respects journal/holdout |
| `engine.evaluate(...)` | `DecisionResult` | `status`, `reason_codes`, `blockers`, `proposed_orders`, input evidence, `submitted=False` for any proposed orders | one snapshot, no transport or simulated fills |
| `engine.session(...)` | `AsyncContextManager[DecisionSession]` | on entry `DecisionSession`; `decisions()` for managed source or `ingest(event)` for manual; `status` | observation/proposals only, no synthetic or real ledger |
| `data.load/resample/inspect(...)` | validated dataset / data view / `DataQualityReport` | typed data, `blockers`, provenance and transformation evidence | explicit data operations, never mode switch |
| `indicators.*` | typed numeric feature series | deterministic values after warmup, missing prefix where insufficient observations | no Engine state, no market I/O |
| `result.export(path)` | `ArtifactReceipt` **proposed** | `location`, `schema_version`, `content_hash`, `redacted` | explicit permitted write only; no raw restricted feed/broker secrets |

**E6.7a open questions:** choose exact Python enum names (below are targets), typed Money/Decimal display, whether `export()` returns a receipt or path, whether `best_candidate` is a separate field or nested under review, and whether a `PlanPreview.config_hash` can be computed without full eligible source verification. Do **not** pretend these names already exist.

## 3. Shared finite-result shape and statuses

Proposed fields on both `SimulationResult` and `ResearchResult`:
- `status: RunStatus` — `COMPLETED`, `NO_TRADE`, `BLOCKED`, `FAILED` (exact names to lock at E6.7a). **NO_TRADE** is a *valid, eligible run with zero orders*; **BLOCKED** means preconditions/rights/data/risk were not satisfied; **FAILED** means an execution failure. Never collapse the three.
- `summary: Summary | None` — typed, run-specific, and **not silently fabricated** on blocked/incomplete execution.
- `metrics: Metrics | None` — `None` unless eligible, meaningful and computed on a verified window; no invented return statistics.
- `config: EffectiveConfig` — normalized redacted settings including strategy/source versions and policies; no credentials.
- `evidence: EvidenceRefs` — source/manifest identity, run/candidate lineage, timestamps, policy versions and stable hashes *only when available and verified*.
- `blockers: tuple[Blocker, ...]` — typed machine-readable reasons for blocked or halted contexts, not just exception messages.
- `export(path)` — explicit, rights-filtered artifact write; exact receipt/return type to settle.

Specialization: `SimulationResult` adds synthetic fills/order/equity/portfolio artifacts, `ResearchResult` adds typed review/candidate/fold analysis. Paper is an *ongoing* session, not a completed `SimulationResult` until closed. `DecisionResult` has separate proposal semantics, never a fake PnL summary.

## 4. Controlled toy fixtures (not actual market results)

These named *future fixture proposals* must be implemented as deterministically replayable offline tests, with published fixture inputs and approval of their expected outcomes before the output text becomes an executable golden test:

| Fixture ID | Inputs / expected scenario | Acceptance meaning |
|---|---|---|
| `toy_no_trade_v1` | two/three eligible finalized toy bars, strategy explicitly returns NO_ACTION, synthetic opening 100,000 USD | completed eligible run with **zero synthetic orders**, `RunStatus.NO_TRADE`, deterministic unchanged synthetic cash, no claim of profit |
| `toy_blocked_gap_v1` | recorded finite tape has required missing interval or unsupported rights/provenance | `RunStatus.BLOCKED` and explicit `DATA_GAP`/`SOURCE_NOT_ELIGIBLE` reason; no fabricated fills/metrics |
| `toy_research_rejected_v1` | 2 predeclared configurations, eligible folds but both fail qualifying gate | `ResearchResult.best_candidate is None`, review has typed no-eligible explanation; holdout untouched |
| `toy_snapshot_stale_v1` | externally supplied account snapshot exceeds declared freshness threshold | `DecisionStatus.BLOCKED`, `SNAPSHOT_STALE` reason, `proposed_orders=()`, broker orders **0** |
| `toy_decision_no_action_v1` | valid market and account snapshots, strategy chooses NO_ACTION | `DecisionStatus.NO_ACTION` and zero proposals; no synthetic account |
| `toy_manual_paper_v1` | deterministic normalized received events + modeled synthetic fill, with adequate warmup | `PaperEvent`/synthetic fill IDs and terminal audited simulated ledger, **no actual broker orders** |
| `toy_manual_session_v1` | same canonical observations and externally verified account snapshot | proposal/no-action stream, no synthetic fills/cash ledger; actual order-submit calls **0** |

The fixture outcomes in the table are **design expectations**, not evidence tests have already passed.

### A. Historical: valid NO_TRADE — example projection

```python
# ILLUSTRATIVE FIXTURE OUTPUT for toy_no_trade_v1, NOT the AAPL example.
# Proposed fields and illustrative values; not real stdout or test evidence.
{
    "type": "SimulationResult",
    "status": "NO_TRADE",
    "summary": {
        "starting_cash": {"amount": "100000.00", "currency": "USD"},
        "ending_cash": {"amount": "100000.00", "currency": "USD"},
        "synthetic_fills": 0
    },
    "metrics": None,  # insufficient meaningful trade metrics; do not pretend gain
    "blockers": [],
    "evidence": {"fixture": "toy_no_trade_v1", "dataset_verified": True}
}
```

`NO_TRADE` is *not* an error. If zero-trade return/drawdown become valid derived metrics, their semantics must be specified and tested rather than silently equating `None` with zero.

### B. Historical: blocked source — no false successful backtest

```python
# ILLUSTRATIVE FIXTURE OUTPUT for toy_blocked_gap_v1
{
    "type": "SimulationResult",
    "status": "BLOCKED",
    "summary": None,
    "metrics": None,
    "blockers": [{"code": "DATA_GAP", "at": "toy_bar_002"}],
    "evidence": {"fixture": "toy_blocked_gap_v1"},
    "fills": []
}
```

An invalid configuration *before* a run can instead raise typed `errors.ConfigurationError` with machine-readable `reason_codes`; a started run that discovers unsafe market data returns a typed blocked state with retained evidence where possible. The exact boundary needs E6.7a tests.

### C. Research: completed study, no eligible candidate

```python
# ILLUSTRATIVE FIXTURE OUTPUT for toy_research_rejected_v1
{
    "type": "ResearchResult",
    "status": "COMPLETED",
    "review": {
        "evaluated_candidates": 2,
        "eligible_candidates": 0,
        "reason_codes": ["NO_ELIGIBLE_CANDIDATE"]
    },
    "best_candidate": None,
    "metrics": None,
    "blockers": [],
    "evidence": {"fixture": "toy_research_rejected_v1", "holdout_accessed": False}
}
```

A study may finish its eligible research work with no accepted strategy. `best_candidate=None` is distinct from a blocked data/journal study; neither implies deployment or holdout release.

### D. Evaluate: one decision, no real order

```python
# ILLUSTRATIVE FIXTURE OUTPUT for toy_snapshot_stale_v1
{
    "type": "DecisionResult",
    "status": "BLOCKED",
    "reason_codes": ["SNAPSHOT_STALE"],
    "blockers": [{"code": "SNAPSHOT_STALE"}],
    "proposed_orders": [],
    "submitted": False,
    "metrics": None
}
```

On a *separately eligible* proposal fixture, a `proposed_orders` item would be a typed `OrderIntent` carrying instrument/side/quantity/expiry/identity and `submitted=False`; its existence **never** implies a broker order was placed. Do not invent an order recommendation from a stale or missing snapshot.

### E. Paper: managed or manual stream, synthetic activity

```python
# ILLUSTRATIVE OUTPUT SHAPE for toy_manual_paper_v1 (E7 only)
{
    "type": "PaperEvent",
    "status": "READY",
    "event_id": "toy:event:003",
    "synthetic_fills": [
        {"id": "sim:fill:001", "quantity": "1", "price": "100.00",
         "currency": "USD", "real_broker_order": False}
    ],
    "reason_codes": []
}
# SessionState on close: CLOSED, terminal PaperResult accessible only after close.
# This value is from a proposed toy fixture, not a live or actual market fill.
```

Paper's session state (`WARMING/READY/HALTED/CLOSED`) is **not** the same enum as completed finite run status or decision status. Streaming output is an ordered **event stream**, not `print(result.summary)` on every tick. Synthetic cash/positions must reconcile with modeled fills and fees in the terminal PaperResult.

### F. Session: single proposal/blocked observation

```python
# ILLUSTRATIVE OUTPUT SHAPE for toy_manual_session_v1 (E7 only)
{
    "type": "DecisionResult",
    "status": "NO_ACTION",
    "reason_codes": [],
    "blockers": [],
    "proposed_orders": [],
    "submitted": False
}
# SessionState: READY while consuming; CLOSED after exit.
# 0 simulated fills, 0 actual broker orders.
```

For a stale real-account snapshot, the same Session produces `BLOCKED/SNAPSHOT_STALE` and no new proposal exposure. The account remains authoritative outside the Engine.

### G. Optional inspect and data quality

```python
# ILLUSTRATIVE PREVIEW ONLY; no run has occurred.
{
    "type": "PlanPreview",
    "effective_config": {
        "source_kind": "historical",
        "capital": {"amount": "100000.00", "currency": "USD"}
    },
    "capabilities": ["historical_replay"],
    "blockers": [],
    "strategy_executed": False,
    "provider_connected": False
}
# DataQualityReport.blockers may instead include DATA_GAP or MISSING_RIGHTS.
# Empty preview blockers are not a guarantee execution cannot later block.
```

## 5. Intended Python types (shape sketch, not a new required API)

```python
# PROPOSED TYPE SHAPE — not a runnable module or finalized signatures
class RunStatus(Enum):
    COMPLETED = "completed"
    NO_TRADE = "no_trade"
    BLOCKED = "blocked"
    FAILED = "failed"

class DecisionStatus(Enum):
    PROPOSED = "proposed"
    NO_ACTION = "no_action"
    BLOCKED = "blocked"
    WARMING = "warming"

class SessionState(Enum):
    CREATED = "created"
    WARMING = "warming"
    READY = "ready"
    PAUSED = "paused"
    HALTED = "halted"
    CLOSED = "closed"

@dataclass(frozen=True)
class Blocker:
    code: str            # versioned reason-code enum to be locked
    detail: str | None

@dataclass(frozen=True)
class DecisionResult:
    status: DecisionStatus
    proposed_orders: tuple[OrderIntent, ...]
    reason_codes: tuple[str, ...]
    blockers: tuple[Blocker, ...]
    evidence: EvidenceRefs  # source + account snapshot identity
    submitted: Literal[False] = False  # *never* an execution permission

@dataclass(frozen=True)
class SimulationResult:
    status: RunStatus
    summary: SimulationSummary | None
    metrics: SimulationMetrics | None
    config: EffectiveConfig
    evidence: EvidenceRefs
    blockers: tuple[Blocker, ...]
    fills: Sequence[SyntheticFill]  # typed, may be lazily paged
    # + export(path) -> ArtifactReceipt (exact return under design)
```

This sketch illustrates **read-only semantics, typed statuses and blocked/no-trade separation**; exact class names/exports, `Decimal/Money` wrappers, optional fields, `ResearchResult` and `PaperResult` type shapes must be agreed via E6.7a, versioned and tested. Do not hard-code a fake `repr`, implicit floats, mutable live account or actual broker submit path.

## 6. E6.7a output-contract acceptance

- Each of the **23 examples** must show **expected type** and concise **observable output/behavior**, linked to a proposed fixture, with no actual-market claims. Basic and advanced invocation must produce the same return type and semantics when policy/source allow.
- Create toy canonical event/manifest fixtures and **exact serialized snapshots** for `toy_no_trade`, `toy_blocked_gap`, `toy_research_rejected`, `toy_snapshot_stale` and both manual/managed E7 ingestion paths. Output snapshots become normative **only after fixture code is implemented and passes tests**.
- Version error reason codes and public enum statuses separately from display text, retain stable field names and deterministic evidence hashes (with secrets redacted). JSON output and Python object repr are not interchangeable.
- Document which fields may be `None` before eligibility, which appear only after session close, and which require explicit export or rights checks; do not invent metrics for invalid/blocked studies.
- Verify the same `Source` and strategy can be used by Paper/Session without crossing simulation/proposal authority; test source rights, stale account, event gaps/duplicates, close/reconnect and **zero real broker-order calls**.
- Preserve current E4/E5/E6 Python/CLI and low-level normalized specs; fail-closed risk/PIT/fees/FX/holdout and market-data licensing remain unchanged. E7/E8 gate release is independent of whether example outputs look plausible.

No content in this document establishes profitability or represents output that has been observed on the current engine.
