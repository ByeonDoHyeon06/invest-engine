# E6.7 — Unified SDK examples (23 design targets)

**DESIGN ONLY — NOT RUNNABLE YET.** This E6.7a DX revision uses four execution roots and a single typed market-source grammar. It does not change the currently implemented E0–E6 engine, release gates or broker permissions. [SDK specification](E6_7_UNIFIED_SDK.md), [public grammar](E6_7_PUBLIC_DX_GRAMMAR.md), [simulation contract](E6_7_SIMULATION_CONTRACT.md), [streaming contract](E6_7_STREAMING_CONTRACT.md), [API migration matrix](E6_7_API_CONTRACT_MATRIX.md), [ADR-0034](adr/0034-unified-sdk.md).

**Rules:** Four execution roots: simulation / research / evaluate / session. Use a typed `source=` for historical, Paper, Research and Session; Evaluate accepts a one-shot `market_data=` snapshot instead. Apply `strategy`, `risk`, simulated `capital`, and simulated `execution` consistently where relevant. Advanced options never require a different `HistoricalSimulationSpec → engine.prepare → engine.run` public ceremony; immutable specs remain available internally/for low-level compatibility. Proposed factories `sources.*`, `risk.Limits`, `execution.Model`, `allocation.Weights`, `simulation.inspect()` require E6.7a capability/signature verification. No actual broker order route.


## Getting Started

The same four roots for normal tasks. An already supplied one-shot Evaluate snapshot is not a stream source.

### 01 — Neutral engine (E6.7b)


```python
from invest_engine import Engine

engine = Engine()
```

Neither package import nor construction fetches data, resolves broker credentials, opens accounts, starts tasks or executes strategies. No `mode`, `offline()` or `online()` constructor.

### 02 — Historical simulation / backtest (E6.7b)


```python
from invest_engine import sources
from invest_engine import Engine, strategies

engine = Engine()
result = engine.simulation(
    source=sources.local("datasets/AAPL/manifest.json"),
    strategy=strategies.orb(),
    capital="100000 USD",
).historical()

print(result.status, result.summary)
result.export("artifacts/aapl-orb")
```

`.historical()` executes a finite, verified local historical replay and returns `SimulationResult`; it does not automatically fetch a ticker's data. Historical Backtest is a *kind of simulation*, not an additional public `engine.backtest()` method.

### 03 — Paper simulation (E7; not implemented)

```python
from invest_engine import Engine, sources, strategies

engine = Engine()
async with engine.simulation(
    source=sources.alpaca(credentials="market-data-secret-ref"),
    strategy=strategies.orb(),
    capital="100000 USD",
).paper() as paper:
    async for event in paper.events():
        print(event.status)
```

The source is read-only market data. Paper owns synthetic cash, orders and fills, never broker trading credentials. E7 only; design target, not runnable.

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
from invest_engine import sources

async with engine.session(
    source=sources.alpaca(credentials="market-data-secret-ref"),
    strategy=strategies.orb(),
    symbols=["AAPL"],
) as session:
    await session.warmup(validated_history)
    await session.update_portfolio(verified_broker_account_snapshot)
    async for decision in session.decisions():
        print(decision.proposed_orders)
```

Session supports a managed market-data source just like Paper, but emits proposals only. Use `source=sources.manual()` and `session.ingest()` when the application owns the feed. E7 only.

## Simulation

Extend risk, execution, source and diagnostics without changing the Simulation terminal.

### 07 — Explicit risk and modeled execution (E6.7b/c)


```python
from invest_engine import sources
from invest_engine import risk, execution, strategies

result = engine.simulation(
    source=sources.dataset(dataset),
    strategy=strategies.orb(opening_range="30m"),
    capital="100000 USD",
    risk=risk.Limits(max_position="5%", max_daily_loss="2%"),
    execution=execution.Model(
        commission_bps=10, spread_bps=5,
        impact_bps=5, max_participation="5%",
    ),
).historical()
```

Explicit profile overrides compose into the same immutable typed spec. Bps values are simulated costs, not certified broker fees. Mandatory risk checks cannot be disabled by a convenience constructor.

### 08 — Explicit market-data provider (E6.7c; rights/adapter dependent)

```python
from invest_engine import sources

