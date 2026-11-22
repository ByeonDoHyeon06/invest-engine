# E6.7 — Unified SDK examples (revised public API design)

> **DESIGN ONLY — NOT EXECUTABLE.** These are proposed public interfaces, not implemented Python methods, live credentials, verified trading results or permission to place real orders. See [specification](E6_7_UNIFIED_SDK.md), [API contract matrix](E6_7_API_CONTRACT_MATRIX.md), [ADR-0034](adr/0034-unified-sdk.md) and [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59). E6.7a records signatures, capability support and golden fixtures before implementation. Paper requires E7; Live requires separate E8 approval.

## Read this first — four rules

1. **One neutral entry point:** `Engine()` creates an inert facade, with optional typed providers/profiles. No mode argument, no network on construction.
2. **One-shot operations return a result directly:** `engine.backtest(...)`, `engine.research(...)`, `engine.evaluate(...)`. Advanced callers may always use `engine.prepare(spec)` then `engine.run(prepared)` for **supported finite offline runs**.
3. **Continuous operations own a session:** `engine.session(...)` is **caller-fed, decision-only**; `engine.paper.start(...)` is an E7 managed **simulated** stream; `engine.live.start(...)` is a future E8-only interface. Async context entry starts lifecycle/I/O where explicitly configured; no background work on `Engine()`.
4. **One configuration/result vocabulary:** `strategy=strategies.orb()`, `risk=risk.Policy(...)`, `execution=execution.Simulation(...)`, `data_provider=...`; completed run results expose `status`, `summary`, `metrics` (nullable), `evidence`, `config`, `blockers`, `export(...)`. Special results add typed fields, not incompatible synonyms.

`data` on an operation is its dataset/market input; `data_provider` is an injected source dependency; `engine.data` is the data service. These names must not be overloaded. No hidden provider credentials, default broker, implicit historical download or Live mode. Simplification **must not remove** advanced E5/E6 capabilities or protections.

## Quickstart — learn the main verbs first

### 01. Create the engine (E6.7b)

```python
from invest_engine import Engine

engine = Engine()
```

Constructor and import are inert; no accounts, data fetches, tasks or orders.

### 02. Basic backtest (E6.7b)

```python
from invest_engine import Engine, strategies

engine = Engine()
result = engine.backtest(
    data="datasets/AAPL/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
)
print(result.summary)
result.export("artifacts/aapl-orb")
```

A manifest is an existing permitted local dataset, not a symbol-based automatic download. `capital` is a currency-bearing decimal string parsed into typed Money; no float money.

### 03. Common result/error handling (E6.7b/d)

```python
from invest_engine import errors

try:
    result = engine.backtest(
        data="datasets/AAPL/manifest.json",
        strategy=strategies.orb(),
        capital="100000 USD",
    )
except errors.ConfigurationError as exc:
    print(exc.reason_codes)
else:
    print(result.status, result.summary, result.evidence, result.blockers)
    if result.metrics is not None:
        print(result.metrics.max_drawdown)
    result.export("artifacts/audit")
```

Contract errors are typed; a started run may instead return BLOCKED/FAILED with evidence. Never manufacture metrics, profit or an empty success when data is unusable. For finite `RunResult` variants, the six shared fields and export method have the same meaning. Decision outcomes also expose `status/evidence/blockers/reason_codes` but are not forced to invent a PnL summary.

### 04. One-shot research (E6.7d)

```python
from invest_engine import Engine, strategies, research

result = Engine().research(
    data="datasets/us-market/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
    search=research.Grid({
        "opening_range": ["5m", "15m", "30m"],
        "volume_multiplier": ["1.5", "2.0", "2.5"],
    }),
    validation=research.WalkForward(train="12M", validation="3M", step="3M"),
    costs=research.CostScenarios(base=True, stress=True),
    max_candidates=9,
)
print(result.status, result.summary)
print(result.review, result.best_candidate)
```

`research(...)` is the same direct-call grammar as `backtest(...)`. Under the hood it reserves an immutable journal plan, checks budgets/temporal splits and executes only the authorized development scope. `best_candidate` is `None` if no eligible candidate; this does **not** authorize holdout, Paper or Live. For staged research use `ResearchSpec` + `prepare/run` (example 13).

### 05. Single decision with caller-supplied assets (future; E6.7a signature design)

```python
decision = engine.evaluate(
    market_data=verified_market_snapshot,
    portfolio=verified_broker_account_snapshot,
    strategy=strategies.orb(),
)
print(decision.status, decision.reason_codes)
print(decision.proposed_orders)  # proposals only; submitted=False
```

