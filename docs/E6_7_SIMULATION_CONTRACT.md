# E6.7 — Simulation contract: Historical and Paper

**Status: user-approved future SDK design (2026-11-22), not implemented or authorized Paper deployment.** [Unified SDK](E6_7_UNIFIED_SDK.md) · [public grammar](E6_7_PUBLIC_DX_GRAMMAR.md) · [23 examples](E6_7_SDK_EXAMPLES.md) · [streaming contract](E6_7_STREAMING_CONTRACT.md) · [ADR-0034](adr/0034-unified-sdk.md).

## One Simulation configuration, two explicit terminals

```python
from invest_engine import sources

result = engine.simulation(
    source=sources.local("datasets/AAPL/manifest.json"),
    strategy=my_strategy, capital="100000 USD",
).historical()

async with engine.simulation(
    source=sources.alpaca(credentials="market-data-secret-ref"),
    strategy=my_strategy, capital="100000 USD",
).paper() as paper:
    async for event in paper.events():
        print(event.status)
```

`Engine()` and `engine.simulation(...)` only configure typed settings and do not perform strategy execution, account access or provider I/O. The terminal method explicitly chooses the **clock/lifecycle** and appropriate source capability; the source never silently chooses a mode.

| Contract | `.historical()` | `.paper()` |
|---|---|---|
| Eligible source | typed historical `sources.local` / `sources.dataset` | E7 streaming market source `sources.alpaca` or manual `sources.manual()` |
| Clock | finite, deterministic historical/availability replay | live observed ingress with explicit causal clock |
| Operation | synchronous result | **async context manager factory**; network only upon permitted context entry |
| Orders/fills/account | **synthetic** ledger, modeled fees and fills | **synthetic** ledger, modeled fees and fills |
| Actual broker API / real account | **none** | **none** |
| Output | typed `SimulationResult`, evidence, results | `PaperSession` events/status and terminal simulated result |
| Core | existing E5 replay/strategy/risk simulation primitives | same shared primitives where actual capabilities permit; E7 ingress and recovery |
| Validation | manifest/PIT/calendar/corporate/actions/fees/source coverage | stream rights, warmup, finalization, staleness, gaps, duplicate/recovery |

A source is a **market-data** origin, not a broker order adapter. `sources.local/dataset` describe finite datasets, `sources.alpaca` is an illustrative read-only real-time provider, and `sources.manual()` means the external application owns normalized ingress. Source classes/names are *design targets subject to E6.7a verification*, not released APIs or a guarantee of access/licensing. A provider supporting two capabilities must advertise them explicitly; no silent download, gap filling or source fallback. Unsupported historical-versus-streaming combinations are typed BLOCKED/ConfigurationError.

## Unified option and advanced API contract

```python
from invest_engine import risk, execution

simulation = engine.simulation(
    source=historical_source,
    strategy=my_strategy,
    capital="100000 USD",
    risk=risk.Limits(max_position="5%", max_daily_loss="2%"),
    execution=execution.Model(commission_bps=10, spread_bps=5),
    calendar=exchange_calendar,
)
plan = simulation.inspect()     # optional read-only preflight
result = simulation.historical()
```

The same `strategy=`, synthetic `capital=`, `risk=` and simulated `execution=` policy concepts apply to Historical/Paper/Research **where supported**. These constructor names, signatures, defaults and any supported advanced options (fill, fees, calendar, allocation, corporate action, PIT, FX, reporting) must be checked against *real* E5/E6 implementation in E6.7a. User limits do not override hard mandatory risk gates. A configured strategy's read-only context, state and canonical event visibility remain identical in supported comparable inputs.

`inspect()` is an optional, read-only config/static capability check which may read declared local manifests; it does not connect a provider, run strategy/orders, or certify unavailable data. Runtime must revalidate. The fluent `.historical()` remains the public execution path regardless of advanced options. Immutable normalized simulation spec, existing `HistoricalBacktest`, typed `BacktestSpec/ResearchSpec` and `prepare/run` internals/low-level imports remain for compatibility and exact economic/CLI parity; they are **not a mandatory second user-facing SDK grammar**.

Paper supports both `source=stream` (managed read-only feed connected on async context entry) and `source=sources.manual()` (caller invokes `await paper.ingest(event)`). Both use one single-writer event/risk/synthetic ledger boundary. Exit cancels/joins owned tasks, records allowed journal/evidence, preserves halt reason, and never mutates an external actual account. Paper's modeled fills may not match any real broker order execution.

## Distinct from Research and decision-only operations

- `engine.research(source=historical, strategy=..., capital=..., risk=..., execution=..., search=..., validation=...)` uses the **same** historical source and simulated cost/risk semantics but adds registered E6 search/fold/holdout/evidence controls. Its internal spec/journal cannot be bypassed through ergonomic syntax.
- `engine.evaluate(market_data=..., portfolio=..., strategy=..., risk=...)` uses *one supplied snapshot*, does not select a streaming source, and returns a decision proposal with `submitted=False`.
- `engine.session(source=stream_or_manual, strategy=..., risk=...)` uses the **same streaming source contract as Paper**, but holds no synthetic or authoritative actual account and returns proposals only, based on separately refreshed verified broker snapshots.
- An actual order/outbox/broker credential/kill switch belongs to an **external Execution Host/Adapter**, never the unified Engine. No `engine.live`, `simulation(...).live()` or real order-submit API.

## E6.7a / E7 validation gates

- E6.7a: actual capability and source protocol inventory, type/return signatures and default/error snapshot for all 23 examples; source/terminal/rights mismatch, no hidden I/O, proposed policy names and inspected preflight boundaries.
- E6.7b–e: deterministic `.historical()` vs E5 low-level/CLI economic parity (decisions, fills, cash/reservations, fees, FX/PIT/corporate evidence), status and failure tests; advanced options do not require new execution grammar or reduce features.
- E7: managed/manual Paper context entry/exit/ingest, bounded canonical stream, warmup, finalized bars, dedupe/gap/overflow/halt/recovery, synthetic account-only reconciliation and **zero real broker order calls**.
- E8: optional independently approved external integration, not an SDK Live feature.

Passing these tests does **not** certify provider data rights, simulated-vs-real fill quality, historical profitability, E5/G1, E6/G2, or authorization to trade with real money.
