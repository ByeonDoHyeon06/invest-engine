# E6.7 — Unified Engine SDK (four-operation public design)

**Status: PLANNED, NOT EXECUTABLE.** User-approved public-design consolidation and advanced-DX revision, 2026-11-22. This replaces earlier **unimplemented** proposals to expose `engine.backtest()`, `engine.paper.start()`, or `engine.live.start()`. Tracking [#59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59), [ADR-0034](adr/0034-unified-sdk.md), [23 examples](E6_7_SDK_EXAMPLES.md), [old→new matrix](E6_7_API_CONTRACT_MATRIX.md), [public DX grammar](E6_7_PUBLIC_DX_GRAMMAR.md), [simulation contract](E6_7_SIMULATION_CONTRACT.md) and [streaming contract](E6_7_STREAMING_CONTRACT.md). No E5/E6 gates, Paper deployment or broker-order authority granted by this design.

## 1. One public grammar across basic and advanced use

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

## 2. Canonical everyday examples

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

## 3. One set of settings, additive complexity

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

## 4. Independent modules and evidence safeguards

`sources` describes where data comes from; independent `data.load/resample/inspect` helpers explicitly process it, while `sources.dataset(validated_dataset)` wraps already loaded normalized data. Do not create a second mandatory `engine.data` execution workflow or allow an injected Engine-global provider to silently override an operation's source. Provider adapters can advertise multiple capabilities but are never assumed licensed or supported without evidence.

`strategies.orb()` and custom Strategy objects share `strategy=`. For **actually supported** multiple strategies use the same root `strategy=[...]` with operation-level `allocation=...` rather than a mandatory nested `strategies.ensemble(...)` run grammar. No promise of shared-account simulation from PR #66 alone. Preserve trusted plugin versioning, read-only causal context, PIT, corporate actions, FX segregation, fees, date windows and holdout restrictions.

See [public grammar](E6_7_PUBLIC_DX_GRAMMAR.md) and [simulation contract](E6_7_SIMULATION_CONTRACT.md) for exact source capability and lifecycle requirements; [streaming contract](E6_7_STREAMING_CONTRACT.md) for managed/manual Session and Paper.

## 5. Result vocabulary and errors

Finite `SimulationResult` and `ResearchResult` expose stable `status`, `summary`, optional `metrics`, `evidence`, `config`, `blockers`, `export(path)`; run-specific `fills`, `equity`, `portfolio`, `review`, `best_candidate` stay typed specializations. `DecisionResult` / streaming outcomes expose `status`, `reason_codes`, `blockers`, source/snapshot identity, `proposed_orders` with `submitted=False`; they **do not invent investment returns** or simulate positions. Distinguish valid no-trade, warming/incomplete context, blocked, halt and failed from success. Configuration errors raise typed exceptions; partially executed studies retain explicitly attributable evidence. Export only licensed and redacted artifacts, never credentials or a full broker account dump.

## 6. External execution boundary (not a fifth SDK mode)

Historical/Paper simulation is **not** real execution. The SDK neither hosts nor selects a broker, manages real-money order tokens, submits/cancels orders nor authoritatively stores live holdings. There is **no** `engine.live.start()`, `simulation(...).live()` or `engine.orders.submit()` API. A separate application/execution host may consume versioned `Decision/OrderIntent` values and independently enforce human authorization, pre-trade risk, idempotency, durable outbox, broker-specific rules, order lifecycle/reconciliation and kill switch. Brokerage API imports, credentials and transport belong to optional separately packaged broker adapters; the core only defines normalized types and read-only snapshot contracts. `BrokerProtocol` in existing lower-level design is an integration boundary, not permission to expose a Live SDK. See [ARCHITECTURE](ARCHITECTURE.md) and [INTEGRATIONS](INTEGRATIONS.md).

**E8 roadmap scope:** *optional external execution integration/verification* after separate approval, not an Invest Engine Live capability. The package can remain useful even when no execution host exists. No actual orders permitted by this design revision.

## 7. Roadmap / acceptance

1. **E6.7a:** inventory actual public/low-level API and capabilities; define typed `Source` descriptors, managed/manual source ownership, consistent policy names, signatures/overloads, optional `inspect()` preflight, invalid combinations, migration, 23-example phase fixtures, golden parity and reference docs.
2. **E6.7b:** inert Engine facade, shared immutable spec/profiles, validated `simulation(...).historical()` and typed results, no core rewrite or networking.
3. **E6.7c:** all implemented supported strategy, provider, data, risk, fill/fees, calendar, corporate action, FX and advanced custom protocols; retain direct core/CLI compatibility.
4. **E6.7d:** `research(...)` with common `source/strategy/capital/risk/execution` options, internal registered specs and CLI parity, journal/evidence/review/report artifacts, batch audit.
5. **E6.7e:** wheel/import/type smoke on 3.12/3.13, API snapshots, economic golden tests, security/failure/blocked, deterministic replay, DX cookbook and measured overhead.
6. **E7:** separately gated `session()` and `simulation(...).paper()` streaming, fault/recovery and forward Paper/Shadow evidence, **zero broker orders**.
7. **E8:** only if separately decided: external execution integration validation in a separate application/adapter project, never an engine Live SDK method.

Completion of an SDK phase does **not** establish strategy profitability, broker/data licensing, PIT completeness, E5/G1 or E6/G2 acceptance, or permission to trade real money.

## 8. Change control

Earlier `engine.backtest()`, `engine.paper.start()`, `engine.live.start()` and `Engine(data_provider=...)` examples are **historical unimplemented design proposals** superseded by this 2026-11-22 decision. [Migration matrix](E6_7_API_CONTRACT_MATRIX.md) and [ADR amendment](adr/0034-unified-sdk.md) preserve the trail. Do not delete actually implemented `HistoricalBacktest`, CLI commands or existing low-level imports. Future public API/authority changes require user approval and synchronized issue, ADR, examples, roadmap, status and contract tests before implementation.
