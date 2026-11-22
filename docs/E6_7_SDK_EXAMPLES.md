# E6.7 — Unified SDK examples (23 normative design targets)

**Status: DESIGN ONLY. None of the new Engine facade examples is executable yet.** 2026-11-22 current user-approved API. [Unified spec](E6_7_UNIFIED_SDK.md) · [Simulation contract](E6_7_SIMULATION_CONTRACT.md) · [API migration matrix](E6_7_API_CONTRACT_MATRIX.md) · [Streaming](E6_7_STREAMING_CONTRACT.md) · [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59).

## Four rules

1. Start with inert `Engine()`; only **four** primary operations: `simulation()`, `research()`, `evaluate()`, `session()`.
2. Configure simulation once and choose execution terminal `.historical()` (past, finite, synchronous) or `.paper()` (simulated trading with real-time data, async context, E7). **Neither may place real broker orders.**
3. `research(...)` organizes registered historical simulations; `evaluate(...)` and `session(...)` make proposals from externally supplied authoritative account snapshots, **without synthetic fills**.
4. Advanced typed specs and original E0–E6 low-level APIs/CLI remain available; the simple facade cannot bypass validation, evidence, risk, provenance or account authority.

All imports/classes and function names in the snippets are proposed public signatures; E6.7a must confirm supported combinations and actual type shapes, then add executable golden examples **only in the authorized implementation phase**. Values are illustrative research settings, never confirmed prices, profits, actual fees, data rights or live permission.

## Quickstart

### 01 — Neutral engine (E6.7b)

```python
from invest_engine import Engine

engine = Engine()
```

Neither package import nor construction fetches data, resolves broker credentials, opens accounts, starts tasks or executes strategies. No `mode`, `offline()` or `online()` constructor.

### 02 — Historical simulation / backtest (E6.7b)

```python
from invest_engine import Engine, strategies

engine = Engine()
result = engine.simulation(
    data="datasets/AAPL/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
).historical()

print(result.status, result.summary)
result.export("artifacts/aapl-orb")
```

`.historical()` executes a finite, verified local historical replay and returns `SimulationResult`; it does not automatically fetch a ticker's data. Historical Backtest is a *kind of simulation*, not an additional public `engine.backtest()` method.

### 03 — Paper simulation (E7; not implemented)

```python
from invest_engine import Engine, strategies, providers

engine = Engine()
async with engine.simulation(
    data_provider=providers.Alpaca(credentials="market-data-ref"),
    strategy=strategies.orb(),
    capital="100000 USD",
).paper() as session:
    async for event in session.events():
        print(event.status, event.reason_codes)
```

`.paper()` is an async context-manager **factory**; opening the context may connect to explicitly permitted read-only market data. Paper uses entirely synthetic cash/orders/fills and cannot submit real orders. Provider credentials are external secret *references* only.

### 04 — Research a family of strategies (E6.7d)

```python
from invest_engine import Engine, research, strategies

result = Engine().research(
    data="datasets/us/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
    search=research.Grid({
        "opening_range": ["5m", "15m", "30m"],
        "volume_multiplier": ["1.5", "2.0"],
    }),
    validation=research.WalkForward(train="12M", validation="3M", step="3M"),
    max_candidates=6,
)
print(result.review, result.best_candidate)
```

This invokes a bounded *registered historical* study under E6 journal/search/holdout restrictions. No strategy auto-promotion; `best_candidate` is `None` when no admissible candidate exists.

### 05 — Single-time proposal (future; E6.7a signature design)

```python
decision = engine.evaluate(
    market_data=verified_market_snapshot,
    portfolio=verified_broker_account_snapshot,
    strategy=strategies.orb(),
)
print(decision.status, decision.proposed_orders)
```

The broker account snapshot is provided and owned by the caller, timestamped and checked for identity/freshness/positions/open orders. A proposed order has `submitted=False`. The engine **does not send it**.

### 06 — Continuous caller-fed decision session (E7)

