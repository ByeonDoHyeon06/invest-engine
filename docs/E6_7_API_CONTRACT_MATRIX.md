# E6.7 public API consistency and migration matrix

**Status:** design target only, 2026-11-22. This records the user-approved API redesign and the precise scope that E6.7a must verify before implementation. Changes below replace **unimplemented proposed** names, not existing working E0–E6 APIs. [Examples](E6_7_SDK_EXAMPLES.md), [spec](E6_7_UNIFIED_SDK.md), [ADR-0034](adr/0034-unified-sdk.md).

## Naming grammar

| Type | One rule | Example |
|---|---|---|
| Root | mode-neutral `Engine()` | `engine = Engine()` |
| Finite operation | directly call verb, obtain result | `engine.backtest(...)`, `engine.research(...)`, `engine.evaluate(...)` |
| Staged finite operation | typed spec → `prepare` → `run` | `engine.run(engine.prepare(ResearchSpec(...)))` |
| Caller-fed continuous observation | `engine.session(...)` async context manager | `async with engine.session(...) as session:` |
| Provider-managed continuous simulation | `engine.paper.start(...)` async context manager | `async with engine.paper.start(...) as session:` |
| Future authorized continuous trading | `engine.live.start(...)` only after E8 | no live method exposed now |
| Operation input | `data=...` means dataset | `engine.backtest(data=dataset, ...)` |
| Dependency | `data_provider=...` means injected source | `Engine(data_provider=provider)` |
| Bound data operations | `engine.data.<verb>()` | `engine.data.fetch/load/inspect` |
| Strategy presets | lowercase factory → instance | `strategies.orb()` |
| Policy | one namespace/type per domain | `risk.Policy(...)`; `execution.Simulation(...)` |
| Run result | status, summary, metrics?, evidence, config, blockers, export | same fields/meaning across finite runs |

## Original design → revised design

| 2026-11-20 planned spelling | Revised target | Rationale / compatibility |
|---|---|---|
| `engine.backtest(...)` | unchanged | shortest finite-run path |
| `engine.research.create(...); study.run()` | `engine.research(...)` | same direct-operation grammar; advanced `ResearchSpec + prepare/run`; no alternate research engine |
| `engine.evaluate(...)` | unchanged | one-shot decision-only; no broker side effect |
| `engine.evaluate.session(...)` | **`engine.session(...)`** | user-selected canonical clean spelling; no callable-service-with-submethod |
| `engine.paper.run(spec=...)` | **`engine.paper.start(...)`** | continuous managed lifecycle, E7 only |
| `session = await engine.paper.start(...); async with session` | **`async with engine.paper.start(...) as session`** | only one lifecycle convention; I/O on context entry |
| `engine.live.run(...)` | **`engine.live.start(...)`** (future) | same continuous lifecycle grammar; E8-only gate |
| `Engine(data=provider)` | `Engine(data_provider=provider)` | distinguish injected source vs `backtest(data=dataset)`; constructor inert |
| `strategies.ORB` in `research.create` | `strategies.orb()` | consistent lowercase instance across research and backtest |
| `strategies.Ensemble(...)` | `strategies.ensemble(...)` (future) | consistent preset factory, only if supported allocation semantics |
| `policies.execution(fill=..., fees=...)` | `execution.Simulation(fill=..., fees=...)` | single policy namespace/type |
| `from invest_engine.indicators import sma` / `from invest_engine import indicators` | `from invest_engine import indicators; indicators.sma(...)` | consistent standalone namespace; old imports not deleted if implemented |
| `result.summary/metrics/pnl/review` ad hoc | common finite result metadata; specialized typed substructures | avoid unrelated root result schemas; no fake metrics |
| `BacktestSpec` + `prepare/run` | unchanged, expanded to `ResearchSpec` | advanced capability parity through same core |
| `Engine.offline()/online()` / mandatory mode | still **rejected** | mode-neutral constructor, explicit operation rights |

The strings above are design deltas. Implementation must inventory and retain working existing imports/CLI. No automatic breaking migration, no undocumented aliases or conflicting synonyms for these **future SDK** methods.

## Phase/capability map for 23 normative examples

| IDs | Category | Design implementation phase / gate | Required E6.7a fixture |
|---|---|---|---|
| 01–03 | quickstart/finite result | E6.7b | import inertness, no network, blocked/no-trade distinction, versioned results |
| 04 | finite research | E6.7d | registered budget/folds, no holdout, parity with current pipeline |
| 05 | one-shot decision | future; signature E6.7a | same authoritative snapshot, staleness and risk rejection; no orders |
| 06–07 | data service | E6.7c, source rights dependent | missing/wrong feed, resample causality, provenance |
| 08–10 | strategy/pure indicators | E6.7c | factory naming, read-only state, deterministic features |
| 11 | ensemble/shared account | future extension, gated by actual support | correct single cash/risk if supported; otherwise explicit unsupported |
| 12 | integration app | external app, SDK E6.7d | tenant/path isolation, no implicit provider I/O |
| 13–16 | advanced spec/policies/FX/plugins | E6.7b/c/d by capability | direct-vs-prepare/run parity, Decimal/fees/FX, plugin gating |
| 17 | CLI parity | E6.7d | same config decode and economic outputs |
| 18–19 | caller-fed session | E7 only | single-writer, warmup, identity, account refresh, no submission |
| 20 | managed Paper | E7 only | read-only provider, simulated account, connect/close/cancel |
| 21 | shared strategy contract | E6.7c design / E7 playback | matched causal observations, isolated state, no tick synthesis |
| 22 | recovery | E7 only | journal/checkpoint/cursor gap & conflict handling |
| 23 | Live | E8 after separate GO | unavailable before approval; no callable live route |

## E6.7a API test requirements

- Signature snapshot for each implemented public method, module/factory namespace and result object.
- Both Python 3.12 and 3.13 import/type tests. No hidden provider I/O from import, Engine(), spec creation or context factory.
- Direct backtest and staged BacktestSpec must produce identical events/decisions/fills/ledger/economics and canonical evidence where contract hashes match; ResearchSpec must preserve journal, validation scope and budget.
- Recover old CLI and existing low-level E4/E5/E6 Python imports unchanged unless independently approved/tested.
- Unsupported modes/strategies/data/policies produce stable reason codes; invalid account state or market gaps fail closed.
- Explicit dry-run fixture for `engine.session()` factory/async lifecycle once E7 is approved; `engine.paper.start()` simulated only; Live remains unshipped.
- E6.7a records exact typed signatures/default values, capability gaps and overhead budget **before** implementing, rather than guessing from examples.

## Non-goals

No new profitability work, strategy retuning, actual broker order API, account ledger authority, production provider rights, raw market-data redistribution or E7/E8 stage acceptance. Simplicity and full function parity are separate, simultaneous acceptance goals.
