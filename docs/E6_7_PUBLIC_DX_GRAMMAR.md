# E6.7a — Public SDK grammar and advanced-capability ergonomics

**Status: user-approved DESIGN DIRECTION (2026-11-22), not an implemented API or a change to E5/E6 acceptance.** Normative for the E6.7a type/contract inventory along with [the unified SDK specification](E6_7_UNIFIED_SDK.md), [23 revised examples](E6_7_SDK_EXAMPLES.md), [API matrix](E6_7_API_CONTRACT_MATRIX.md), [ADR-0034](adr/0034-unified-sdk.md) and [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59).

## A. One mental model, four execution roots

| Operation | Required input | Optional policy surface | Result / ownership |
|---|---|---|---|
| `simulation(...).historical()` | `source=` historical, `strategy=`, `capital=` | `risk=`, `execution=`, calendar, allocation, reporting | finite synthetic fills and metrics |
| `simulation(...).paper()` | `source=` stream/manual, `strategy=`, `capital=` | **same** simulation policy names where supported | E7 async synthetic fills / simulated cash |
| `research(...)` | `source=` historical, `strategy=`, `capital=` | **same** `risk=` / `execution=`, plus `search=`, `validation=`, budgets | finite registered study and evidence |
| `evaluate(...)` | `market_data=` single snapshot, `portfolio=` verified account snapshot, `strategy=` | `risk=` where supported | one-time decision proposal, no fills |
| `session(...)` | `source=` stream/manual, `strategy=`, externally refreshed account snapshot | `risk=` where supported, declared symbols/subscriptions | E7 continuous decision proposals, no fills |

Four **roots**, five rows because Simulation has two terminal methods. `market_data=` in Evaluate is an *already supplied one-shot observation*, not another market source configuration: we deliberately do not connect streams or fetch accounts as a side effect of `evaluate()`.

A simple call and its advanced form use the **same public execution grammar**; adding risk, source, calendar, fees, FX, custom strategy or allocation must not force users into a different `Spec → prepare → run` workflow. No separate new `engine.backtest`, `engine.paper` or `engine.live` route. Existing working lower-level E4/E5/E6 Python classes, typed specs and CLI commands remain **preserved** for compatibility.

## B. One `source=` concept, typed capabilities

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

## C. Stable settings by concept

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

## D. Advanced features should add options, not execution ceremonies

**Common path:**

```python
result = engine.simulation(
    source=sources.local("datasets/AAPL/manifest.json"),
    strategy=my_strategy,
    capital="100000 USD",
    risk=risk.Limits(max_position="5%"),
    execution=execution.Model(commission_bps=10),
).historical()
```

**Optional read-only preflight (proposed):**

```python
simulation = engine.simulation(source=historical, strategy=my_strategy, capital="100000 USD")
plan = simulation.inspect()
result = simulation.historical()
```

`inspect()` is an optional, read-only validation/config explanation (allowed explicit local manifest reads; **no strategy execution, remote provider connect, live order or bypass of journal/holdout**). Inspect is never required to run, and its report cannot certify data that will only be checked at runtime. E6.7a must decide exact preflight type/signature and whether comparable diagnostics for research are justified; do not expose a second public `engine.prepare/run` ceremony solely for advanced use.

**Internal/compatibility:** a normalized immutable typed spec, simulation/research plans, canonical journal/outbox/snapshot contract, historical E5 runner and CLI still exist *under the facade* and may remain available as versioned low-level imports. Their signatures/economic outputs must be parity-tested against the fluent API. Advanced behavior cannot lose any actually supported E5/E6 capability. Future types/policies requiring a genuinely different lifecycle must be justified by an ADR rather than hidden coercion or arbitrary kwargs.

## E. Consistent results and explicit safety

Finite `SimulationResult` / `ResearchResult` share `status`, `summary`, `metrics` (possibly None), `evidence`, `config`, `blockers` and explicit `export(path)`; specialized fills/equity/research review stay in typed fields. Decision-only results contain `status`, `reason_codes`, `blockers`, authoritative input identity and `proposed_orders` with `submitted=False` — **not** invented simulated PnL. Configuration/source incompatibility gets a typed error; missing data, invalid PIT or stale snapshots block/halt instead of returning a successful zero trade.

Historical and Paper use **virtual** capital, orders and fills; Session/Evaluate only propose actions from supplied broker-authoritative snapshots. Actual broker submission, account reconciliation/outbox/credentials/kill switch belong to an independent external Execution Host/Adapter, not the Engine SDK. E8 remains optional external integration verification after independent approval.

## F. Documentation and acceptance gates

Organize examples by **use case** rather than a sudden Core/Advanced grammar switch: **Getting Started → Simulation → Research → Decision → Customization → Reference**. All 23 existing intended capabilities must remain represented with E6.7b/c/d/e vs E7 vs external E8 markers and unsupported variants clearly identified.

E6.7a acceptance tests before implementation:
1. An explicit typed `Source` protocol and capability matrix, owner/lifecycle contract, market-data license/provenance and invalid source/mode/ingress fixtures; no import/factory I/O.
2. SDK signature snapshot showing common `source/strategy/risk/capital/execution` option semantics, E7 session-managed/manual source variants, risk enforcement and finite/streaming return overloads.
3. Basic vs advanced *same fluent method* regression and economic parity against actual E5 HistoricalBacktest (decisions, fills, ledger, fees, PnL, evidence); E6 research journal, validation and holdout parity.
4. Optional `inspect()` only reads explicitly allowed local config/metadata and never starts a strategy, provider or broker; deterministic fail-closed runtime checks still apply.
5. Existing Python low-level APIs and CLI unchanged or explicitly migrated/tested; unsupported FX/corporate action/quote, multi-symbol and external plugins blocked honestly.
6. No engine Live order route, account-ledger duplication or credentials; Paper/Session cannot leak order permissions. E7/E8 remain separate approvals.

This is **only a design revision**, not a guarantee of SDK implementations or market-data availability, strategy quality, real fills, legal entitlement or live trading authorization.