```python
async with engine.session(
    symbols=["AAPL"], strategy=strategies.orb(),
) as session:
    await session.warmup(validated_history)
    await session.update_portfolio(verified_broker_account_snapshot)
    async for event in normalized_market_stream:
        decision = await session.ingest(event)
        if decision.proposed_orders:
            print(decision.proposed_orders)
```

Unlike Paper, this session does **not** simulate a cash ledger or fills. Only read-only observations and proposals; no broker connection or permission required in the engine.

## Core API

### 07 — Explicit risk and modeled execution (E6.7b/c)

```python
from invest_engine import risk, execution, strategies

result = engine.simulation(
    data=dataset,
    strategy=strategies.orb(opening_range="30m"),
    capital="100000 USD",
    risk=risk.Policy(max_position="5%", max_daily_loss="2%"),
    execution=execution.Simulation(
        commission_bps=10, spread_bps=5,
        impact_bps=5, max_participation="5%",
    ),
).historical()
```

Explicit profile overrides compose into the same immutable typed spec. Bps values are simulated costs, not certified broker fees. Mandatory risk checks cannot be disabled by a convenience constructor.

### 08 — Explicit market-data provider (E6.7c; rights/adapter dependent)

```python
from invest_engine import Engine, providers

engine = Engine(data_provider=providers.Alpaca(credentials="market-data-ref"))
dataset = engine.data.fetch(
    symbols=["AAPL", "MSFT"],
    start="2022-10-01", end="2022-10-31",
    interval="1m", destination="datasets/oct-2022",
)
result = engine.simulation(
    data=dataset, strategy=my_strategy, capital="100000 USD",
).historical()
```

Provider injection is inert. Only explicit `fetch()` performs permitted network data I/O and validates completeness/calendar/PIT/source/license/warmup. `data_provider` never enables brokerage order APIs.

### 09 — Local load, resample and data-quality inspection (E6.7c)

```python
dataset = engine.data.load("datasets/us/manifest.json")
bars = engine.data.resample(dataset, interval="5m")
quality = engine.data.inspect(bars)
print(quality.blockers)
```

Coarsening native supported bar intervals is allowed; reconstructing quotes/ticks from OHLCV is not. Quality gates fail closed rather than invent missing market observations.

### 10 — Pure indicator utilities (E6.7c)

```python
from invest_engine import indicators

average = indicators.sma(prices, period=20)
range_ = indicators.atr(bars, period=14)
```

Standalone pure helpers do not require an Engine. They are subject to typed data/warmup and numerical parity.

### 11 — Custom strategy, shared across historical and streaming (E6.7c; E7 for stream)

```python
from invest_engine import Strategy, indicators

class MovingAverageCross(Strategy):
    def setup(self):
        self.require_bars("5m", warmup=51)

    def on_bar(self, ctx):
        closes = ctx.bars("5m").close
        fast = indicators.sma(closes, 10)
        slow = indicators.sma(closes, 50)
        if indicators.cross_above(fast, slow):
            return ctx.long(target="5%", stop_loss="1.5%")
        if indicators.cross_below(fast, slow):
            return ctx.exit()
        return ctx.no_action()

result = Engine().simulation(
    data=dataset, strategy=MovingAverageCross(), capital="100000 USD",
).historical()
```

High-level callbacks adapt to existing read-only manifest/context/signal/snapshot contracts. This is trusted plugin code, not a sandbox. Independent runs require isolated strategy state, canonical event visibility and snapshot/restore parity.

### 12 — Multiple instruments/strategies (future supported combinations only)

```python
from invest_engine import strategies, allocation

ensemble = strategies.ensemble(
    strategies=[strategies.orb(), MovingAverageCross()],
    allocation=allocation.Weighted(
        weights=["0.6", "0.4"], max_total_exposure="20%"
    ),
)
result = engine.simulation(
    data=validated_multi_symbol_dataset,
    strategy=ensemble, capital="100000 USD",
).historical()
```

