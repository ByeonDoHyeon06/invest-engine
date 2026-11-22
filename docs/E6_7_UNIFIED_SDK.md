# E6.7 — Unified Engine SDK (four-operation public design)

**Status: PLANNED, NOT EXECUTABLE.** User-approved public-design consolidation, 2026-11-22. This replaces earlier **unimplemented** proposals to expose `engine.backtest()`, `engine.paper.start()`, or `engine.live.start()`. Tracking [#59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59), [ADR-0034](adr/0034-unified-sdk.md), [23 examples](E6_7_SDK_EXAMPLES.md), [old→new matrix](E6_7_API_CONTRACT_MATRIX.md), [simulation contract](E6_7_SIMULATION_CONTRACT.md) and [streaming contract](E6_7_STREAMING_CONTRACT.md). No E5/E6 gates, Paper deployment or broker-order authority granted by this design.

## 1. Purpose and design rules

One **inert, mode-neutral** `Engine()` with exactly **four primary public operations**:

| Operation | Responsibility | Runtime |
|---|---|---|
| `engine.simulation(...)` | configure simulated cash, strategy/risk/fees and choose **`.historical()`** (past finite replay) or **`.paper()`** (real-time simulated trading) | historical: E6.7b–e; paper: E7 |
| `engine.research(...)` | registered candidate comparison, parameter search, walk-forward, evidence and review; may orchestrate multiple historical simulations | E6.7d |
| `engine.evaluate(...)` | single causal decision based on externally supplied market/account snapshots; **proposals only** | signature E6.7a, implementation separately gated |
| `engine.session(...)` | continuously ingest caller-owned market events and broker-authoritative account snapshots for **proposals only** | E7 |

No `Engine.offline()`, `mode="live"`, `engine.backtest()` convenience alias, `engine.paper` namespace or `engine.live` namespace in the *new unified SDK*. Implemented legacy E4/E5/E6 Python/CLI entry points remain supported and must not be deleted merely because the new facade is smaller. No magical trading switch or automatic broker setup.

The same deterministic market-event/strategy/allocator/risk core serves the appropriate supported pathways. Historical and Paper both simulate cash/order/fill accounting; Evaluate and Session **do not** create simulated trading accounts or submit orders. A real broker's account remains authoritative in the **external application**; the engine observes verified snapshots, never duplicates a real asset database.

## 2. Canonical developer experience

### Historical simulation (formerly SDK backtest)

```python
from invest_engine import Engine, strategies

engine = Engine()
result = engine.simulation(
    data="datasets/AAPL/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
).historical()

print(result.status, result.summary)
result.export("artifacts/aapl")
```

### Real-time Paper (simulated trading, E7 only)

```python
async with engine.simulation(
    data_provider=market_data_provider,
    strategy=strategies.orb(),
    capital="100000 USD",
).paper() as session:
    async for event in session.events():
        print(event.status)
```

### Research

```python
from invest_engine import research

study = engine.research(
    data=validated_dataset,
    strategy=strategies.orb(),
    capital="100000 USD",
    search=research.Grid({"opening_range": ["5m", "15m", "30m"]}),
    validation=research.WalkForward(train="12M", validation="3M", step="3M"),
)
print(study.review, study.best_candidate)
```

### One-shot decision and continuous decision session

```python
decision = engine.evaluate(
    market_data=market_snapshot,
    portfolio=broker_account_snapshot,
    strategy=strategies.orb(),
)

async with engine.session(symbols=["AAPL"], strategy=strategies.orb()) as s:
    await s.warmup(validated_history)
    await s.update_portfolio(broker_account_snapshot)
    async for event in normalized_market_stream:
        decision = await s.ingest(event)
        print(decision.proposed_orders)  # never submitted
```

Only Historical's synchronous execution belongs to the initial offline SDK. The future streaming and Paper examples require E7 separately; no actual broker orders from any engine method.

## 3. Simulation execution semantics

`engine.simulation(...)` is an **inert configuration/builder** with shared typed inputs `strategy`, `capital`, `risk`, `execution` and optional supported policies. **The terminal method defines the time/data/ownership contract**:

- `.historical()`: synchronous finite replay, explicit validated `data=` and exchange calendar, versioned/evidence-hashed spec, simulated fills and cash; returns finite `SimulationResult`.
- `.paper()`: **async context-manager factory** with explicit streaming `data_provider=`, simulated ledger, source freshness, warmup, incomplete bars, gap/duplicate/clock policies, recovery and safe closure; returns `PaperSession` on entry. Context entry is the first point provider I/O may occur. Do not introduce `await .paper()`, `.paper().start()` or a second paper namespace.
- Missing/contradictory historical/live data sources are rejected; no inferring execution mode from input type, no silent download or wrong-mode fallback. See [simulation contract](E6_7_SIMULATION_CONTRACT.md) for exact invariants and typed planning.

`data_provider` always names a **market-data** adapter, not the brokerage execution API. `Engine(data_provider=...)` may optionally inject a source, but data fetching is explicit, rights/credentials are validated only at the declared I/O boundary, and an injected provider **never grants real order authority**. `engine.data.load/fetch/resample/inspect` remains a data service, not a fifth execution mode.

## 4. Advanced typed specs and full feature parity

The public four-operation UX must not block supported advanced E5/E6 features. `HistoricalSimulationSpec` (planned) and `ResearchSpec` compile into immutable, versioned, audited prepared specs and use:

```python
from invest_engine import HistoricalSimulationSpec, risk, execution

spec = HistoricalSimulationSpec(
    data=validated_dataset,
    strategy=strategies.orb(),
    capital="100000 USD",
    risk=risk.Policy(max_position="5%", max_daily_loss="2%"),
    execution=execution.Simulation(commission_bps=10, spread_bps=5),
)
prepared = engine.prepare(spec)
result = engine.run(prepared)
```

This is a **non-primary advanced operation path**, not a second mode/execution engine. `simulation(...).historical()` and `prepare/run` must produce identical canonical decisions, fills, synthetic ledger, fees, metrics/evidence for the same policy/spec/data/seed; CLI decodes the same normalized spec. E6.7a must inventory actual support and settle exact typed class/default names, not pretend this example works now.

- `strategies.orb(...)` and (only once supported) `strategies.ensemble(...)` are lowercase factories returning instances. Custom Strategy/PortfolioStrategy plugins use read-only contexts and canonical signals; risk/allocator alone may authorize synthetic orders.
- `risk.Policy(...)` and `execution.Simulation(...)` are consistent policy namespaces, advanced fill/fee/corporate action/PIT/FX/calendar/reporting adapters remain typed. No unrestricted settings dict or risk bypass.
- Versioned, explicit `profiles.research_v1()`; no hidden optimization, hard-coded fees assumed to be real, silent currency conversion or unlicensed data export.
- `research(...)` and `ResearchSpec` use the same E6 pipeline/journal, registered candidates/budgets, purge/embargo, holdout controls and report evidence; a simulated gain never automatically promotes a strategy.
- Features supported by the current core must map losslessly through the new facade or documented low-level access; missing combinations fail with typed reason codes, not fabricated results. In particular multi-symbol shared-account historical execution is not guaranteed merely because #66 proposes portfolio-decision contracts.

## 5. Result vocabulary and errors

Finite `SimulationResult` and `ResearchResult` expose stable `status`, `summary`, optional `metrics`, `evidence`, `config`, `blockers`, `export(path)`; run-specific `fills`, `equity`, `portfolio`, `review`, `best_candidate` stay typed specializations. `DecisionResult` / streaming outcomes expose `status`, `reason_codes`, `blockers`, source/snapshot identity, `proposed_orders` with `submitted=False`; they **do not invent investment returns** or simulate positions. Distinguish valid no-trade, warming/incomplete context, blocked, halt and failed from success. Configuration errors raise typed exceptions; partially executed studies retain explicitly attributable evidence. Export only licensed and redacted artifacts, never credentials or a full broker account dump.

## 6. External execution boundary (not a fifth SDK mode)

Historical/Paper simulation is **not** real execution. The SDK neither hosts nor selects a broker, manages real-money order tokens, submits/cancels orders nor authoritatively stores live holdings. There is **no** `engine.live.start()`, `simulation(...).live()` or `engine.orders.submit()` API. A separate application/execution host may consume versioned `Decision/OrderIntent` values and independently enforce human authorization, pre-trade risk, idempotency, durable outbox, broker-specific rules, order lifecycle/reconciliation and kill switch. Brokerage API imports, credentials and transport belong to optional separately packaged broker adapters; the core only defines normalized types and read-only snapshot contracts. `BrokerProtocol` in existing lower-level design is an integration boundary, not permission to expose a Live SDK. See [ARCHITECTURE](ARCHITECTURE.md) and [INTEGRATIONS](INTEGRATIONS.md).

**E8 roadmap scope:** *optional external execution integration/verification* after separate approval, not an Invest Engine Live capability. The package can remain useful even when no execution host exists. No actual orders permitted by this design revision.

## 7. Roadmap / acceptance

1. **E6.7a:** document actual public/low-level API and capability inventory, signatures/overloads, invalid combinations, migration, source ownership, typed result contract, 23-example fixture matrix, golden parity and reference SDK documentation.
2. **E6.7b:** inert Engine facade, shared immutable spec/profiles, validated `simulation(...).historical()` and typed results, no core rewrite or networking.
3. **E6.7c:** all implemented supported strategy, provider, data, risk, fill/fees, calendar, corporate action, FX and advanced custom protocols; retain direct core/CLI compatibility.
4. **E6.7d:** `research(...)`, `ResearchSpec`, CLI parity, journal/evidence/review/report artifacts, batch audit.
5. **E6.7e:** wheel/import/type smoke on 3.12/3.13, API snapshots, economic golden tests, security/failure/blocked, deterministic replay, DX cookbook and measured overhead.
6. **E7:** separately gated `session()` and `simulation(...).paper()` streaming, fault/recovery and forward Paper/Shadow evidence, **zero broker orders**.
7. **E8:** only if separately decided: external execution integration validation in a separate application/adapter project, never an engine Live SDK method.

Completion of an SDK phase does **not** establish strategy profitability, broker/data licensing, PIT completeness, E5/G1 or E6/G2 acceptance, or permission to trade real money.

## 8. Change control

Earlier `engine.backtest()`, `engine.paper.start()` and `engine.live.start()` examples are **historical unimplemented design proposals** superseded by this 2026-11-22 decision. [Migration matrix](E6_7_API_CONTRACT_MATRIX.md) and [ADR amendment](adr/0034-unified-sdk.md) preserve the trail. Do not delete actually implemented `HistoricalBacktest`, CLI commands or existing low-level imports. Future public API/authority changes require user approval and synchronized issue, ADR, examples, roadmap, status and contract tests before implementation.