No network request or order is performed implicitly. Verify authoritative broker account identity, timestamp, currency, buying power, open orders and freshness. Stateless entry may require sufficient explicit strategy history; absence is BLOCKED rather than a fictitious decision.

## Core API — typed data, strategy, policy and application

### 06. Explicit provider fetch (E6.7c; provider/license adapter dependent)

```python
from invest_engine import Engine, providers, strategies

engine = Engine(data_provider=providers.Alpaca(credentials="alpaca-market-data"))
dataset = engine.data.fetch(
    symbols=["AAPL", "MSFT"],
    start="2022-10-01",
    end="2022-10-31",
    interval="1m",
    destination="datasets/us-oct-2022",
)
result = engine.backtest(data=dataset, strategy=strategies.orb(), capital="100000 USD")
```

The credential is an external secret-manager reference, not a literal key. `data_provider` injects an inert dependency; **only** `fetch()` requests external data after rights/provenance checks. Explicit warmup, calendar, PIT, identity and completeness required; no implicit gap fill or unsupported raw export.

### 07. Local data tools (E6.7c)

```python
engine = Engine()
dataset = engine.data.load("datasets/us/manifest.json")
bars = engine.data.resample(dataset, interval="5m")
quality = engine.data.inspect(bars)
print(quality.blockers)
```

`engine.data` owns data actions; `backtest(data=...)` consumes their validated result. Resample only supported *coarser* native resolutions with PIT/calendar preserved. No bar-to-tick synthesis.

### 08. Configure an existing strategy consistently (E6.7b/c)

```python
from invest_engine import strategies

orb = strategies.orb(opening_range="30m", volume_multiplier="2.0")
result = engine.backtest(
    data=dataset,
    strategy=orb,
    capital="100000 USD",
)
```

Preset strategy constructors are consistently lowercase factories returning configured instances. A bare `strategies.ORB` class is not a separate research-only public rule.

### 09. Custom strategy (E6.7c)

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

result = engine.backtest(
    data=dataset, strategy=MovingAverageCross(), capital="100000 USD"
)
```

Convenience intent helpers convert to the **existing** read-only Strategy/Signal protocol. Risk, allocator and execution alone decide orders. Stateful strategies need deterministic snapshot/restore and isolated instances per run; Python plugin code is trusted, not sandboxed. `warmup=51` must satisfy cross-detection's prior observations.

### 10. Independent indicator helpers (E6.7c)

```python
from invest_engine import indicators

mean = indicators.sma(prices, period=20)
volatility = indicators.atr(bars, period=14)
```

Pure helpers do not require an Engine instance. Unsupported indicators fail explicitly and never construct fictional inputs.

### 11. Multiple strategies, one shared simulated account (extension; only supported paths)

```python
from invest_engine import strategies, allocation

ensemble = strategies.ensemble(
    strategies=[strategies.orb(), MovingAverageCross()],
    allocation=allocation.Weighted(
        weights=["0.6", "0.4"], max_total_exposure="20%"
    ),
)
result = engine.backtest(
    data=validated_multi_symbol_dataset,
    strategy=ensemble,
    capital="100000 USD",
)
print(result.summary)
```

`strategies.ensemble()` follows the lowercase preset factory rule. One shared simulated cash/risk authority, never one fake account per strategy. Full multi-instrument shared-account execution is **not yet implemented** by the facade or PR #66 contracts; mark unsupported combinations rather than simulate silently. Future policy names and availability must be confirmed in E6.7a.

### 12. Application integration without arbitrary dataset paths (E6.7d)

```python
from fastapi import FastAPI
from invest_engine import Engine, strategies

app = FastAPI()

@app.post("/backtest")
def backtest(dataset_id: str, capital: str):
    engine = Engine()
    dataset = engine.data.load_registered(dataset_id)
    result = engine.backtest(
        data=dataset, strategy=strategies.orb(), capital=capital
    )
    return result.summary.to_dict()
```

Surrounding web app is not part of SDK. Authenticate tenants and dataset registry, bound CPU/queue, enforce storage rights and isolate runs; never use unchecked user file paths.

## Advanced — explicit specs, reproducibility and extensibility

### 13. Same underlying prepare/run path (E6.7b/d)

```python
from invest_engine import BacktestSpec, ResearchSpec, strategies, research