stream = sources.alpaca(credentials="market-data-secret-ref")
async with engine.session(
    source=sources.manual(),
    source=stream,
    strategy=my_strategy,
    symbols=["AAPL"],
) as session:
    await session.warmup(validated_history)
    await session.update_portfolio(verified_account_snapshot)
    async for decision in session.decisions():
        print(decision.status)
```

No `Engine(data_provider=...)` precedence. A source identifies read-only market data, not trading authority; the same streaming source can be passed to Simulation Paper. Licenses, event identities and calendars must be verified.

### 09 — Local load, resample and data-quality inspection (E6.7c)


```python
from invest_engine import data
dataset = data.load("datasets/us/manifest.json")
bars = data.resample(dataset, interval="5m")
quality = data.inspect(bars)
print(quality.blockers)
```

Coarsening native supported bar intervals is allowed; reconstructing quotes/ticks from OHLCV is not. Quality gates fail closed rather than invent missing market observations.

### 10 — Paper state, recovery and shutdown (E7)

```python
from invest_engine import sources

async with engine.simulation(
    source=sources.alpaca(credentials="market-data-secret-ref"),
    strategy=my_strategy,
    capital="100000 USD",
).paper() as paper:
    async for event in paper.events():
        if event.blockers:
            print(event.blockers)
            break
    print(paper.status)
```

Context entry opens only permitted market-data I/O; context exit joins tasks and persists allowed audit. Resume requires verified source cursor, journal, synthetic ledger and state. No live order calls.

## Research

Add registered search and walk-forward options without an alternate ResearchSpec execution ceremony.

### 11 — Registered research spec / phased execution (E6.7d)

```python
from invest_engine import sources, research, risk, execution

study = engine.research(
    source=sources.dataset(validated_dataset),
    strategy=strategies.orb(),
    capital="100000 USD",
    risk=risk.Limits(max_position="5%"),
    execution=execution.Model(commission_bps=10),
    search=research.Grid({"opening_range": ["15m", "30m"]}),
    validation=research.WalkForward(train="12M", validation="3M", step="3M"),
)
print(study.status, study.review)
```

Advanced research uses the **same** source/strategy/capital/risk/execution option names, adding research-specific search and validation. Immutable registered study specs, journaling, holdout and resource gates still execute internally; no public second prepare/run grammar required.

## Decision

Session accepts the same managed/manual source contract as Paper but produces only proposals.

### 12 — Host application uses decisions, not engine live orders (future)


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

### 13 — Normalized event ingestion and snapshot freshness (E7)


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

## Customization

Strategies, allocation, FX, preflight and trusted adapters extend the same basic calls.

### 14 — Pure indicator utilities (E6.7c)


```python
from invest_engine import indicators

average = indicators.sma(prices, period=20)
range_ = indicators.atr(bars, period=14)
```

Standalone pure helpers do not require an Engine. They are subject to typed data/warmup and numerical parity.

### 15 — Custom strategy, shared across historical and streaming (E6.7c; E7 for stream)


```python
from invest_engine import sources
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
    source=sources.dataset(dataset), strategy=MovingAverageCross(), capital="100000 USD",
).historical()
```

High-level callbacks adapt to existing read-only manifest/context/signal/snapshot contracts. This is trusted plugin code, not a sandbox. Independent runs require isolated strategy state, canonical event visibility and snapshot/restore parity.

### 16 — Multiple instruments/strategies (future supported combinations only)

```python
from invest_engine import sources, strategies, allocation, risk