One shared **simulated** account/risk budget is required. The #66 multi-symbol **decision** foundation alone does not establish shared-account backtesting or a runnable ensemble; unsupported configurations must be rejected.

## Advanced API

### 13 — Explicit immutable historical spec (E6.7b/c)

```python
from invest_engine import HistoricalSimulationSpec, risk, execution

spec = HistoricalSimulationSpec(
    data=dataset,
    strategy=my_strategy,
    capital="100000 USD",
    risk=risk.Policy(max_position="5%"),
    execution=execution.Simulation(commission_bps=10),
)
prepared = engine.prepare(spec)
print(prepared.effective_config, prepared.blockers)
result = engine.run(prepared)
```

This **advanced** path is the exact same offline pipeline as `simulation(...).historical()`, with durable hashes/capability checks. `prepare` validates and never executes; `run` checks stale/tampered plans. The actual typed class signature is an E6.7a fixture.

### 14 — Registered research spec / phased execution (E6.7d)

```python
from invest_engine import ResearchSpec, research, strategies

spec = ResearchSpec(
    data=dataset,
    strategy=strategies.orb(),
    capital="100000 USD",
    search=research.Grid({"opening_range": ["15m", "30m"]}),
    validation=research.WalkForward(train="12M", validation="3M", step="3M"),
)
result = engine.run(engine.prepare(spec))
print(result.status, result.review)
```

Same immutable registered research specification, budget, scope reservation, fold/embargo and lineage contract as `engine.research(...)`. No new holdout access.

### 15 — Multi-currency reporting (E6.7c; existing support-dependent)

```python
from invest_engine import Money, HistoricalSimulationSpec

spec = HistoricalSimulationSpec(
    data=validated_dataset,
    strategy=my_strategy,
    capital=[Money("100000", "USD"), Money("1000000", "KRW")],
    reporting=explicit_fx_reporting_policy,
)
result = engine.run(engine.prepare(spec))
print(result.summary)
```

Currency ownership stays separate; FX *reporting* does not create FX trades/buying power. Unsupported multi-currency/venue execution is rejected.

### 16 — Typed custom dependency and fee/fill policies (E6.7c)

```python
from invest_engine import Engine, HistoricalSimulationSpec, execution

engine = Engine(
    data_provider=my_market_data_provider,
    calendar=my_exchange_calendar,
    artifact_store=my_artifact_store,
)
spec = HistoricalSimulationSpec(
    data=validated_dataset, strategy=my_strategy, capital=opening_cash,
    risk=custom_risk_policy,
    execution=execution.Simulation(fill=custom_fill, fees=custom_fees),
    reporting=reporting_policy,
)
result = engine.run(engine.prepare(spec))
```

Provider/calendar/storage and policy implementations are trusted typed extensions, versioned and evidence-hashed (secrets redacted). No unrestricted kwargs bag or silent invalid-combination fallback.

### 17 — Consistent results and artifacts (E6.7b/d)

```python
result = engine.simulation(
    data=dataset, strategy=my_strategy, capital="100000 USD",
).historical()

print(result.status, result.summary, result.evidence)
print(result.blockers, result.config)
if result.metrics is not None:
    print(result.metrics.max_drawdown)
result.export("artifacts/study-001")
```

Finite `SimulationResult` and `ResearchResult` share `status/summary/metrics?/evidence/config/blockers/export`; specialized `fills/equity/portfolio/review` are typed. No fabricated success/PnL for invalid data.

### 18 — Failure handling is not zero-trade (E6.7b/c)

```python
from invest_engine import errors

try:
    result = engine.simulation(
        data=dataset, strategy=my_strategy, capital="100000 USD",
    ).historical()
except errors.ConfigurationError as exc:
    print(exc.reason_codes)
else:
    if result.blockers:
        print("blocked:", result.blockers)
    elif result.metrics is not None:
        print(result.metrics)
```