backtest_spec = BacktestSpec(
    data="datasets/AAPL/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
)
prepared = engine.prepare(backtest_spec)
print(prepared.effective_config, prepared.blockers)
result = engine.run(prepared)

research_spec = ResearchSpec(
    data="datasets/us-market/manifest.json",
    strategy=strategies.orb(),
    capital="100000 USD",
    search=research.Grid({"opening_range": ["15m", "30m"]}),
    validation=research.WalkForward(train="12M", validation="3M", step="3M"),
)
study_result = engine.run(engine.prepare(research_spec))
```

Both direct calls delegate to **the same immutable typed spec and validated engine path**. `prepare` does not execute a strategy or orders; `run` rejects stale/tampered plans, unauthorized holdout and unsupported combinations. The research journal reservation remains mandatory. Signatures are proposed; E6.7a must verify field parity.

### 14. Risk and simulation cost policy (E6.7b/c)

```python
from invest_engine import Engine, profiles, strategies, risk, execution

engine = Engine(profile=profiles.research_v1())
result = engine.backtest(
    data=dataset,
    strategy=strategies.orb(opening_range="30m"),
    capital="100000 USD",
    risk=risk.Policy(max_position="5%", max_daily_loss="2%"),
    execution=execution.Simulation(
        commission_bps=10, spread_bps=5, impact_bps=5,
        max_participation="5%",
    ),
)
print(result.config, result.evidence)
```

No split between `risk.Policy`, `policies.execution` and other competing policy factories. `execution.Simulation` accepts versioned supported fill/fees options at the advanced boundary; modeled bps are not actual broker charges. A custom policy must not bypass mandatory safety constraints.

### 15. Multi-currency / FX reporting (E6.7c; supported combinations only)

```python
from invest_engine import BacktestSpec, Money

spec = BacktestSpec(
    data=validated_dataset,
    strategy=my_strategy,
    capital=[Money("100000", "USD"), Money("1000000", "KRW")],
    reporting=fx_reporting_policy,
)
result = engine.run(engine.prepare(spec))
print(result.metrics, result.summary)
```

Separate currencies remain separate cash/accounting primitives. Explicit as-of FX reporting never implies FX execution or buying power. Unimplemented cross-market combinations fail.

### 16. Advanced typed provider/policy injection (E6.7c)

```python
from invest_engine import Engine, BacktestSpec, execution

engine = Engine(
    data_provider=my_data_provider,
    calendar=my_exchange_calendar,
    artifact_store=my_artifact_store,
)
spec = BacktestSpec(
    data=validated_dataset,
    strategy=my_strategy,
    capital=opening_cash,
    risk=custom_risk_policy,
    execution=execution.Simulation(fill=custom_fill, fees=custom_fees),
    evaluation=evaluation_window,
    reporting=reporting_policy,
)
result = engine.run(engine.prepare(spec))
```

Typed dependencies are injected at one documented boundary and inert until called. Custom provider/calendar/store identity and versions are hashed, secrets excluded. Existing typed low-level contracts remain accessible if a capability is not yet wrapped; no magical dict of arbitrary options.

### 17. CLI shares the exact run spec (E6.7d)

```bash
invest-engine run --config configs/backtest.json
invest-engine inspect --run-id research-001
invest-engine explain --run-id research-001 --decision-id decision-001
```

Python and CLI decode a common versioned spec; do not duplicate execution semantics. Preserve existing `backtest`, `import-csv`, `stress`, `replay-synthetic` and `e5-research-v1` interfaces or provide explicit migrations.

## Runtime — sessions are intentionally different from one-shot calls

### 18. Caller-fed, decision-only session (E7 target)

```python
from invest_engine import Engine, strategies

engine = Engine()
async with engine.session(symbols=["AAPL"], strategy=strategies.orb()) as session:
    await session.warmup(validated_history)
    await session.update_portfolio(verified_broker_account_snapshot)

    async for event in normalized_market_stream:
        decision = await session.ingest(event)
        if decision.proposed_orders:
            print(decision.proposed_orders)
```

**`engine.session()` is the sole proposed caller-fed session factory**, replacing `engine.evaluate.session()` and not a second trading mode. Session observes and proposes; `submitted=False` always. Warmup and account snapshot are explicit; import/factory do not connect to providers. A blocked event is not equivalent to NO_TRADE.

### 19. Optional snapshot refresh / raw trade conversion (E7 target)

```python
from invest_engine import market