result = engine.simulation(
    source=sources.dataset(validated_multi_symbol_dataset),
    strategy=[strategies.orb(), MovingAverageCross()],
    allocation=allocation.Weights(["0.6", "0.4"]),
    capital="100000 USD",
    risk=risk.Limits(max_total_exposure="20%"),
).historical()
```

Proposed list/allocation syntax is future-only, if shared-account multi-strategy execution becomes supported. Allocation is an option on Simulation, not a nested new execution grammar. PR #66 alone does not establish this capability.

### 17 — Explicit immutable historical spec (E6.7b/c)

```python
from invest_engine import sources, risk

simulation = engine.simulation(
    source=sources.dataset(validated_dataset),
    strategy=my_strategy,
    capital="100000 USD",
    risk=risk.Limits(max_position="5%"),
)
plan = simulation.inspect()
print(plan.effective_config, plan.blockers)
result = simulation.historical()
```

Optional `inspect()` is read-only preflight (possibly reading explicitly permitted local manifests), never a new mandatory lifecycle or provider/trading connection. Internal typed specs and existing low-level prepare/run paths remain available for compatibility; advanced SDK callers use the same Simulation terminal.

### 18 — Multi-currency reporting (E6.7c; existing support-dependent)

```python
from invest_engine import Money, sources

result = engine.simulation(
    source=sources.dataset(validated_dataset),
    strategy=my_strategy,
    capital=[Money("100000", "USD"), Money("1000000", "KRW")],
    reporting=explicit_fx_reporting_policy,
).historical()
print(result.summary)
```

Multi-currency reporting extends Simulation with optional configuration, not another run API. Reporting never confers FX execution or buying power; unsupported combinations fail explicitly.

### 19 — Typed custom dependency and fee/fill policies (E6.7c)

```python
from invest_engine import sources, execution

result = engine.simulation(
    source=sources.dataset(validated_dataset),
    strategy=my_strategy,
    capital=opening_cash,
    calendar=my_exchange_calendar,
    risk=custom_risk_limits,
    execution=execution.Model(fill=custom_fill, fees=custom_fees),
    reporting=my_reporting_policy,
    artifact_store=my_artifact_store,
).historical()
```

Typed advanced adapters/policies are optional **operation-level** arguments. No hidden Engine-global source precedence, arbitrary untyped kwargs, mandatory alternate Spec/prepare/run or safety bypass.

## Reference

Results, typed failures, existing CLI and external execution boundaries.

### 20 — Consistent results and artifacts (E6.7b/d)


```python
from invest_engine import sources
result = engine.simulation(
    source=sources.dataset(dataset), strategy=my_strategy, capital="100000 USD",
).historical()

print(result.status, result.summary, result.evidence)
print(result.blockers, result.config)
if result.metrics is not None:
    print(result.metrics.max_drawdown)
result.export("artifacts/study-001")
```

Finite `SimulationResult` and `ResearchResult` share `status/summary/metrics?/evidence/config/blockers/export`; specialized `fills/equity/portfolio/review` are typed. No fabricated success/PnL for invalid data.

### 21 — Failure handling is not zero-trade (E6.7b/c)


```python
from invest_engine import sources
from invest_engine import errors

try:
    result = engine.simulation(
        source=sources.dataset(dataset), strategy=my_strategy, capital="100000 USD",
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

### 22 — Shared CLI / Python contract (E6.7d)


```bash
invest-engine run --config configs/historical-simulation.json
invest-engine inspect --run-id study-001
invest-engine explain --run-id study-001 --decision-id decision-001
```

Planned new config decodes the same normalized spec as `.historical()`. Preserve working legacy commands (`backtest`, `import-csv`, `stress`, `replay-synthetic`, `e5-research-v1`) through documented migration.

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

## Verification / change control

E6.7a inventories exact typed source capabilities and actual implemented contracts and maps all 23 examples to phases and golden fixtures. E6.7b–e covers offline Simulation and Research; E7 managed/manual Paper and Session; E8 only optional **external** execution-host verification. Preserve existing Python/CLI, risk, PIT, fees, corporate actions, FX, journal/holdout, account authority and data-rights controls. Future API changes must align Issue #59, ADR, examples, roadmap and tests; unsupported combinations fail explicitly.
