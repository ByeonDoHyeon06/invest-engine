# E6.7a / E7 — Continuous decision sessions and Paper simulation

**Status: DESIGN ONLY, approved public naming on 2026-11-22.** [SDK spec](E6_7_UNIFIED_SDK.md) · [Simulation contract](E6_7_SIMULATION_CONTRACT.md) · [23 examples](E6_7_SDK_EXAMPLES.md) · [ADR-0034](adr/0034-unified-sdk.md). E7 is not authorized by this design. E5/E6 evidence and provider-license gates remain open.

## 1. Two different continuous operations

| Public API | Input and state | Result | Actual broker orders |
|---|---|---|---|
| `engine.session(...)` | caller owns real-time market stream; verified externally authoritative broker account snapshots; persistent observation/strategy state only | decision proposals with `submitted=False` | **never** |
| `engine.simulation(data_provider=..., strategy=..., capital=...).paper()` | permitted external market-data source; SDK manages **synthetic** account, orders, fills and fee/risk models | Paper simulated events, synthetic ledger and terminal status | **never** |

Both return **async context-manager factories**. Examples: `async with engine.session(...) as s:` and `async with engine.simulation(...).paper() as s:`. Creating either factory is inert; entering the Paper context is the first moment permitted market-data connection may occur. No competing `engine.paper.start()`, `engine.evaluate.session()`, `await simulation.paper()`, `engine.live` or `simulation(...).live()` public spellings. `engine.evaluate(...)` remains a distinct one-shot decision proposal.

E5 HistoricalBacktest currently drives finite EventEnvelope replay and simulated order accounting through multiple existing core services; EventRuntime is only a reducer, not the entire trading engine. E6.7a must inventory actual event, StrategyRunner, fee/fill/order, journal and provider capabilities before designing streaming composition. Existing TradeTick/QuoteTick/Bar/OrderBook domain types do not imply production support for all execution combinations.

## 2. Canonical event and time contract

Accept validated canonical `EventEnvelope` objects at the advanced boundary. Capture source/market/instrument/venue identity, event time, available-at/published-at when source-proven, actual receive time, event ID and optional source sequence. Use timezone-aware UTC and causal visibility from existing core (max of available/received). Never manufacture a missing timestamp, source ordinal, price, volume, quote or market venue. A convenience `market.Trade` must map losslessly, or fail.

One writer serializes event ingest, timer, bar finalization and (for decision sessions) broker-account snapshot refresh. Multiple sources use bounded queues with known cursor/ordinal limits, not assumed global ordering across unprovable vendor streams. Equal canonical retransmission may be deduplicated at ingress only with identity/content proof; conflicting duplicate, sequence gap, time regression, late correction or non-pausable overflow produces typed BLOCKED/HALT rather than silent loss or hindsight resorting. Recorded stream replay preserves availability/receipt ordering and versioned policy.

## 3. Explicit warmup, subscriptions and session state

Session states: `created → warming → ready → paused/halted → operator-reviewed resume or closed`. `await session.warmup(validated_history)` initializes indicators using read-only eligible observations; no warmup simulated trades, actual proposals or future-data leakage. Declared `DataRequirements`, native interval, exchange calendar, DST/early close and gap policy are mandatory. Bar strategies execute on finalized bars only (native or versioned trade aggregation with causal watermark/completeness), not provisional bars; no bar-to-tick reconstruction.

Optional high-level `on_bar/on_tick/on_quote/on_timer` callbacks adapt to supported existing read-only Strategy contracts; unimplemented callback/data combinations remain errors. Stateful strategy snapshots and incremental indicators must replay consistently on the same captured tape.

## 4. Broker snapshot and decision-only boundaries

`session.update_portfolio(snapshot)` binds broker/account ID, positions, currency, buying power, open/unknown orders, as-of/receipt time and state/version; it never mutates the real account or creates a second authoritative ledger. A stale/wrong/incomplete/unreconciled snapshot blocks new exposure. `session.ingest(event)` returns typed observed decision outcome with explicit blockers, reason codes, versioned proposal IDs and expiry; **submitted=False** always. Caller-controlled external execution host may inspect the proposal but must independently check authorization/risk/account state before any future real order.

`engine.simulation(...).paper()` instead owns a completely separate synthetic cash/positions ledger and simulated fills; Paper **cannot** be initialized with a real account's holdings and does not use real trading credentials. Its market provider must only access permitted read-only market-data endpoints; source failure cannot silently change feeds.

## 5. Error handling, restart and shutdown

Record heartbeat, data staleness, latency, queue pressure, replay/source cursors, duplicate/late events, provider rights and memory. Reconnect is not completeness proof. Recovery requires verified cursor/backfill, matching journal/checkpoint/strategy state and, for decision-only sessions, fresh authoritative account reconciliation. No old proposal or simulated order is replayed as a live order. Context exit must be idempotent, join/cancel owned tasks, persist permitted audit and expose terminal reasons. Never log secrets or unauthorized raw market data.

## 6. E6.7a design fixtures and future E7 tests

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
