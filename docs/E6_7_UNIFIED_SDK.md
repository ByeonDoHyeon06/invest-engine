# E6.7 — Unified Engine SDK: canonical design

**Status: planned SDK; public design targets, not executable code.** Four execution roots, typed market sources, Historical/Paper/Session lifecycles, returns and errors, migration, fixtures and release gates are documented **here**. The one companion [23-example cookbook](E6_7_SDK_EXAMPLES.md) shows call sites and expected illustrative outputs. [ADR-0034](adr/0034-unified-sdk.md) retains historical decisions; [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59) tracks implementation. Last consolidation: 2026-11-22.

**Important:** Proposed names and output numbers are neither implemented behavior nor real market/broker test evidence. E5/G1, E6/G2, E7 and optional external E8 remain separately gated. There is no broker-order API in Engine.

## Navigate this design

- [Public API and advanced settings](#public-api-and-advanced-settings)
- [Typed market sources](#typed-market-sources)
- [Historical and Paper simulation](#historical-and-paper-simulation)
- [Continuous Session and Paper runtime](#continuous-session-and-paper-runtime)
- [Return types statuses and illustrative outputs](#return-types-statuses-and-illustrative-outputs)
- [Compatibility migration and acceptance](#compatibility-migration-and-acceptance)
- [External order-execution boundary and release roadmap](#external-order-execution-boundary-and-release-roadmap)
- [All 23 SDK examples with expected behavior](E6_7_SDK_EXAMPLES.md)

## Public API and advanced settings

### One public grammar across basic and advanced use

The 2026-11-22 advanced-DX revision adds a **common typed market source** and removes the need to learn an unrelated public execution path for advanced options. The four primary operations remain unchanged: `simulation`, `research`, `evaluate`, `session`.

| Operation | Market input | Policy surface | Operation |
|---|---|---|---|
| `simulation(...).historical()` | `source=sources.local(...)` or `sources.dataset(...)` | `strategy`, synthetic `capital`, `risk`, `execution`, supported advanced options | finite backtest on the existing historical core |
| `simulation(...).paper()` | `source=sources.alpaca(...)` or `sources.manual()` | **same** simulated portfolio/risk/execution option meanings | async managed or caller-fed Paper **synthetic** account, E7 |
| `research(...)` | **same historical** `source=` | **same** `strategy/capital/risk/execution` plus `search/validation` | registered historical study |
| `evaluate(...)` | supplied `market_data=` one-shot snapshot | `strategy`, verified external `portfolio`, `risk` if supported | proposal only |
| `session(...)` | **same stream/manual** `source=` | `strategy`, `risk` if supported, account snapshot refresh | E7 continuous proposal only |

There are **four roots**, not five: Historical and Paper are terminal methods of Simulation. No `engine.backtest`, separate `engine.paper` or `engine.live` in the proposed unified facade. Legacy working E0–E6 low-level Python/CLI routes stay compatible.

`Engine()` is inert. Source factory creation and `engine.simulation(...)` are inert. Managed Paper and managed Session connect to permitted **market data only** on explicit async-context entry; `sources.manual()` is caller-fed `ingest(event)` for **both** kinds of sessions. `evaluate()` consumes a supplied *snapshot* and deliberately does not open a source/stream. No broker-order submission and no second authoritative live-asset ledger.

### Canonical everyday examples

```python
from invest_engine import Engine, sources, strategies, research

engine = Engine()
strategy = strategies.orb()

historical = sources.local("datasets/AAPL/manifest.json")
result = engine.simulation(
    source=historical, strategy=strategy, capital="100000 USD",
).historical()

study = engine.research(
    source=historical, strategy=strategy, capital="100000 USD",
    search=research.Grid({"opening_range": ["15m", "30m"]}),
)
```

```python
from invest_engine import sources

stream = sources.alpaca(credentials="market-data-secret-ref")

async with engine.simulation(
    source=stream, strategy=my_strategy, capital="100000 USD",
).paper() as paper:
    async for event in paper.events():
        print(event.status)

async with engine.session(source=stream, strategy=my_strategy, symbols=["AAPL"]) as session:
    await session.warmup(validated_history)
    await session.update_portfolio(verified_broker_account_snapshot)
    async for decision in session.decisions():
        print(decision.proposed_orders)
```

For caller-owned network transports use `source=sources.manual()` and `await session.ingest(event)`, or `await paper.ingest(event)`. A declared historical source cannot silently become Paper; a streaming source cannot silently run Historical without a separate explicit dataset acquisition/normalization step. Typed source capabilities, rights, availability timestamps, calendars and ordering must be checked and unsupported configurations blocked.

### One set of settings, additive complexity

### Common option names

| Name | Meaning | Where valid |
|---|---|---|
| `source=` | a typed finite dataset/local manifest, stream provider or manual ingress source | Historical, Paper, Research, Session |
| `strategy=` | same configured strategy/registered read-only Strategy contract | all four |
| `capital=` | simulated initial money only | Simulation, Research |
| `portfolio=` / `session.update_portfolio(...)` | broker-authoritative, timestamped and reconciled immutable snapshot | Evaluate / Session |
| `risk=` | user-configurable limits, **never** weakening mandatory safety boundaries | supported simulation/research/proposal paths |
| `execution=` | **simulation-only** fees, slippage and modeled fills | Simulation, Research |
| `search` / `validation` | bounded strategy search and registered temporal folds | Research |
| `allocation` | optional supported shared-synthetic-account strategy allocation | supported multi-strategy Simulation/Research only |
| `calendar` / `reporting` / `artifact_store` | typed operation-level advanced options, no hidden Engine-global precedence | paths whose capability is actually implemented |

`risk.Limits(...)`, `execution.Model(...)`, `allocation.Weights(...)` and `sources.local/dataset/alpaca/manual(...)` are **proposed public spelling targets** pending E6.7a signature and capability inventory. Preserve existing internal/legacy `risk.Policy`, `execution.Simulation` and historical provider contracts where implemented. The new facade must not publish both old and new names as redundant equivalent entry points.

### The advanced form still runs the same way

```python
from invest_engine import risk, execution

simulation = engine.simulation(
    source=historical,
    strategy=my_strategy,
    capital="100000 USD",
    risk=risk.Limits(max_position="5%", max_daily_loss="2%"),
    execution=execution.Model(commission_bps=10, spread_bps=5),
    calendar=my_exchange_calendar,
    reporting=my_reporting_policy,
)
plan = simulation.inspect()     # optional preflight, not execution or guaranteed I/O-free
result = simulation.historical() # same terminal as quickstart
```

`inspect()` is an **optional read-only** diagnostic of effective config/static capability/blockers, possibly reading explicitly permitted local manifests. It does not execute a strategy, connect a streaming provider, reserve unauthorized holdout or place any order; final runtime validation always applies. E6.7a must settle the exact return and I/O allowances.

Advanced historical/research `Spec` classes, validated immutable normalized plans, prepare/run orchestration, journals, run manifests and CLI interoperability **remain inside the core/compatibility interfaces**. The new fluent SDK **does not require** `engine.prepare(spec)/engine.run(prepared)` just to enable supported advanced settings. One engine, one risk/economic implementation, deterministic parity with existing E5/E6 and old commands; unsupported combinations are typed errors/blocked outcomes, not an alternate reduced-function engine.

### Independent modules and evidence safeguards

`sources` describes where data comes from; independent `data.load/resample/inspect` helpers explicitly process it, while `sources.dataset(validated_dataset)` wraps already loaded normalized data. Do not create a second mandatory `engine.data` execution workflow or allow an injected Engine-global provider to silently override an operation's source. Provider adapters can advertise multiple capabilities but are never assumed licensed or supported without evidence.

`strategies.orb()` and custom Strategy objects share `strategy=`. For **actually supported** multiple strategies use the same root `strategy=[...]` with operation-level `allocation=...` rather than a mandatory nested `strategies.ensemble(...)` run grammar. No promise of shared-account simulation from PR #66 alone. Preserve trusted plugin versioning, read-only causal context, PIT, corporate actions, FX segregation, fees, date windows and holdout restrictions.

See [typed source rules](#typed-market-sources) and [simulation rules](#historical-and-paper-simulation) for exact source capability and lifecycle requirements; [continuous runtime rules](#continuous-session-and-paper-runtime) for managed/manual Session and Paper.

## Typed market sources

Proposed factory namespace:

```python
from invest_engine import sources

historical = sources.local("datasets/AAPL/manifest.json")
memory = sources.dataset(validated_dataset)
stream = sources.alpaca(credentials="market-data-secret-ref")
manual = sources.manual()
```

`sources.local` and `sources.dataset` are **historical finite** inputs; `sources.alpaca` represents a permitted **read-only streaming market feed**, not a broker account/order API; `sources.manual` means the caller feeds normalized events. Each source advertises **typed capabilities** (finite historical vs streaming, optional subscriptions, supported market/event types, data rights and provenance) checked against the selected execution terminal. Factories are inert descriptors; provider I/O begins only on an explicit operation/context entry. The source type *never silently chooses* Historical/Paper/Session. E6.7a must determine whether a provider can implement both historical and streaming capability, and reject unsupported modes without implicit download or feed replacement.

- `simulation(source=historical, ...).historical()` — validated historical replay, no implied network.
- `simulation(source=stream, ...).paper()` — read-only stream + synthetic fills, E7 only.
- `simulation(source=manual, ...).paper()` — external feed via `paper.ingest(event)`, E7 only; source must be explicit.
- `session(source=stream, ...)` — managed read-only market connection; consumer can iterate `session.decisions()`.
- `session(source=manual, ...)` — caller provides `session.ingest(event)`; no implicit transport.
- `research(source=historical, ...)` — E6 licensed historical data and immutable registered study.
- `evaluate(market_data=snapshot, ...)` — no source lifecycle, exactly one verified decision context.

Disallow missing, ambiguous, contradictory or unsupported sources, dual ingestion without a documented serialization policy, unlicensed provider data, data-type/time travel and forged timestamp/availability. Caller-owned streams retain their ownership; provider-managed feeds have explicit context-entry/exit lifecycle. `Engine(data_provider=...)` is **not** a canonical public shortcut because engine-global versus operation-specific source precedence introduces ambiguity. If an actual legacy injection API exists, preserve it separately and test compatibility; do not silently break it.

### C. Stable settings by concept

| Option | Applies to | Meaning / restriction |
|---|---|---|
| `source=` | Historical, Paper, Research, Session | typed market source; only validated source capabilities used |
| `strategy=` | all operations | same configured Strategy/Strategy protocol, read-only context, deterministic snapshots where needed |
| `capital=` | Historical, Paper, Research | simulated opening funds only, never actual broker account |
| `portfolio=` | Evaluate; Session via explicit refresh/ingest | external broker-authoritative immutable verified snapshot, no invented live balance |
| `risk=` | supported trading/proposal paths | user-controllable limits, **cannot relax mandatory hard safety gates** |
| `execution=` | Historical, Paper, Research | **simulated** fees/slippage/fill model; no broker order authority |
| `search=` / `validation=` | Research only | bounded candidate studies, temporal folds/journal/holdout gates |
| `allocation=` | supported multi-strategy simulated paths | single account allocation, not strategy-internal duplicate ledgers |
| `calendar=`, `reporting=`, `artifact_store=` | paths with actual support | explicit typed advanced configuration, not engine-global hidden behavior |

Proposed user-facing policy objects: `risk.Limits(...)` (risk limit configuration) and `execution.Model(...)` (simulated fill/fee model). Names are **DX targets, not claims of existing implementations**; E6.7a must check existing policy contracts, clarify what belongs to mandatory risk vs user limits and settle typed signatures and defaults before implementation. Do not create competing `risk.Policy` and `risk.Limits` as equivalent *new* facade entry points, or multiple execution-model factories for the same semantic purpose. Existing implemented low-level names remain intact.

Strategy presets should use lowercase constructors such as `strategies.orb()`. A custom Strategy uses the same `strategy=` argument. For *supported* multiple strategies, prefer a collection in `strategy=[...]` and one operation-level `allocation=` configuration, rather than a nested ensemble/allocator-specific run grammar; do not imply that PR #66 supplies shared-account simulation automatically.

## Historical and Paper simulation

```python
from invest_engine import sources

result = engine.simulation(
    source=sources.local("datasets/AAPL/manifest.json"),
    strategy=my_strategy, capital="100000 USD",
).historical()

async with engine.simulation(
    source=sources.alpaca(credentials="market-data-secret-ref"),
    strategy=my_strategy, capital="100000 USD",
).paper() as paper:
    async for event in paper.events():
        print(event.status)
```

`Engine()` and `engine.simulation(...)` only configure typed settings and do not perform strategy execution, account access or provider I/O. The terminal method explicitly chooses the **clock/lifecycle** and appropriate source capability; the source never silently chooses a mode.

| Contract | `.historical()` | `.paper()` |
|---|---|---|
| Eligible source | typed historical `sources.local` / `sources.dataset` | E7 streaming market source `sources.alpaca` or manual `sources.manual()` |
| Clock | finite, deterministic historical/availability replay | live observed ingress with explicit causal clock |
| Operation | synchronous result | **async context manager factory**; network only upon permitted context entry |
| Orders/fills/account | **synthetic** ledger, modeled fees and fills | **synthetic** ledger, modeled fees and fills |
| Actual broker API / real account | **none** | **none** |
| Output | typed `SimulationResult`, evidence, results | `PaperSession` events/status and terminal simulated result |
| Core | existing E5 replay/strategy/risk simulation primitives | same shared primitives where actual capabilities permit; E7 ingress and recovery |
| Validation | manifest/PIT/calendar/corporate/actions/fees/source coverage | stream rights, warmup, finalization, staleness, gaps, duplicate/recovery |

A source is a **market-data** origin, not a broker order adapter. `sources.local/dataset` describe finite datasets, `sources.alpaca` is an illustrative read-only real-time provider, and `sources.manual()` means the external application owns normalized ingress. Source classes/names are *design targets subject to E6.7a verification*, not released APIs or a guarantee of access/licensing. A provider supporting two capabilities must advertise them explicitly; no silent download, gap filling or source fallback. Unsupported historical-versus-streaming combinations are typed BLOCKED/ConfigurationError.

### Unified option and advanced API contract

```python
from invest_engine import risk, execution

simulation = engine.simulation(
    source=historical_source,
    strategy=my_strategy,
    capital="100000 USD",
    risk=risk.Limits(max_position="5%", max_daily_loss="2%"),
    execution=execution.Model(commission_bps=10, spread_bps=5),
    calendar=exchange_calendar,
)
plan = simulation.inspect()     # optional read-only preflight
result = simulation.historical()
```

The same `strategy=`, synthetic `capital=`, `risk=` and simulated `execution=` policy concepts apply to Historical/Paper/Research **where supported**. These constructor names, signatures, defaults and any supported advanced options (fill, fees, calendar, allocation, corporate action, PIT, FX, reporting) must be checked against *real* E5/E6 implementation in E6.7a. User limits do not override hard mandatory risk gates. A configured strategy's read-only context, state and canonical event visibility remain identical in supported comparable inputs.

`inspect()` is an optional, read-only config/static capability check which may read declared local manifests; it does not connect a provider, run strategy/orders, or certify unavailable data. Runtime must revalidate. The fluent `.historical()` remains the public execution path regardless of advanced options. Immutable normalized simulation spec, existing `HistoricalBacktest`, typed `BacktestSpec/ResearchSpec` and `prepare/run` internals/low-level imports remain for compatibility and exact economic/CLI parity; they are **not a mandatory second user-facing SDK grammar**.

Paper supports both `source=stream` (managed read-only feed connected on async context entry) and `source=sources.manual()` (caller invokes `await paper.ingest(event)`). Both use one single-writer event/risk/synthetic ledger boundary. Exit cancels/joins owned tasks, records allowed journal/evidence, preserves halt reason, and never mutates an external actual account. Paper's modeled fills may not match any real broker order execution.

## Continuous Session and Paper runtime

### 1. Two different continuous operations

| Public API | Input and state | Result | Actual broker orders |
|---|---|---|---|
| `engine.session(source=...)` | managed read-only market stream OR caller-fed `sources.manual()`; externally authoritative broker snapshots, observation/strategy state only | proposals with `submitted=False` | **never** |
| `engine.simulation(source=..., strategy=..., capital=...).paper()` | same managed streaming source OR `sources.manual()` caller-fed ingress; SDK manages **synthetic** orders/fills/account | Paper synthetic events and terminal status | **never** |

Both return **async context-manager factories**. Examples: `async with engine.session(...) as s:` and `async with engine.simulation(...).paper() as s:`. Creating either factory is inert; entering **either managed-provider context** is the first moment permitted market-data connection may occur. A `sources.manual()` context never connects a provider and uses caller-fed `ingest(event)`. No competing `engine.paper.start()`, `engine.evaluate.session()`, `await simulation.paper()`, `engine.live` or `simulation(...).live()` public spellings. `engine.evaluate(...)` remains a distinct one-shot decision proposal.

E5 HistoricalBacktest currently drives finite EventEnvelope replay and simulated order accounting through multiple existing core services; EventRuntime is only a reducer, not the entire trading engine. E6.7a must inventory actual event, StrategyRunner, fee/fill/order, journal and provider capabilities before designing streaming composition. Existing TradeTick/QuoteTick/Bar/OrderBook domain types do not imply production support for all execution combinations.

### 2. Canonical event and time contract

Accept validated canonical `EventEnvelope` objects at the advanced boundary. Capture source/market/instrument/venue identity, event time, available-at/published-at when source-proven, actual receive time, event ID and optional source sequence. Use timezone-aware UTC and causal visibility from existing core (max of available/received). Never manufacture a missing timestamp, source ordinal, price, volume, quote or market venue. A convenience `market.Trade` must map losslessly, or fail.

One writer serializes event ingest, timer, bar finalization and (for decision sessions) broker-account snapshot refresh. Multiple sources use bounded queues with known cursor/ordinal limits, not assumed global ordering across unprovable vendor streams. Equal canonical retransmission may be deduplicated at ingress only with identity/content proof; conflicting duplicate, sequence gap, time regression, late correction or non-pausable overflow produces typed BLOCKED/HALT rather than silent loss or hindsight resorting. Recorded stream replay preserves availability/receipt ordering and versioned policy.

### 3. Explicit warmup, subscriptions and session state

Session states: `created → warming → ready → paused/halted → operator-reviewed resume or closed`. `await session.warmup(validated_history)` initializes indicators using read-only eligible observations; no warmup simulated trades, actual proposals or future-data leakage. Declared `DataRequirements`, native interval, exchange calendar, DST/early close and gap policy are mandatory. Bar strategies execute on finalized bars only (native or versioned trade aggregation with causal watermark/completeness), not provisional bars; no bar-to-tick reconstruction.

Optional high-level `on_bar/on_tick/on_quote/on_timer` callbacks adapt to supported existing read-only Strategy contracts; unimplemented callback/data combinations remain errors. Stateful strategy snapshots and incremental indicators must replay consistently on the same captured tape.

### 4. Broker snapshot and decision-only boundaries

`session.update_portfolio(snapshot)` binds broker/account ID, positions, currency, buying power, open/unknown orders, as-of/receipt time and state/version; it never mutates the real account or creates a second authoritative ledger. A stale/wrong/incomplete/unreconciled snapshot blocks new exposure. `session.ingest(event)` returns typed observed decision outcome with explicit blockers, reason codes, versioned proposal IDs and expiry; **submitted=False** always. Caller-controlled external execution host may inspect the proposal but must independently check authorization/risk/account state before any future real order.

`engine.simulation(...).paper()` instead owns a completely separate synthetic cash/positions ledger and simulated fills; Paper **cannot** be initialized with a real account's holdings and does not use real trading credentials. Its market provider must only access permitted read-only market-data endpoints; source failure cannot silently change feeds.

### 5. Error handling, restart and shutdown

Record heartbeat, data staleness, latency, queue pressure, replay/source cursors, duplicate/late events, provider rights and memory. Reconnect is not completeness proof. Recovery requires verified cursor/backfill, matching journal/checkpoint/strategy state and, for decision-only sessions, fresh authoritative account reconciliation. No old proposal or simulated order is replayed as a live order. Context exit must be idempotent, join/cancel owned tasks, persist permitted audit and expose terminal reasons. Never log secrets or unauthorized raw market data.

### 6. E6.7a design fixtures and future E7 tests

| Fixture family | Required outcome |
|---|---|
| import/factory | no tasks, broker I/O, market-provider connection or real order path on Engine/factory creation |
| historical/stream parity | same canonical available/received tape and supported policies → equivalent causal decisions; no future visibility |
| gap/duplicate/backpressure | known retries only; conflict, gap and overflow explicit typed halt, no silent dropped events |
| warmup, early close, DST | missing coverage blocks, complete final bars only, no trading during warmup |
| account snapshots | wrong/stale/replayed/unreconciled broker snapshot blocks proposal exposure, no copied authoritative balance |
| Paper execution | synthetic orders/fills/cash only, exact matched simulated-tape policy parity where supported; **0 broker submit calls** |
| recovery/closure | journal/cursor/state parity, no unattended tasks, no repeated proposals after restart |
| source rights and latency | provider permissions, explicitly measured p50/p95/p99 processing, bounded resources, safe audit |
| external E8 boundary | engine exposes proposal values and no `engine.live`; external host owns broker credentials/order lifecycle |

E6.7a designs exact signatures and fixture ownership; E6.7b–e implements the offline simulation/research facade; E7 separately implements the two continuous operations with forward Paper/Shadow gates. **E8 is a separately authorized external execution-host/adapter integration validation**, not an SDK Live entry point. No profitability, trading permission or actual fill guarantee is inferred.

## Return types statuses and illustrative outputs

### 1. Read the output examples correctly

Every code example in `E6_7_SDK_EXAMPLES.md` is followed by a short **Expected contract** explanation: returned type, key fields, and one toy-fixture observable outcome when useful. The type/field shape is **proposed normative API behavior**; numbers/IDs/time in comments are **non-normative fictional fixture data**. Python class `repr` or exact `print` formatting is **not** specified; the fenced snippets here show a **canonical conceptual JSON-like projection**, not an actual terminal transcript. Any stable JSON export requires independent versioned schema tests.

The user-visible DX should answer five questions: *What object do I get? When can it be used? What can it contain? What do I do when it is blocked? Can this trigger actual broker orders?* Return types are intentionally predictable across basic/advanced settings; no branching into a second Spec/prepare/run API.

### 2. Proposed type/field matrix

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

### 3. Shared finite-result shape and statuses

Proposed fields on both `SimulationResult` and `ResearchResult`:
- `status: RunStatus` — `COMPLETED`, `NO_TRADE`, `BLOCKED`, `FAILED` (exact names to lock at E6.7a). **NO_TRADE** is a *valid, eligible run with zero orders*; **BLOCKED** means preconditions/rights/data/risk were not satisfied; **FAILED** means an execution failure. Never collapse the three.
- `summary: Summary | None` — typed, run-specific, and **not silently fabricated** on blocked/incomplete execution.
- `metrics: Metrics | None` — `None` unless eligible, meaningful and computed on a verified window; no invented return statistics.
- `config: EffectiveConfig` — normalized redacted settings including strategy/source versions and policies; no credentials.
- `evidence: EvidenceRefs` — source/manifest identity, run/candidate lineage, timestamps, policy versions and stable hashes *only when available and verified*.
- `blockers: tuple[Blocker, ...]` — typed machine-readable reasons for blocked or halted contexts, not just exception messages.
- `export(path)` — explicit, rights-filtered artifact write; exact receipt/return type to settle.

Specialization: `SimulationResult` adds synthetic fills/order/equity/portfolio artifacts, `ResearchResult` adds typed review/candidate/fold analysis. Paper is an *ongoing* session, not a completed `SimulationResult` until closed. `DecisionResult` has separate proposal semantics, never a fake PnL summary.

### 4. Controlled toy fixtures (not actual market results)

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

#### A. Historical: valid NO_TRADE — example projection

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

#### B. Historical: blocked source — no false successful backtest

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

#### C. Research: completed study, no eligible candidate

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

#### D. Evaluate: one decision, no real order

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

#### E. Paper: managed or manual stream, synthetic activity

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

#### F. Session: single proposal/blocked observation

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

#### G. Optional inspect and data quality

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

### 5. Intended Python types (shape sketch, not a new required API)

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

### 6. E6.7a output-contract acceptance

- Each of the **23 examples** must show **expected type** and concise **observable output/behavior**, linked to a proposed fixture, with no actual-market claims. Basic and advanced invocation must produce the same return type and semantics when policy/source allow.
- Create toy canonical event/manifest fixtures and **exact serialized snapshots** for `toy_no_trade`, `toy_blocked_gap`, `toy_research_rejected`, `toy_snapshot_stale` and both manual/managed E7 ingestion paths. Output snapshots become normative **only after fixture code is implemented and passes tests**.
- Version error reason codes and public enum statuses separately from display text, retain stable field names and deterministic evidence hashes (with secrets redacted). JSON output and Python object repr are not interchangeable.
- Document which fields may be `None` before eligibility, which appear only after session close, and which require explicit export or rights checks; do not invent metrics for invalid/blocked studies.
- Verify the same `Source` and strategy can be used by Paper/Session without crossing simulation/proposal authority; test source rights, stale account, event gaps/duplicates, close/reconnect and **zero real broker-order calls**.
- Preserve current E4/E5/E6 Python/CLI and low-level normalized specs; fail-closed risk/PIT/fees/FX/holdout and market-data licensing remain unchanged. E7/E8 gate release is independent of whether example outputs look plausible.

No content in this document establishes profitability or represents output that has been observed on the current engine.

## Compatibility migration and acceptance

### 2. Previous proposed naming → current target

| Earlier proposed surface | Current design | Compatibility treatment |
|---|---|---|
| `engine.backtest(...)` / `simulation(mode="historical").run()` | `engine.simulation(...).historical()` | retain working low-level HistoricalBacktest and existing CLI |
| `engine.paper.start(...)` / `simulation(mode="paper").start()` | `engine.simulation(...).paper()` | E7 only, async context manager; virtual orders only |
| `engine.live.start(...)` / `simulation(...).live()` | **no Engine live API** | external host/adapter E8 independent |
| `engine.research.create(...).run()` | `engine.research(...)` | internal registered research planning/journal remains |
| `engine.evaluate.session(...)` / `evaluation_session(...)` | `engine.session(...)` | caller-fed **and provider-managed** source variants |
| operation `data=dataset` vs `data_provider=provider` | typed operation `source=...` | finite/streaming/manual capability checked at terminal; no implicit download |
| `Engine(data_provider=...)` | prefer operation-level `source=...` | avoid hidden global precedence; preserve actually implemented legacy calls |
| `engine.data.load/resample/inspect` as primary workflow | `sources.local/dataset` + **optional** standalone `data.*` tools | operations still use `source=`; data tools are independent |
| `risk.Policy` vs other risk policy constructors | proposed `risk.Limits` | typed user limits, never bypass mandatory risk; actual low-level compatibility retained |
| `execution.Simulation` / mixed policy factories | proposed `execution.Model` | only simulated fills/fees, same for historical/paper/research |
| nested `strategies.ensemble(... allocation=...)` | supported `strategy=[...]` with operation-level `allocation=...` | future typed extension only after single simulated account semantics |
| mandatory public `HistoricalSimulationSpec → engine.prepare → engine.run` | ordinary `simulation(...).historical()`, optional `simulation.inspect()` | typed specs and prepare/run remain **internal/legacy advanced** not a second everyday SDK |
| mandatory public `ResearchSpec → prepare/run` | `engine.research(..., search=..., validation=...)` | E6 journal, budgets and holdout unchanged |
| inconsistent result metadata | common finite `status/summary/metrics?/evidence/config/blockers/export` | typed specialized result fields; no fabricated success |

The names `sources.local/dataset/alpaca/manual`, `risk.Limits`, `execution.Model`, `allocation.Weights` and `inspect` are **design candidates** to confirm at E6.7a. Existing actual low-level E0–E6 classes/commands remain; never delete them solely because the future facade grammar is simplified.

### 3. Source capability matrix

| Source | Historical | Paper | Research | Decision Session |
|---|---|---|---|---|
| `sources.local(manifest)` | yes if validated | no implicit live replay | yes if licensed/eligible | no implicit streaming |
| `sources.dataset(immutable_normalized_dataset)` | yes if validated | no implicit live replay | yes if eligible | no implicit streaming |
| `sources.alpaca(market_data_secret_ref)` | no implicit download; historical capability only if separately documented | E7 read-only streaming if permitted | no implicit registered historical study | E7 read-only streaming if permitted |
| `sources.manual()` | no finite dataset inferred | E7 via `paper.ingest(event)` | no historical inference | E7 via `session.ingest(event)` |

A future provider may explicitly implement both historical and streaming capabilities; typed validation and rights/coverage determine permitted use, never the provider brand alone. Historical/Paper/Session do **not** select mode by guessing source type. Conflicting/missing sources, stale evidence, unlicensed feed, gaps, unsupported event/strategy and insufficient warmup reject or halt with typed reasons.

### 4. Updated 23-example phase map

| IDs | Topic | Gate and minimum evidence |
|---|---|---|
| 01–02 | Engine / Historical | E6.7b; no factory I/O, existing E5 economics and evidence parity |
| 03 | managed Paper | E7; permissioned read-only feed, simulated cash/fill, safe close, zero broker orders |
| 04 | direct research | E6.7d; source validation, journal/budget/holdout checks |
| 05 | one-shot decision | signature design E6.7a; no submission and verified snapshot |
| 06 | managed-source Session | E7; subscriptions, causal stream, fresh external portfolio, no submission |
| 07–09 | policy, source, data utilities | E6.7b/c or E7 where streaming; same names, no precedence/fallback |
| 10 | Paper recovery | E7; cursor, journal, gap/duplicate, synthetic account, shutdown |
| 11 | advanced research | E6.7d; same settings without a second public Spec/prepare/run |
| 12–13 | external host/manual Session | E7/E8 external boundary; caller-owned ingress, no SDK real orders |
| 14–16 | indicators, custom strategy, multi-strategy | E6.7c/future capability; Strategy read-only and one synthetic account |
| 17–19 | optional inspect, FX, custom policies/adapters | E6.7b/c; no runtime bypass or reduced feature set |
| 20–23 | results, failures, CLI, external E8 | E6.7e + external E8; stable status/evidence, legacy CLI compatibility, no engine live |

### 5. Golden tests and DoD

1. Python 3.12/3.13 public signature/**return-type/status snapshots for each of 23 examples**, typed source capabilities, no I/O from Engine/source/builder factories, explicit read-only local inspect behavior; managed/manual context exit tests.
2. Same default and advanced parameters in `simulation(...).historical()` compile to immutable validated specs and match existing E5 historical decisions, synthetic fills, ledger/PnL, fees, timestamp evidence and blocked statuses.
3. `research(...)` uses the same input/policies where valid and preserves E6 journal, fold, candidate, budget, purge/embargo, holdout non-access and result evidence.
4. `session(source=stream)` and `session(source=manual)` share causal strategy/risk/portfolio-contract semantics; Paper uses same source capabilities but synthetic account and no real orders. Instrument identity/late/gap/overflow/source rights fail closed.
5. Optional `simulation.inspect()` does not place simulated or actual orders, reserve unauthorized holdout, or connect remote provider. Final execution revalidates.
6. All actual supported fee/fill/FX/PIT/corporate action/multi-symbol/advanced adapters remain available under the facade or explicit versioned low-level escape hatch. Unsupported combinations reject explicitly; real broker account remains authoritative externally.
7. Name and implement deterministic output fixtures (`toy_no_trade_v1`, `toy_blocked_gap_v1`, `toy_research_rejected_v1`, `toy_snapshot_stale_v1`, `toy_manual_paper_v1`, `toy_manual_session_v1`) and lock expected status/reason/evidence/optional fields in separate executable golden tests; **do not treat proposed output panels as test evidence**.
8. Existing actual low-level Python imports and CLI commands unchanged unless an explicitly reviewed migration has parity tests. No actual Live SDK, broker secrets or execution adapter; E7/E8 independent approvals.

**No new execution code in this design PR.** E5/G1, E6/G2, provider rights, real fees and investment profitability remain separate unresolved gates.

## External order-execution boundary and release roadmap

### 6. External execution boundary (not a fifth SDK mode)

Historical/Paper simulation is **not** real execution. The SDK neither hosts nor selects a broker, manages real-money order tokens, submits/cancels orders nor authoritatively stores live holdings. There is **no** `engine.live.start()`, `simulation(...).live()` or `engine.orders.submit()` API. A separate application/execution host may consume versioned `Decision/OrderIntent` values and independently enforce human authorization, pre-trade risk, idempotency, durable outbox, broker-specific rules, order lifecycle/reconciliation and kill switch. Brokerage API imports, credentials and transport belong to optional separately packaged broker adapters; the core only defines normalized types and read-only snapshot contracts. `BrokerProtocol` in existing lower-level design is an integration boundary, not permission to expose a Live SDK. See [ARCHITECTURE](ARCHITECTURE.md) and [INTEGRATIONS](INTEGRATIONS.md).

**E8 roadmap scope:** *optional external execution integration/verification* after separate approval, not an Invest Engine Live capability. The package can remain useful even when no execution host exists. No actual orders permitted by this design revision.

### 7. Roadmap / acceptance

1. **E6.7a:** inventory actual public/low-level API and capabilities; define typed `Source` descriptors, managed/manual ownership, policy names, signatures/overloads, optional `inspect()` preflight, **typed return and status/error contracts for each of 23 examples**, deterministic named toy fixtures/expected snapshots, nullable metric/terminal session semantics, migrations and golden parity ([output guide](E6_7_UNIFIED_SDK.md)).
2. **E6.7b:** inert Engine facade, shared immutable spec/profiles, validated `simulation(...).historical()` and typed results, no core rewrite or networking.
3. **E6.7c:** all implemented supported strategy, provider, data, risk, fill/fees, calendar, corporate action, FX and advanced custom protocols; retain direct core/CLI compatibility.
4. **E6.7d:** `research(...)` with common `source/strategy/capital/risk/execution` options, internal registered specs and CLI parity, journal/evidence/review/report artifacts, batch audit.
5. **E6.7e:** wheel/import/type smoke on 3.12/3.13, API snapshots, economic golden tests, security/failure/blocked, deterministic replay, DX cookbook and measured overhead.
6. **E7:** separately gated `session()` and `simulation(...).paper()` streaming, fault/recovery and forward Paper/Shadow evidence, **zero broker orders**.
7. **E8:** only if separately decided: external execution integration validation in a separate application/adapter project, never an engine Live SDK method.

Completion of an SDK phase does **not** establish strategy profitability, broker/data licensing, PIT completeness, E5/G1 or E6/G2 acceptance, or permission to trade real money.

### 8. Change control

Earlier `engine.backtest()`, `engine.paper.start()`, `engine.live.start()` and `Engine(data_provider=...)` examples are **historical unimplemented design proposals** superseded by this 2026-11-22 decision. [Migration matrix](E6_7_UNIFIED_SDK.md) and [ADR amendment](adr/0034-unified-sdk.md) preserve the trail. Do not delete actually implemented `HistoricalBacktest`, CLI commands or existing low-level imports. Future public API/authority changes require user approval and synchronized issue, ADR, examples, roadmap, status and contract tests before implementation.
