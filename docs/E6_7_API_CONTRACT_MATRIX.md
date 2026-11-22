# E6.7 — SDK consistency, capability and migration matrix

**Status: current DX design direction, not yet executable (2026-11-22).** [Spec](E6_7_UNIFIED_SDK.md) · [DX grammar](E6_7_PUBLIC_DX_GRAMMAR.md) · [23 examples](E6_7_SDK_EXAMPLES.md) · [expected output contracts](E6_7_SDK_OUTPUT_CONTRACTS.md) · [Simulation contract](E6_7_SIMULATION_CONTRACT.md) · [Streaming](E6_7_STREAMING_CONTRACT.md) · [ADR-0034](adr/0034-unified-sdk.md).

## 1. Four roots, consistent parameters

| Public operation | Source | Common options | Additional / specialized options | Effect |
|---|---|---|---|---|
| `simulation(...).historical()` | finite `sources.local/dataset` | strategy, synthetic capital, risk, execution | supported calendar/reporting/allocation | historical virtual fills |
| `simulation(...).paper()` | `sources.alpaca` or `sources.manual` | **same** strategy, synthetic capital, risk, execution | supported streaming subscriptions | E7 virtual fills |
| `research(...)` | finite historical source | **same** strategy/capital/risk/execution | search, validation, resource budgets | E6 registered historical study |
| `evaluate(...)` | concrete `market_data=` snapshot, not a stream source | strategy, risk where supported | verified `portfolio=` | one-off proposal only |
| `session(...)` | **same** streaming/manual `source` as Paper | strategy, risk where supported | symbols, verified account refresh | E7 continuing proposals only |

`Engine()` is inert. `sources.*` are inert typed descriptors; `simulation(...)` is inert configuration. Managed provider network data starts only in an explicit permitted operation/context; Session and Paper use **the same input-source contract**. No engine-owned actual broker-order transport.

## 2. Previous proposed naming → current target

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

## 3. Source capability matrix

| Source | Historical | Paper | Research | Decision Session |
|---|---|---|---|---|
| `sources.local(manifest)` | yes if validated | no implicit live replay | yes if licensed/eligible | no implicit streaming |
| `sources.dataset(immutable_normalized_dataset)` | yes if validated | no implicit live replay | yes if eligible | no implicit streaming |
| `sources.alpaca(market_data_secret_ref)` | no implicit download; historical capability only if separately documented | E7 read-only streaming if permitted | no implicit registered historical study | E7 read-only streaming if permitted |
| `sources.manual()` | no finite dataset inferred | E7 via `paper.ingest(event)` | no historical inference | E7 via `session.ingest(event)` |

A future provider may explicitly implement both historical and streaming capabilities; typed validation and rights/coverage determine permitted use, never the provider brand alone. Historical/Paper/Session do **not** select mode by guessing source type. Conflicting/missing sources, stale evidence, unlicensed feed, gaps, unsupported event/strategy and insufficient warmup reject or halt with typed reasons.

## 4. Updated 23-example phase map

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

## 5. Golden tests and DoD

1. Python 3.12/3.13 public signature/**return-type/status snapshots for each of 23 examples**, typed source capabilities, no I/O from Engine/source/builder factories, explicit read-only local inspect behavior; managed/manual context exit tests.
2. Same default and advanced parameters in `simulation(...).historical()` compile to immutable validated specs and match existing E5 historical decisions, synthetic fills, ledger/PnL, fees, timestamp evidence and blocked statuses.
3. `research(...)` uses the same input/policies where valid and preserves E6 journal, fold, candidate, budget, purge/embargo, holdout non-access and result evidence.
4. `session(source=stream)` and `session(source=manual)` share causal strategy/risk/portfolio-contract semantics; Paper uses same source capabilities but synthetic account and no real orders. Instrument identity/late/gap/overflow/source rights fail closed.
5. Optional `simulation.inspect()` does not place simulated or actual orders, reserve unauthorized holdout, or connect remote provider. Final execution revalidates.
6. All actual supported fee/fill/FX/PIT/corporate action/multi-symbol/advanced adapters remain available under the facade or explicit versioned low-level escape hatch. Unsupported combinations reject explicitly; real broker account remains authoritative externally.
7. Name and implement deterministic output fixtures (`toy_no_trade_v1`, `toy_blocked_gap_v1`, `toy_research_rejected_v1`, `toy_snapshot_stale_v1`, `toy_manual_paper_v1`, `toy_manual_session_v1`) and lock expected status/reason/evidence/optional fields in separate executable golden tests; **do not treat proposed output panels as test evidence**.
8. Existing actual low-level Python imports and CLI commands unchanged unless an explicitly reviewed migration has parity tests. No actual Live SDK, broker secrets or execution adapter; E7/E8 independent approvals.

**No new execution code in this design PR.** E5/G1, E6/G2, provider rights, real fees and investment profitability remain separate unresolved gates.
