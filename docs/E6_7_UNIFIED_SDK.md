# E6.7 — Unified Engine SDK (public API revision)

**Status: DESIGN ONLY, NOT EXECUTABLE.** 2026-11-22 user-approved DX revision of the prior proposal. Tracking [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59), [ADR-0034](adr/0034-unified-sdk.md), [23 normative examples](E6_7_SDK_EXAMPLES.md), [contract matrix](E6_7_API_CONTRACT_MATRIX.md) and [streaming contract](E6_7_STREAMING_CONTRACT.md). Existing E5/E6 validations and E7/E8 authorizations remain separate.

## 1. Goal and design principles

Create a predictable small public API over **one** existing deterministic core. Simple syntax must not restrict supported advanced policies, evidence, strategy/data contracts or multi-symbol evolution. No duplicate simulation ledger or real account state. The SDK facade does not become a new trading engine, and none of its methods silently unlock Live, call network on construction, tune a strategy or reach an independent holdout.

1. **Nouns for modules, verbs for operations.** `engine.data.load/fetch/resample/inspect`; `strategies.orb()`, `risk.Policy()`, `execution.Simulation()`.
2. **Direct calls for bounded work.** `engine.backtest(...)`, `engine.research(...)`, `engine.evaluate(...)` → typed result. Synchronous initially for local finite runs; no magic background jobs.
3. **Session for continuous external ingestion.** `async with engine.session(...) as session:` (decision-only, caller-fed E7). No callable-service-with-.session indirection.
4. **Explicit managed lifecycle for simulated/authorized execution.** `async with engine.paper.start(...) as session:` (E7, zero broker orders). Only E8 may offer `engine.live.start(...)` after separate GO; do not expose a callable live order path before then.
5. **Advanced parity through one spec.** Direct backtest/research → versioned immutable `BacktestSpec`/`ResearchSpec` → `engine.prepare(spec)` → `engine.run(prepared)`; CLI translates into the same spec. No feature reductions, silent provider fallback or risk bypass.

## 2. Public API reference (proposed)

| Public name | Responsibility | Shape | Boundary |
|---|---|---|---|
| `Engine()` | mode-neutral inert facade | constructor | E6.7b |
| `Engine(profile=..., data_provider=..., calendar=..., artifact_store=...)` | typed dependencies, versioned defaults | constructor | E6.7b/c |
| `engine.backtest(data, strategy, capital, ...)` | finite historical simulation | direct sync call → `BacktestResult` | E6.7b |
| `engine.research(data, strategy, capital, search, validation, ...)` | bounded registered study | direct sync call → `ResearchResult` | E6.7d |
| `engine.evaluate(market_data, portfolio, strategy)` | single verified observation + proposal, never submit | direct call → `DecisionResult` | signature E6.7a; future availability |
| `engine.prepare(BacktestSpec/ResearchSpec)` / `engine.run(prepared)` | exact offline advanced path | staged sync operations | E6.7b/d |
| `engine.data.load/fetch/resample/inspect` | explicit data operations | service methods | E6.7c, adapter-dependent |
| `engine.session(symbols, strategy, ...)` | caller-fed continuous decision-only observation | **async context manager factory** | E7 |
| `engine.paper.start(data_provider, strategy, capital, ...)` | provider-managed simulated trading | **async context manager factory** | E7 |
| `engine.live.start(...)` | separately authorized real broker runtime | not shipped before E8 | E8 |
| `indicators.*`, `strategies.*`, `risk.*`, `execution.*` | standalone utilities, typed factories/policies | modules | E6.7c |

`data` always means supplied dataset/input; `data_provider` always means the injected source/adapter. `engine.data` is a bound data service, not `Engine(data=...)`. Market-data provider credentials never imply actual trading capability. `strategies.orb()` yields a configured instance everywhere, including research. Avoid class-object `strategies.ORB` in the ordinary factory path. Advanced custom Strategy/PortfolioStrategy protocols remain independent of factories.

## 3. Basic workflow

```python
from invest_engine import Engine, strategies

engine = Engine()
result = engine.backtest(
    data="datasets/us-2022/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
)
print(result.status, result.summary)
result.export("artifacts/orb")
```

No implicit download from a ticker string; manifest binds calendar, identity, provenance/rights/PIT, warmup, hashes and source pricing basis. Unknown inputs fail/are blocked. Profiles expand to immutable, auditable cost/risk/fill policies; original Decimal currencies remain authoritative.

For staged advanced execution:

```python
from invest_engine import BacktestSpec, risk, execution

spec = BacktestSpec(
    data="datasets/us-2022/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
    risk=risk.Policy(max_position="5%", max_daily_loss="2%"),
    execution=execution.Simulation(commission_bps=10, spread_bps=5),
)
prepared = engine.prepare(spec)
if prepared.blockers:
    print(prepared.blockers)
else:
    result = engine.run(prepared)
```

The convenience call and staged path compile to **the same normalized spec** and existing orchestration; no alternate simplified core. Unsupported combinations have stable typed errors, not a silent downgrade. `prepare` does not place orders or execute strategies; `run` revalidates tampering/capability and respects journal/holdout gates.

## 4. Settings and namespaces

