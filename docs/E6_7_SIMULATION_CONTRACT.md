# E6.7 — Unified simulation contract (historical + paper)

**Status:** user-selected **public API design**, 2026-11-22; not an implemented SDK or E7 authorization. [SDK spec](E6_7_UNIFIED_SDK.md) · [examples](E6_7_SDK_EXAMPLES.md) · [ADR-0034](adr/0034-unified-sdk.md). This document is normative for E6.7a contract inventory; actual typed signatures/defaults remain an implementation gate.

## 1. Principle: one simulation, two time/data lifecycles

```python
result = engine.simulation(
    data=historical_data, strategy=my_strategy, capital="100000 USD",
).historical()

async with engine.simulation(
    data_provider=market_provider, strategy=my_strategy, capital="100000 USD",
).paper() as session:
    async for event in session.events():
        print(event)
```

`engine.simulation(...)` **only builds an inert, typed configuration**. It never replays bars, connects a provider, starts tasks, makes a mock fill or requests credentials. The terminal methods determine execution semantics, not an inferred mode string or an actual broker capability. Both methods use the **same existing** strategy/event/risk/allocation/simulated-order/accounting primitives wherever their market-data and execution contracts permit.

| Contract | `.historical()` | `.paper()` |
|---|---|---|
| Input | fixed, validated historical manifest or canonical finite tape (`data=`) | explicitly configured authorized real-time source (`data_provider=`) |
| Clock | recorded event/availability time; deterministic virtual progression | observed real-time ingress, sourced timestamps and bounded clock policy |
| Duration | finite; synchronous method returning `SimulationResult` | continuous; async context-manager factory returning `PaperSession` |
| Portfolio | isolated simulated opening capital and ledger | isolated simulated capital, fills and ledger |
| Orders | synthetic order lifecycle and modeled fill/fees | synthetic order lifecycle and modeled fill/fees |
| Broker API / actual orders | **never** | **never** |
| Validation | PIT, calendar, corporate actions, fees, gaps, snapshot/cost parity | source rights, warmup, freshness, subscription, gaps/late data, modeled fills, recovery |
| Results | terminal status/metrics/evidence/artifact export | typed events/status during execution, auditable result after safe close |

Simulation is **not** a real trading transport. There is **no** `simulation(...).live()`, `mode="live"`, SDK `engine.live` or SDK broker-order submission method. Real-money execution is an **external application's** explicit responsibility through its own broker adapter and order service. E8, if retained, covers **external integration verification** and operational controls, not a broker-specific core/SDK implementation.

## 2. Precise lifecycle and invalid combinations

`engine.simulation(data=..., ...)` and `engine.simulation(data_provider=..., ...)` build configurations. E6.7a must decide whether both may ever be supplied; **default design rejects ambiguous, missing or contradictory sources** before execution. No auto-detect based on file/URL/schema, no implicit download, no silent history-to-live transition. `data_provider` is a market data provider, **not** an execution broker. Only `historical()` may process a finite recorded tape; `paper()` must have a supported streaming source and complete data-rights/freshness contract. Any future replay-at-wall-clock policy is a separately versioned capability, not an implicit fallback.

`historical()` validates and prepares an immutable versioned execution spec, then delegates to the exact E5/HistoricalBacktest path. A blocked run is distinct from a zero-trade success. Deterministic reruns with the same canonical tape, config, strategy snapshot, fees and seed must match decision, order, fill, cash, position and evidence data (modulo documented version/timing differences).

`paper()` returns a **non-awaitable async context-manager factory**; `async with simulation.paper() as session` performs start/warmup/connect after policy/rights validation. Context exit drains or cancels owned tasks, closes streams, preserves halt reasons and flushes permitted audit records. `PaperSession.events()` supplies typed events, and `session.status` / `session.result` (available only when terminal) expose state. No second `start()`, `run()`, `await .paper()` spelling. A fresh paper session owns isolated strategy and synthetic portfolio state; no cross-session leakage.

Both modes use explicit monetary Decimal/typed Money, declared instruments and exchange calendars, configured risk/sizing/fees, no future observations, no same-bar impossible fills, no unsupported tick-to-quote reconstruction, and immutable provenance. The optional real-time data provider **can** connect to a vendor, but only for permitted market-data consumption; **never** its trade or account mutation endpoints. No paper session becomes live by toggling a bool or attaching credentials.

## 3. Strict distinction from evaluation/session

| Engine operation | Manages simulated positions/fills? | External authoritative account? | Actual orders? |
|---|---|---|---|
| `simulation(...).historical()` | yes | no | no |
| `simulation(...).paper()` | yes | no | no |
| `research(...)` | only within registered historical simulations | no | no |
| `evaluate(...)` | no | caller-supplied, timestamped snapshot | no; proposal only |
| `session(...)` | no | caller-updated broker/account snapshots | no; proposal only |

An external application can attach to `session()` outcomes, independently authorize or reject a proposal, and own **all** broker token management, idempotent order submission, outbox, retries, reconciliation, kill switch, custody and trade permissions. No internal engine ownership of the actual account. Engine may expose stable typed `Decision/OrderIntent` *values*, but no `submit_order` side effect in the four-operation facade.

## 4. Typed plan and advanced capability parity

The convenience `simulation(...).historical()` must normalize into an **immutable, versioned historical simulation spec** supported by `engine.prepare(spec)` / `engine.run(prepared)` and existing E5 low-level `HistoricalBacktest`. In this design the public advanced type is `HistoricalSimulationSpec` (precise constructor to be confirmed at E6.7a). Preserve all implemented advanced policies (fill/fee/FX/PIT/corporate actions, calendars, multistrategy when supported, allocation, risk, evidence), and existing imports and CLI paths. There is no need for a *second* historical runner or public `engine.backtest()` alias; keeping a working lower-level `HistoricalBacktest` class is **not** the same as adding another SDK entry point.

`ResearchSpec` keeps the existing search/journal/fold/review gates. Research may schedule multiple historical simulations but does not automatically retune a deployed strategy, unlock validation holdout or skip independent market-data licensing. Unsupported combinations are explicit typed blockers with reason codes, not silent fallbacks.

## 5. Test / release map

- **E6.7a (design):** type/signature/default matrix; no import/constructor/builder/provider I/O; validate terminal-method/source mismatch; proposal-vs-simulation state separation; map to actual E4/E5/E6/Python/CLI capabilities.
- **E6.7b–e (offline):** `simulation(...).historical()` and `HistoricalSimulationSpec/prepare/run` golden parity (decisions, fills, cash/fees, PnL, journal/evidence, CLI) against existing E5, including rejection and no-trade.
- **E7 (separately gated):** `simulation(...).paper()`, `engine.session()`, canonical input/watermarks, stale/gap/duplicate, warmup/handoff, disconnect/recovery and bounded queue tests; forward shadow/Paper evidence, **zero broker orders**.
- **E8 (outside SDK):** optional external host/adapter integration validation with independent operational and legal approval, test account order/reconciliation and kill switch; no `engine.live.start()` and no change to public SDK authority.

This consolidation changes **planned public names**, not already merged E0–E6 runtime semantics or evidence. E5/G1 and E6/G2 remain open; historical research and Paper returns are not evidence of actual fills or profitability.