Invalid construction/configuration raises typed errors. Started runs may yield explicit BLOCKED/FAILED evidence. Valid NO_TRADE is a distinct outcome from broken or missing data.

### 19 — Shared CLI / Python contract (E6.7d)

```bash
invest-engine run --config configs/historical-simulation.json
invest-engine inspect --run-id study-001
invest-engine explain --run-id study-001 --decision-id decision-001
```

Planned new config decodes the same normalized spec as `.historical()`. Preserve working legacy commands (`backtest`, `import-csv`, `stress`, `replay-synthetic`, `e5-research-v1`) through documented migration.

## Runtime and integration boundaries

### 20 — Host application uses decisions, not engine live orders (future)

```python
engine = Engine()
async with engine.session(symbols=["AAPL"], strategy=my_strategy) as s:
    await s.warmup(validated_history)
    async for event in external_market_stream:
        await s.update_portfolio(await app.read_verified_broker_snapshot())
        proposal = await s.ingest(event)
        await external_execution_host.review(proposal)
```

`external_execution_host` and `app` are **application-owned placeholders, not invest_engine modules**. The application alone would handle authorization, broker SDK, reconciliation, and any actual order submission. `review()` here is not automatic trading approval.

### 21 — Normalized event ingestion and snapshot freshness (E7)

```python
from invest_engine import market

async with engine.session(symbols=["AAPL"], strategy=my_strategy) as s:
    await s.warmup(validated_history)
    await s.update_portfolio(verified_account_snapshot)
    for raw in external_events:
        outcome = await s.ingest(market.Trade(
            symbol=raw.symbol, price=raw.price, quantity=raw.quantity,
            timestamp=raw.event_time, received_at=raw.received_at,
            event_id=raw.event_id, source=raw.source,
        ))
        print(outcome.status, outcome.reason_codes)
```

Never synthesize instrument identity, source sequence, publication timestamp, or unobservable trade volume. Missing/stale broker snapshots block new exposure. Serialized writer and explicit data gap/late policies required.

### 22 — Paper state, recovery and shutdown (E7)

```python
async with engine.simulation(
    data_provider=authorized_market_provider,
    strategy=my_strategy, capital="100000 USD",
).paper() as paper:
    async for event in paper.events():
        if event.blockers:
            print(event.blockers)
            break
    print(paper.status)
# context closes, joins owned tasks and records a terminal audited result
```

Provider connection on async context entry; no background I/O on Engine or builder creation. Reconnect does not clear a gap/HALT; journal/cursor/synthetic ledger verification needed for operator-reviewed resume. Paper simulated fills can differ from any real broker.

### 23 — External execution remains outside the SDK (optional future E8)

```python
# Illustrative architecture only — NOT part of invest_engine API:
proposal = engine.evaluate(
    market_data=verified_market_snapshot,
    portfolio=verified_broker_account_snapshot,
    strategy=my_strategy,
)
await external_execution_host.review(proposal)
# Real-order approval/submission, if ever authorized, belongs to the host.
```

There is no `engine.live`, `engine.simulation(...).live()` or `engine.orders.submit()` interface. A separate broker adapter/application project owns credentials, broker-specific REST/WebSocket, real account authority, outbox, order reconciliation and kill switch. The original E8 live milestone becomes an **external integration verification track**, not an engine public execution mode.

## Change control and release safety

These 23 cases are **design targets**, not working SDK methods. E6.7a must enumerate actual support, source/mode and class signatures, expected results, typed failures and concrete fixtures; add public API snapshots and deterministic golden parity. E6.7b–e implement supported offline parts; E7 separately authorizes Paper and continuous decision sessions; E8 external applications only after independent approval. Retain existing E0–E6 implementation and CLI behavior and all PIT/fees/corporate/risk/holdout/data-rights gates. Do not introduce an SDK broker-order path, hidden side effects or unverifiable profitability claims. Any later public-name change requires user decision and coordinated ADR, Issue #59, roadmap, docs and tests.
