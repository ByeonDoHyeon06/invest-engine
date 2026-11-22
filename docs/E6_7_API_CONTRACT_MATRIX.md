# E6.7 — Public API contract and migration matrix

**Status:** approved **design only**, 2026-11-22. [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59) · [spec](E6_7_UNIFIED_SDK.md) · [23 examples](E6_7_SDK_EXAMPLES.md) · [simulation](E6_7_SIMULATION_CONTRACT.md). This migration table concerns **proposed, not-yet-shipped** E6.7 surface. Existing E0–E6 code, `HistoricalBacktest`, Python imports and CLI remain subject to strict regression/compatibility.

## 1. Four-operation grammar

| Operation | Call grammar | Output | Authority |
|---|---|---|---|
| Simulation | `engine.simulation(**config).historical()` | synchronous `SimulationResult` | historical virtual account, synthetic fills |
| Simulation | `async with engine.simulation(**config).paper() as s:` | async `PaperSession` | live data, **virtual** account/fills |
| Research | `engine.research(**study)` | synchronous `ResearchResult` | historical candidate study only |
| Evaluate | `engine.evaluate(market_data=..., portfolio=..., strategy=...)` | `DecisionResult` | caller-supplied account, proposal only |
| Session | `async with engine.session(...) as s:` | async decision session | caller market stream/account, proposal only |

`Engine()` is inert. `engine.data` is a **service** for load/fetch/inspect, not a fifth top-level *execution* operation. `prepare(spec)/run(prepared)` is the shared **advanced offline typed orchestration path**, not an alternative backtest/public trading mode.

## 2. Proposed API changes

| Former planned spelling | Current agreed design | Reason |
|---|---|---|
| `engine.backtest(...)` | `engine.simulation(...).historical()` | no duplicate backtest entry; simulation owns all synthetic execution |
| `engine.simulation(mode="historical", ...).run()` | `engine.simulation(...).historical()` | fluent, typed, discoverable terminal method |
| `engine.simulation(mode="paper", ...).start()` | `engine.simulation(...).paper()` | common configuration + explicit simulated lifecycle |
| `engine.paper.start(...)`, `engine.paper.run(...)` | `engine.simulation(...).paper()` | Paper belongs under simulation, no duplicate namespace |
| `engine.live.start(...)`, `engine.live.run(...)` | **none in Engine SDK** | broker execution outside engine; E8 optionally tests external host/adapter |
| `engine.simulation(...).live()` | **explicitly forbidden** | simulated account can never become live via option |
| `engine.research.create(...).run()` | `engine.research(...)` | finite research is a direct operation |
| `engine.evaluate.session(...)` / `evaluation_session(...)` | `engine.session(...)` | caller-fed decision-only sessions are independent |
| `engine.evaluate(...)` | unchanged | one-shot proposal; no account/order mutation |
| `Engine(data=provider)` | optional `Engine(data_provider=provider)` | distinguish provider dependency from operation input |
| `strategies.ORB` in research | `strategies.orb()` | configured instance, consistent factory |
| `strategies.Ensemble(...)` | `strategies.ensemble(...)` **if supported** | no premature shared-account claims |
| `policies.execution(...)` | `execution.Simulation(...)` | typed consistent policy namespace |
| Public `BacktestSpec` staged path | planned `HistoricalSimulationSpec` → `prepare/run` | preserve existing low-level BacktestSpec implementation until parity verified |
| `ResearchSpec` staged path | retained `ResearchSpec` → `prepare/run` | same registered research pipeline/holdout gates |
| `engine.session(...)` | unchanged | separate decision-only path |
| `Engine.offline()/online()` | still rejected | neutral constructor, no implicit mode or broker |
| `result.*` inconsistent | shared finite fields + typed specialization | no fabricated metrics/account holdings |

**Important:** rename decisions concern the **new future SDK only**. Never remove a working `HistoricalBacktest`, `run_experiment`, old import or existing CLI `backtest` command without explicitly reviewed compatibility and golden tests.

## 3. Invariants and configuration matrix

