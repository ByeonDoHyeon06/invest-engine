# E6.7 — Unified SDK cookbook — 23 example calls and expected outcomes

**DESIGN ONLY — NOT RUNNABLE YET.** Each of the 23 examples includes a proposed return type and observable behavior. Seven include explicitly fictional toy-fixture output panels, **not** observed runtime stdout, actual market performance or broker orders. See the [canonical SDK design — result types and toy fixtures](E6_7_UNIFIED_SDK.md#return-types-statuses-and-illustrative-outputs) for nullable metrics, blocked/no-trade distinctions and projected return shapes.

This E6.7a DX revision uses four execution roots and a single typed market-source grammar. It does not change the currently implemented E0–E6 engine, release gates or broker permissions. [Canonical SDK design, including types and validation](E6_7_UNIFIED_SDK.md) · [ADR-0034 decision history](adr/0034-unified-sdk.md).

**Rules:** Four execution roots: simulation / research / evaluate / session. Use a typed `source=` for historical, Paper, Research and Session; Evaluate accepts a one-shot `market_data=` snapshot instead. Apply `strategy`, `risk`, simulated `capital`, and simulated `execution` consistently where relevant. Advanced options never require a different `HistoricalSimulationSpec → engine.prepare → engine.run` public ceremony; immutable specs remain available internally/for low-level compatibility. Proposed factories `sources.*`, `risk.Limits`, `execution.Model`, `allocation.Weights`, `simulation.inspect()` require E6.7a capability/signature verification. No actual broker order route.


## Getting Started

The same four roots for normal tasks. An already supplied one-shot Evaluate snapshot is not a stream source.

### 01 — Neutral engine (E6.7b)


```python
from invest_engine import Engine

engine = Engine()
```

**Expected contract (proposed):** `Engine`.

- Construction: inert facade; no configured market source, account, tasks or I/O
- No result metrics or trading status yet.


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

**Expected contract (proposed):** `SimulationResult`.

- Toy fixture `toy_no_trade_v1` (NOT an AAPL run): `status=NO_TRADE`, `summary.starting_cash=100000.00 USD`, `summary.ending_cash=100000.00 USD`
- `fills=()`, `blockers=()`, `metrics=None`; `export()` explicitly writes permitted artifacts.

**Illustrative toy-fixture output (not observed):**

```text
# Proposed toy_no_trade_v1 output — NOT the AAPL dataset result
NO_TRADE
starting_cash=100000.00 USD, ending_cash=100000.00 USD
fills=0, metrics=None, blockers=()
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

**Expected contract (proposed):** `AsyncContextManager[PaperSession] → PaperEvent stream`.

- Upon context entry: `paper.status=WARMING → READY` when warmup/source checks pass
- Toy `toy_manual_paper_v1` PaperEvent: `synthetic_fills=[{id:sim:fill:001, quantity:1, price:100.00 USD}]`; **real broker orders=0**
- After safe close: `paper.status=CLOSED`; terminal `paper.result` is an audited synthetic result (E7 only).

**Illustrative toy-fixture output (not observed):**

```text
# Proposed toy_manual_paper_v1 event shape — E7 future
PaperSession.status: WARMING -> READY -> CLOSED
PaperEvent.synthetic_fills: [sim:fill:001]  # virtual only
real_broker_orders: 0
```


The source is read-only market data. Paper owns synthetic cash, orders and fills, never broker trading credentials. E7 only; design target, not runnable.

### 04 — Research a family of strategies (E6.7d)


```python
from invest_engine import Engine, research, strategies, sources

result = Engine().research(
    source=sources.local("datasets/us/manifest.json"),
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

**Expected contract (proposed):** `ResearchResult`.

- Toy `toy_research_rejected_v1`: `status=COMPLETED`, `review.evaluated_candidates=2`, `review.eligible_candidates=0`, `best_candidate=None`
- This is **not** an observed strategy-performance result or holdout approval. The example's actual 6-candidate search has no claimed numerical output.

**Illustrative toy-fixture output (not observed):**

```text
# Proposed toy_research_rejected_v1 — NOT a strategy result
ResearchResult.status: COMPLETED
review: evaluated=2, eligible=0
best_candidate: None
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

**Expected contract (proposed):** `DecisionResult`.

- Toy valid no-action snapshot: `status=NO_ACTION`, `proposed_orders=()`, `submitted=False`
- Toy stale snapshot: `status=BLOCKED`, `reason_codes=(SNAPSHOT_STALE,)`; never a real order.

**Illustrative toy-fixture output (not observed):**

```text
# Proposed toy_decision_no_action_v1
DecisionResult.status: NO_ACTION
proposed_orders: ()
submitted: False
```


The broker account snapshot is provided and owned by the caller, timestamped and checked for identity/freshness/positions/open orders. A proposed order has `submitted=False`. The engine **does not send it**.

### 06 — Continuous managed-source decision session (E7)

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

**Expected contract (proposed):** `AsyncContextManager[DecisionSession] → DecisionResult stream`.

- After eligible warmup and broker snapshot: `session.status=READY`; toy decision `status=NO_ACTION`, `proposed_orders=()`
- Stale/missing account snapshot yields `BLOCKED/SNAPSHOT_STALE`, no proposed exposure. No synthetic fills or actual orders.

**Illustrative toy-fixture output (not observed):**

```text
# Proposed toy_manual_session_v1
DecisionSession.status: READY
DecisionResult.status: NO_ACTION
proposed_orders: (), submitted: False
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

**Expected contract (proposed):** `SimulationResult (same as #02)`.

- Adding `risk.Limits` and `execution.Model` changes `result.config` and may alter synthetic fills/fees/metrics; it **does not change the result type**.
- No invented PnL: toy no-action fixture remains `NO_TRADE` if the strategy never issues an order.


Explicit profile overrides compose into the same immutable typed spec. Bps values are simulated costs, not certified broker fees. Mandatory risk checks cannot be disabled by a convenience constructor.

### 08 — Caller-fed Paper with a manual source (E7; future)

```python
from invest_engine import sources

async with engine.simulation(
    source=sources.manual(),
    strategy=my_strategy,
    capital="100000 USD",
).paper() as paper:
    async for event in my_normalized_market_stream:
        outcome = await paper.ingest(event)
        print(outcome.status)
```

**Expected contract (proposed):** `AsyncContextManager[PaperSession] → PaperEvent via ingest()`.

- `outcome` is one typed PaperEvent/ingest outcome, e.g. toy `status=READY`, `reason_codes=()` after eligible event
- When the synthetic fill model fires: `outcome.synthetic_fills` holds synthetic fill IDs, never real order IDs; gap gives a blocked/halted outcome.


The same `source=` contract supports a read-only managed stream (example 03) **or** explicit caller-owned ingress. The **Paper simulation engine remains identical**, and real broker orders are never submitted. Manual events require validated identity, provenance, causal ordering, completeness and data rights.

### 09 — Local load, resample and data-quality inspection (E6.7c)


```python
from invest_engine import data
dataset = data.load("datasets/us/manifest.json")
bars = data.resample(dataset, interval="5m")
quality = data.inspect(bars)
print(quality.blockers)
```

**Expected contract (proposed):** `ValidatedDataset, ResampledData, DataQualityReport`.

- Clean fixture: `quality.blockers=()`; missing interval: `quality.blockers=(DATA_GAP, ...)`
- `data.resample()` only returns validated eligible coarser bars, not artificial ticks/quotes.


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

**Expected contract (proposed):** `PaperSession.status + PaperEvent.blockers`.

- Toy feed gap: `event.blockers=(DATA_GAP,)`, `paper.status=HALTED`; after context exit, `paper.status=CLOSED` with halt reason retained
- A disconnect is not proof of recovery; no broker order calls.


Context entry opens only permitted market-data I/O; context exit joins tasks and persists allowed audit. Resume requires verified source cursor, journal, synthetic ledger and state. No live order calls.

## Research

Add registered search and walk-forward options without an alternate ResearchSpec execution ceremony.

### 11 — Advanced research validation without new execution grammar (E6.7d)

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

**Expected contract (proposed):** `ResearchResult (same as #04)`.

- Toy `toy_research_rejected_v1`: `status=COMPLETED`, `best_candidate=None`, `review.reason_codes=(NO_ELIGIBLE_CANDIDATE,)`
- `config` records modeled costs, validation folds and risk settings; actual eligible-candidate count comes only from an executed eligible fixture.


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

**Expected contract (proposed):** `DecisionResult from ingest(); external review is not SDK output`.

- Toy eligible snapshot: `proposal.status=NO_ACTION`, `proposal.proposed_orders=()`
- `external_execution_host.review(...)` returns an **application-defined** value, not an Invest Engine type or proof of order placement.


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

**Expected contract (proposed):** `DecisionResult per normalized market event`.

- Eligible no-action toy: `status=NO_ACTION`, `reason_codes=()`
- Stale account toy: `status=BLOCKED`, `reason_codes=(SNAPSHOT_STALE,)`, `proposed_orders=()`. Normalizing an event does not invent missing source proof.


Never synthesize instrument identity, source sequence, publication timestamp, or unobservable trade volume. Missing/stale broker snapshots block new exposure. Serialized writer and explicit data gap/late policies required.

## Customization

Strategies, allocation, FX, preflight and trusted adapters extend the same basic calls.

### 14 — Pure indicator utilities (E6.7c)


```python
from invest_engine import indicators

average = indicators.sma(prices, period=20)
range_ = indicators.atr(bars, period=14)
```

**Expected contract (proposed):** `Typed indicator series / numeric features`.

- Illustrative **separate** SMA fixture: `sma([1, 2, 3], period=3)` → prefix unavailable, final value `2.0`
- Exact array/Decimal/NaN representation and ATR warmup convention are E6.7a type decisions. These are **not** computed from the snippet's unspecified `prices`/`bars`.


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

**Expected contract (proposed):** `SimulationResult; strategy callbacks return signal intents`.

- `on_bar()` returns a typed long/exit/no-action intent based on actual eligible data; risk/fill model determines any synthetic order/fill
- No predetermined buy signal, trade count or performance without a specified fixture. The final `result` has the same shape as #02.


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

**Expected contract (proposed):** `SimulationResult if supported; typed rejection otherwise`.

- Until single-account multi-strategy execution is implemented: expected `ConfigurationError.reason_codes=(UNSUPPORTED_COMBINATION,)` (proposed code)
- Do **not** report fabricated portfolio performance, separate virtual accounts, or silently run just one strategy.


Proposed list/allocation syntax is future-only, if shared-account multi-strategy execution becomes supported. Allocation is an option on Simulation, not a nested new execution grammar. PR #66 alone does not establish this capability.

### 17 — Inspect configured Simulation without changing its execution method (E6.7b/c)

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

**Expected contract (proposed):** `PlanPreview, then SimulationResult`.

- Proposed preflight on toy eligible source: `plan.blockers=()`, `plan.effective_config.risk.max_position=5%`
- An empty preview blocker set is **not** a guaranteed success; `historical()` revalidates runtime inputs and can return `BLOCKED`.

**Illustrative toy-fixture output (not observed):**

```text
# Proposed read-only preflight on eligible toy source
PlanPreview.blockers: ()
PlanPreview.effective_config.risk.max_position: 5%
# Runtime historical() still performs full validation
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

**Expected contract (proposed):** `SimulationResult with currency-separated summary`.

- Toy no-action fixture: `summary.cash_by_currency={USD:100000.00, KRW:1000000}`
- No invented cross-currency aggregate, FX trade or automatic buying power; unsupported combination yields a typed blocker/error.


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

**Expected contract (proposed):** `SimulationResult (same finite contract)`.

- `result.config` exposes the normalized redacted calendar, fill/fees and reporting policy IDs/versions; `result.evidence` refers to eligible actual sources
- Custom policy errors are typed; no generic performance output can be promised before running the chosen deterministic fixture.


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

**Expected contract (proposed):** `SimulationResult and explicit ArtifactReceipt (proposed)`.

- Toy no-trade fixture: `status=NO_TRADE`, `metrics=None`, `blockers=()`, `evidence.fixture=toy_no_trade_v1`
- Proposed `result.export(path)` → `ArtifactReceipt(location, schema_version, content_hash, redacted=True)` **only when** rights checks pass.


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

**Expected contract (proposed):** `ConfigurationError OR typed SimulationResult`.

- Bad source/config: `ConfigurationError.reason_codes=(SOURCE_MODE_MISMATCH,)` (proposed)
- Already-started run with discovered data gap: `result.status=BLOCKED`, `result.blockers=(DATA_GAP,)`, `result.metrics=None`; valid zero trades are instead `NO_TRADE`.

**Illustrative toy-fixture output (not observed):**

```text
# Proposed blocked-gap toy fixture
SimulationResult.status: BLOCKED
blockers: (DATA_GAP,), metrics: None
# Unlike valid NO_TRADE, this is not a successful run
```


Invalid construction/configuration raises typed errors. Started runs may yield explicit BLOCKED/FAILED evidence. Valid NO_TRADE is a distinct outcome from broken or missing data.

### 22 — Shared CLI / Python contract (E6.7d)


```bash
invest-engine run --config configs/historical-simulation.json
invest-engine inspect --run-id study-001
invest-engine explain --run-id study-001 --decision-id decision-001
```

**Expected contract (proposed):** `CLI status and artifact references; exact CLI formatting TBD`.

- Toy future CLI target, **not existing CLI stdout**: `{status: NO_TRADE, run_id: toy_no_trade_v1, metrics: null}`
- `inspect`/`explain` should expose versioned reason/evidence references; existing commands/flags and their real output remain compatible.


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

**Expected contract (proposed):** `DecisionResult followed by application-defined review`.

- Toy snapshot: `proposal.status=NO_ACTION`, `proposal.proposed_orders=()`, `proposal.submitted=False`
- `external_execution_host.review()` returns an independently defined application decision; the engine submits **zero** actual broker orders.


There is no `engine.live`, `engine.simulation(...).live()` or `engine.orders.submit()` interface. A separate broker adapter/application project owns credentials, broker-specific REST/WebSocket, real account authority, outbox, order reconciliation and kill switch. The original E8 live milestone becomes an **external integration verification track**, not an engine public execution mode.

## Verification / change control

E6.7a inventories exact typed source capabilities and actual implemented contracts and maps all 23 examples to phases and golden fixtures. E6.7b–e covers offline Simulation and Research; E7 managed/manual Paper and Session; E8 only optional **external** execution-host verification. Preserve existing Python/CLI, risk, PIT, fees, corporate actions, FX, journal/holdout, account authority and data-rights controls. Future API changes must align Issue #59, ADR, examples, roadmap and tests; unsupported combinations fail explicitly.