- `Engine(profile=profiles.research_v1(), data_provider=..., calendar=..., artifact_store=...)` is explicit typed dependency/configuration setup, inert until operations.
- Operation-level `data=dataset`, `strategy=instance`, `capital="100000 USD"` and optional `risk=risk.Policy(...)`, `execution=execution.Simulation(...)` are stable spelling across simple/advanced forms where applicable.
- Named strategy factories follow lowercase `strategies.orb()`, `strategies.ensemble()` (future if multi-symbol allocation parity). Higher-level `Strategy.setup/on_bar` adapts to existing read-only `on_event` contract, not a replacement.
- Use `execution.Simulation(fill=..., fees=...)` for advanced injection, rather than conflicting `policies.execution`/other constructors. Full feature and supported-combination inventory at E6.7a is mandatory.
- `ResearchSpec`, `research.Grid` and `research.WalkForward` share the research path; registration/lineage/purge/embargo/experiments/journal and resource budgets preserved, no unverified best candidate.
- Multi-symbol/portfolio features are mapped to actually implemented contracts (e.g. #66 foundation) only; unsupported shared-account backtesting or order handling is never presented as available.

## 5. Result and error contract

| Element | Finite BacktestResult / ResearchResult | DecisionResult / session outcome |
|---|---|---|
| `status` | enum: success / no-trade / blocked / failed | decision, warming, no-action, blocked / halted |
| `evidence`, `blockers`, `reason_codes` | typed evidence and stable reasons | typed source/portfolio/proposal evidence and reasons |
| `config` | normalized effective profile/spec, secrets redacted | validated non-secret decision context/identity |
| `summary` | typed summary, distinct per operation | optional compact decision summary; **not** a fabricated PnL |
| `metrics` | typed metrics or `None` if unavailable | `None` absent a meaningful evaluation metric |
| `export(path)` | explicit rights-aware canonical artifacts | explicit future audit mechanism only; no uncontrolled account/raw export |
| specialized data | `decisions`, `fills`, `equity`, research `review`/`best_candidate` | `proposed_orders`, `action`, `submitted=False`, `expiry` |

Do not force nonsensical fields to pretend all results are identical. Common names and state semantics apply where valid; run-specific details remain typed substructures. A rejected/blocked run has no fabricated zero-PnL success. Large result artifacts are iterated or streamed, not implicitly loaded into memory.

## 6. Streaming / authority

[Streaming contract](E6_7_STREAMING_CONTRACT.md) defines normalized single-writer EventEnvelope ingestion, UTC event/available/received timestamps, no ahead-of-time visibility, bounded queues/backpressure, explicit validated warmup, finalized bars, snapshot freshness, duplicate/conflict/gap rejection, journal cursor/restore and safe shutdown.

- `engine.session(...)`: application owns transport, supplies events and broker-authoritative snapshots. It returns **proposals only**, never broker orders. No second live portfolio DB.
- `engine.paper.start(...)`: SDK manages permitted streaming source only while inside async context, with **simulated** cash, modeled fills and shared mandatory Risk; actual broker orders = zero.
- `engine.live.start(...)`: spelling reserved for possible E8, but **no callable Live order route** before independent adapter, authorization, reconciliation, kill switch and GO.
- Async context-manager **factory** is the canonical lifecycle; `async with engine.paper.start(...)` is valid future syntax, not `await engine.paper.start(...)` before entering and not `paper.run()`.
- Streaming observations with identical normalized events and visibility should reach the same causal strategy/risk decisions as replay; Paper vs broker fills are not asserted equal unless policy/tape truly equal.

## 7. Phases and completion criteria

1. E6.7a: current API inventory and actual-supported matrix, public signatures, capability/fixture map, independent code/DX review. Verify every revised normative example is either executable for its phase or marked future. No core rewrite/permission gate change.
2. E6.7b: neutral facade + immutable specs/profiles + local manifest single backtest + typed result/prepare/run, keep existing CLI.
3. E6.7c: supported strategy/data/fee/risk/fill/calendar/FX/reporting extensions and all existing capabilities without loss; explicit failures for unsupported combos.
4. E6.7d: direct-call research + registered experiments/validation/journal/results, shared versioned Python/CLI config and migration.
5. E6.7e: wheel/import smoke, signature/API snapshots, golden parity, deterministic replay, security/failure/docs checks and measured facade overhead.
6. E7: independent streaming design acceptance and Forward Paper prerequisites; E8 separate Live approval.

**DoD:** quickstart <=10 logical lines after dataset preparation; all supported E5/E6 options mapped, specialized results auditable; same normalized tape/spec/policy yields equivalent economic outcomes where supported; root import/Engine() never I/O; public names, lifecycle and failure semantics contract-tested; no Live route, synthetic-to-real balance promotion, risk bypass or false evidence. E5/G1 and E6/G2 release acceptance remain open independently.

## 8. Change control

ADR-0034 records the 2026-11-22 **approved design revision** from the 2026-11-20 *unimplemented* spellings, with [old→new migration](E6_7_API_CONTRACT_MATRIX.md). Do not silently preserve both future names or create duplicate facades. Preserve actually implemented legacy Python/CLI routes unless a documented migration passes compatibility and parity tests. Future public API/default/authority changes require explicit user review and aligned Issue #59, ADR, examples, matrix, status/roadmap and contract snapshots. None of the examples proves profitability, data rights, Paper readiness or Live authority.