| Builder input | Terminal | Support policy |
|---|---|---|
| `data=validated_historical_manifest`, no streaming provider | `.historical()` | allowed when complete, rights and capabilities pass |
| `data_provider=authorized_market_stream`, no historical dataset | `.paper()` | **E7 only**, with explicit warmup, controlled I/O and simulated capital |
| historical `data` with `.paper()` | mismatch | typed rejection (no implicit realtime replay) |
| streaming `data_provider` with `.historical()` | mismatch | typed rejection (no automatic provider download) |
| both/no source, unsupported price/clock policy | either | typed invalid/unsupported; no guessed mode |
| any `broker`, real `authorization`, `mode="live"` or `.live()` | either | no SDK support / no real trade submission |
| `engine.session(...)` + supplied market and authoritative account | proposal only | no synthetic ledger/fills |
| `engine.research(...)` | historical registered study | cannot bypass journal, holdout, resource or provenance gates |

E6.7a must settle exact typing/defaults, including how explicitly supplied *prepared* data and an injected data-service dependency interact; must **never** accept ambiguous sources silently.

## 4. Phase/fixture matrix for 23 examples

| IDs | Area | Earliest implementation | Mandatory test/ownership |
|---|---|---|---|
| 01–03 | Engine, historical, Paper | E6.7b historical; E7 Paper | inert builder, golden backtest parity; provider-only Paper context lifecycle |
| 04–06 | research, evaluate, session | E6.7d research, E7 session, evaluate separately gated | registered folds/holdout; snapshots; no broker route |
| 07–10 | policies, providers/data, indicators | E6.7c; provider rights vary | Decimal/PIT/quality, validated sources, no silent fetch |
| 11–12 | custom/multi-symbol strategy | E6.7c and future allocation | read-only signal and single-account risk; unsupported explicit |
| 13–16 | typed specs/advanced/FX/extension | E6.7b/c/d | direct historical vs prepare/run vs current core/CLI golden |
| 17–18 | results/errors | E6.7b/d | blocked vs no-trade, no fabricated PnL, safe export |
| 19 | shared CLI | E6.7d | existing CLI flag compatibility and same spec decode |
| 20 | host integration | external app | no broker import/order in engine; standalone host policy |
| 21–22 | streaming/Paper lifecycle and parity | E7 | warmup/finalization/gap/cancel/recovery/zero actual orders |
| 23 | external broker boundary | optional E8 external integration | independent rights, idempotency/reconciliation/kill switch; **no engine.live** |

## 5. Acceptance/compatibility tests

- Public import, typed signature and return snapshots on Python 3.12/3.13; `Engine()`, `simulation(...)`, `.paper()` factory, `ResearchSpec` construction are all inert.
- `.historical()` and `engine.prepare(HistoricalSimulationSpec)/run` match existing E5 `HistoricalBacktest` on same canonical event tape, risk/fill/fee/FX/calendar/corporate/PIT policy: decisions, fills, synthetic cash, PnL, exposure, errors and permitted evidence hashes.
- Research direct call vs `ResearchSpec/prepare/run` retains search boundaries, validation embargo, journal reservations, candidates and blocked statuses.
- Historical vs recorded Paper event/sim execution parity only when *canonical event visibility and execution policy* are equal, never invent equivalent real broker fills.
- Source/type mismatch, incomplete warmup, duplicate/late/gapped ticks, unsupported calendars/multi-symbol/FX, wrong account and stale snapshot fail closed, with stable reason codes.
- No core/SDK dependency on Toss/Alpaca *trading* API or real account credential; no `engine.live` public method; external executor is separately built/tested.
- Preserve old Python/CLI public APIs; versioned migration plan for truly breaking existing calls (not merely replacing drawings in prior docs). E5/G1, E6/G2, E7 and E8 approval do not follow from passing SDK tests.

## 6. Documentation scope

This is a user-reviewed **design change** to prior not-yet-shipped API proposals, not a claim of implementation. E6.7a verifies actual capabilities and may identify problems requiring another ADR/user decision; do not silently change named contracts. Current planned Paper/decision continuous interfaces remain E7 only; optional E8 external host is **outside the SDK**.