async with engine.session(symbols=["AAPL"], strategy=my_strategy) as session:
    await session.warmup(validated_history)
    async for tick in my_websocket:
        await session.update_portfolio(broker.account_snapshot)
        result = await session.ingest(market.Trade(
            symbol=tick.symbol,
            price=tick.price, quantity=tick.quantity,
            timestamp=tick.event_time, received_at=tick.received_at,
            event_id=tick.event_id, source=tick.source,
        ))
        print(result.status, result.reason_codes)
```

The source and identity cannot be invented, and the account snapshot must be immutable and causally available. Same-session `update_portfolio` / `ingest` serialize through one writer. An unsupported quote/tick subscription fails explicitly, not silent bar reconstruction.

### 20. Managed Paper with a real-time data provider (E7 target)

```python
from invest_engine import Engine, providers, strategies

engine = Engine()
async with engine.paper.start(
    data_provider=providers.Alpaca(credentials="alpaca-market-data"),
    symbols=["AAPL", "NVDA", "TSLA"],
    strategy=strategies.orb(),
    capital="100000 USD",
) as session:
    async for event in session.events():
        print(event.status, event.reason_codes)
```

`start(...)` returns an async context manager; I/O begins **only on entry**, with explicit allowed read-only data access. Paper has a separate simulated ledger and never accesses broker order endpoints. No `await paper.start(...)` / `paper.run(...)` competing public spellings. Provider rights, warmup, staleness, source reconciliation and modeled execution gates are required.

### 21. One strategy for replay and streaming (E6.7c/E7 target)

```python
class Momentum(Strategy):
    def setup(self):
        self.require_bars("1m", warmup=21)

    def on_bar(self, ctx):
        closes = ctx.bars("1m").close
        if indicators.cross_above(closes, indicators.sma(closes, 20)):
            return ctx.long(target="5%")
        return ctx.no_action()

strategy = Momentum()
historical = Engine().backtest(
    data=validated_dataset, strategy=strategy, capital="100000 USD"
)
# E7, a fresh stateful instance with the same definition:
async with Engine().session(symbols=["AAPL"], strategy=Momentum()) as session:
    await session.warmup(validated_history)
    # caller then ingests normalized observations
```

Actual replay/streaming parity is conditional on identical canonical events, available/received timestamps, strategy state and applicable execution policies. Live fills cannot be inferred from OHLCV or these examples.

### 22. Recovery, blockers and closure (E7 target)

```python
async with engine.session(
    symbols=["AAPL"],
    strategy=my_strategy,
    journal=my_session_journal,
) as session:
    await session.warmup(validated_history)
    async for event in normalized_market_stream:
        decision = await session.ingest(event)
        if decision.blockers:
            print(decision.blockers)
            break
    print(session.status)
```

Closing joins owned tasks. Recovery is separately operator-reviewed with verified journal/cursor, missing-data backfill, strategy state and broker-authoritative snapshot; a reconnect alone does not clear HALT. Exact restart API to be specified at E6.7a.

### 23. Future authorized Live is a *different capability* (E8 only)

```python
# DESIGN SKETCH ONLY — no actual live route or trading authority exists.
# async with engine.live.start(spec=approved_live_spec,
#                              authorization=approved_authorization) as session:
#     async for event in session.events():
#         print(event.status)
```

The lifecycle verb `start()` matches Paper because both are continuous; live trading needs separately approved broker adapter, authentication, pre-trade controls, risk reconciliation, idempotency, operator kill switch and independent E8 GO. Market-data permission does not imply broker-order permission. Never ship a fake enabled Live endpoint.

## Contract enforcement and change process

- This document specifies **design targets**, not runnable code. Existing E0–E6 implementations are unchanged. Phases and unsupported/future paths are explicitly stated for each example.
- E6.7a creates an explicit [old→new mapping and contract matrix](E6_7_API_CONTRACT_MATRIX.md), verifies real core capabilities, defines typed signatures/defaults, error/result contracts, fixture ownership and snapshots; no undocumented changes to established legacy Python/CLI contracts.
- E6.7b–e implements and verifies only accepted offline interfaces. E7 owns decision-session lifecycle, managed Paper, streaming gap recovery and subscription work. E8 separately authorizes Live.
- Any future change to the **revised** public surface or mandatory safety behavior requires user review and coordinated ADR, Issue #59, spec, examples, matrix, roadmap and contract tests. The 2026-11-22 revision supersedes the earlier 2026-11-20 **unimplemented** names, not underlying engine compatibility.
