# E6.7 — Unified Engine SDK (proposed)

Status: PLANNED, not implemented. Tracking: [#59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59). Design reviewed during #57 research; implementation follows existing validation work and must not imply E5/E6 acceptance.

## 1. Problem and goals

The root `invest_engine` currently exports only version information; Strategy SDK, core runtime, E5 `HistoricalBacktest` and `run_experiment`, E6 `PipelineSpec` / prepare/run/review, dataset ingestion and CLI are separate entry points. The caller must manually compose internal dependencies, even for standard research. Keep deterministic core and safety rules; improve discoverability, setup, typed composition, configuration and evidence handling. Simple default usage must not reduce supported functionality.

## 2. Public surface (illustrative, not executable yet)

```python
from invest_engine import Engine, Money, profiles, strategies

engine = Engine.research(profile=profiles.research_v1())
data = engine.data.load("datasets/us-2022/manifest.json")
result = engine.backtest(
    data=data, strategy=strategies.orb(opening_range="30m"),
    capital=Money("100000", "USD"),
)
print(result.summary)
result.export("artifacts/orb")
```

Money string convenience is a proposed boundary parser, not a change to current Decimal core types. Manifest contains exact data scope, identity, calendar, price basis, license/provenance status, hashes and availability. No implicit data download or fabricated calendar. Profile name/version and all expanded costs/risk/fill defaults are visible and hashed. This is offline only. Missing provenance remains provisional or blocked per the existing gate, never silently marked verified.

Advanced use of the same engine:

```python
from invest_engine import Engine, BacktestSpec, profiles
from invest_engine.sdk import data, policies, strategies

engine = Engine.research(profile=profiles.research_v1())
spec = BacktestSpec(
    data=data.from_manifest("datasets/us-2022/manifest.json"),
    strategy=MyStrategy(),  # implements the existing Strategy protocol
    capital=opening_cash,  # typed, currency-separated Money
    calendar=exchange_calendar,
    risk=custom_risk,
    execution=policies.execution(fill=fill_policy, fees=fee_policy),
    evaluation=window,
    reporting=reporting_policy,
)
prepared = engine.prepare(spec)
print(prepared.effective_config)
result = engine.run(prepared)
```

All identifiers above are design proposals. Existing public/internal contracts remain available; SDK classes and function names to be finalized in E6.7a. Mutually exclusive options rejected explicitly; custom components are trusted Python code subject to existing capability boundaries, not sandboxed. Do not introduce a universal options dictionary, a magical fluent DSL, hidden global configuration or a second trading engine.

## 3. API architecture

- Root export: Engine, stable input/result/spec types, errors, profiles, deliberate namespace aliases. Minimal root API; structured namespaces for data, strategies, policies, research, reports and future paper.
- Simple path -> typed spec -> prepare -> validated, immutable normalized configuration + capability checks -> existing orchestration/core -> typed result, report, evidence. Advanced path constructs the exact same spec. CLI decodes the same canonical versioned spec, not a separate engine.
- `Engine.research(...)` explicit offline context; no default broker, network call, live credentials, connection or automatic run on import/creation. Explicit provider configuration with secrets resolved only at I/O boundary; no secrets in repr, evidence or config hash.
- Versioned named profiles are immutable, documented and expanded before execution. Overrides are typed, explicit, deterministic, and validated; no relaxed gates. Same effective inputs -> same economic results, reproducibility hashes where same contract/version.
- Python SDK is synchronous for offline operations initially. Future async data/paper adapter can implement async lifecycle via separate mode-specific interface, not hide event-loop/network side effects. Live not available or enabled by SDK.
- Result exposes summary, evidence status/blockers, decisions, fills, equity, holdings (simulated only), per-currency PnL, artifact handles, explain/inspect. Large tapes/outputs stream or use iterators/storage rather than loading all into memory arbitrarily. No uncontrolled raw data export.
- Error taxonomy preserves engine reason codes: configuration error, missing capability, data-quality/PIT, blocked/unsupported mode, safety rejection, execution failure. Distinguish successful no-trade from blocked/failed; no implicit retry/downgrade on policy failures.
- Extension paths: existing Strategy, calendar/data/typed event provider, fee/fill policies, corporate-action evidence, reporting/artifact stores, research timing/grid/journal. Maintain dependency direction SDK -> core; core cannot import SDK/adapters. Extensions may not bypass Risk or manipulate authoritative account state.
- Portfolio boundary: Backtest/Paper use isolated simulated cash/ledger. Future real-account assets originate from verified broker snapshots; attach/reference them to engine decisions with timestamp, source and freshness rather than duplicating a live authoritative asset database. SDK must not silently make a simulated ledger authoritative for actual holdings.

## 4. Capability parity matrix to implement and test

| Capability | Common facade | Advanced typed access | Gate |
|---|---|---|---|
| Market data | local manifest/normalized data | event streams, provider adapter, schemas, calendar, resample | provenance and native resolution preserved |
| Strategies | presets + custom Strategy | requirements, features, signal, multi-strategy supported paths | no direct order privileges |
| Backtest | prepare/run/inspect/export | full settings, interval, evaluation, FX, corporate evidence, costs, risk, protection | preserve unsupported-combination restrictions |
| Risk/execution | explicit profile | RiskLimits, monetary rules, fill & dated fees | no risk bypass, actual broker unavailable |
| Portfolio | isolated opening cash and output report | multi-currency, simulated ledger snapshots, reconciliation | no invented FX or live asset ownership |
| Research | fixed run or study | walk-forward, grid, journal, regime/exposure, review/lock | registered candidates, immutable evidence, holdout authorization |
| Reports | compact result.summary/export | canonical artifacts, reason codes, full decisions/fills/equity | audit and raw-data rights maintained |
| CLI | existing commands and unified planned run/inspect | versioned typed config + compatibility | strict decode; no ambiguous live mode |

Inventory all implemented APIs at E6.7a, including non-default paths; mark supported/unsupported, map to existing classes or explicit low-level entry points. Parity applies to implemented capabilities, not a promise to enable every combination or future feature.

## 5. Phased implementation

1. E6.7a — API inventory, usage pain points, namespace, signatures, compatibility and capability matrix; finalize ADR and golden examples; no core rewrite.
2. E6.7b — Facade + immutable specs, versioned profiles, local data and single backtest path, normalized plan/inspect, typed reports, preserve existing CLI.
3. E6.7c — Advanced options + custom protocols, all supported E5 configurations (FX, splits/dividend/delisting where already supported, fee models, risk, fill, evaluation); explicit unsupported matrix; avoid duplicated models.
4. E6.7d — E6 research orchestration, journal/review/reporting, artifact lifecycle, unified CLI + Python API parity; existing e5-research-v1 decode preserved, migration tests and examples. No holdout or deployment gate bypass.
5. E6.7e — SDK public-contract snapshot, typed API, wheel/import smoke, DX cookbook and parity/failure tests; offline release candidate. E7 adds opt-in paper adapter after prerequisites; E8 separately authorized only.

## 6. Acceptance criteria

- Common offline use <=10 logical lines from root import (not counting user-provided dataset preparation); advanced custom strategy and policy examples do not require copying internal orchestration.
- Complete capability inventory; every supported existing option either maps losslessly to typed config/advanced access or is explicitly documented as existing low-level path. Unsupported combinations fail before replay.
- Golden parity with direct E5/E6 paths and existing CLI on canonical fixtures including complete minute data, multiple intervals, multi-currency/reporting, corporate-action constraints, failure/blocked states and repeated replay. Compare economic fields, decisions, fills, ledger, artifact hashes when equal contract; explain any schema-version differences.
- All prior regression fixtures unchanged except intentional versioned interfaces; backward-compatible import/CLI paths, deprecation policy and migrations. Fresh installation, public export/import smoke, mypy and CI pass.
- No network/credential use by import or offline facade, no secret logging, no live order route, no simulated-to-real promotion, no false provenance. No fake result when data unavailable. Profile defaults visible in manifest, no hidden state. Performance benchmark against direct engine with overhead budget measured and agreed in E6.7a.
- README quickstart and advanced cookbook; STATUS/ROADMAP/Issue/ADR updated with actual tests. SDK completion does not mark E5/G1/E6/G2 accepted or authorize E7/E8.

## 7. Non-goals

New profitability algorithm, independent evidence certification, broker execution, live order workflow, rewriting reducer, web UI/SaaS, new data subscription, adding unsupported instrument types or claiming unsupported combinations. Implement separately when authorized.
