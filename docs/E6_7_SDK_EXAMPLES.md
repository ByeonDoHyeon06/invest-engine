# E6.7 — Unified SDK API examples (normative design targets)

Status: agreed design direction, not executable SDK code. [Issue #59](https://github.com/ByeonDoHyeon06/invest-engine/issues/59) / [specification](E6_7_UNIFIED_SDK.md) / [ADR-0034](adr/0034-unified-sdk.md). Examples define the intended developer experience, not current support, actual profits or authority to trade. E6.7a must inventory existing capabilities and turn the applicable examples into executable contract tests, using synthetic or permitted local fixtures. Future-only examples stay gated. The canonical constructor is **Engine()**, not Engine.offline(), Engine.online(), Engine.research() or a mandatory mode argument.

## 01 — Zero-configuration engine construction (E6.7b)

```python
from invest_engine import Engine

engine = Engine()
```

Construction and package import never call providers, start tasks, download data, open accounts, resolve credentials, or submit orders. The instance owns explicit configuration and service namespaces, not a permanently selected execution mode. A named, documented research profile supplies safe backtest defaults; defaults are expanded into the prepared spec and manifest. No global singleton or ambient credentials.

## 02 — Basic offline backtest (E6.7b)

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

A dataset reference identifies an already prepared local manifest; missing data fails explicitly, rather than downloading implicitly. Capital is an explicit currency-bearing decimal string; the SDK parses it into existing typed Money. No float money. The result includes status, evidence, blockers and effective configuration. No strategy is asserted profitable.

## 03 — Explicit defaults and adjustable policy (E6.7b/c)

```python
from invest_engine import Engine, profiles, strategies, risk, execution

engine = Engine(profile=profiles.research_v1())
result = engine.backtest(
    data="datasets/AAPL/manifest.json",
    strategy=strategies.orb(opening_range="30m", volume_multiplier="2.0"),
    capital="100000 USD",
    risk=risk.Policy(max_position="5%", max_daily_loss="2%"),
    execution=execution.Simulation(
        commission_bps=10, spread_bps=5, impact_bps=5,
        max_participation="5%",
    ),
)
print(result.config)
print(result.manifest)
```

Illustrative values are modeled research settings, not broker fees. Overrides compose into one immutable typed spec; contradictory settings and unsupported combinations fail before replay. A profile never disables mandatory constraints. Engine defaults do not create an account or place an order.

## 04 — Prepare, inspect, execute (E6.7b/c)

```python
from invest_engine import Engine, BacktestSpec, strategies

engine = Engine()
spec = BacktestSpec(
    data="datasets/AAPL/manifest.json",
    strategy=strategies.orb(opening_range="30m"),
    capital="100000 USD",
)
prepared = engine.prepare(spec)
print(prepared.effective_config)
print(prepared.blockers)
result = engine.run(prepared)
```

prepare normalizes, binds hashes and validates; it never executes the strategy or orders. run refuses invalid, stale or tampered plans. The convenience backtest call delegates to exactly that prepare/run path. A blocked result is distinct from a successful result with no trades.

## 05 — Explicit provider configuration and download (E6.7c; provider adapter subject to rights and implementation)

```python
from invest_engine import Engine, providers, strategies

engine = Engine(data=providers.Alpaca(credentials="alpaca-market-data"))
dataset = engine.data.fetch(
    symbols=["AAPL", "MSFT"],
    start="2022-10-01",
    end="2022-10-31",
    interval="1m",
    destination="datasets/us-oct-2022",
)
result = engine.backtest(
    data=dataset,
    strategy=strategies.orb(),
    capital="100000 USD",
)
```

credentials is a secret-manager reference, not a key. Provider construction is inert, and only the explicit data.fetch call performs network I/O. Download must verify rights, calendar, identity, source/price basis, version, checksums and gaps; warmup requirements must be covered explicitly by the declared dataset or reported as a blocker. No raw output without storage rights; no provider order access. Having an online data provider does not enable Live or even Paper.

## 06 — Local import and native resolution (E6.7c)

```python
from invest_engine import Engine, data

engine = Engine()
dataset = engine.data.load("datasets/us/manifest.json")
bars = engine.data.resample(dataset, interval="5m")
quality = engine.data.inspect(bars)
print(quality.blockers)
```

Resample only supported compatible native data to coarser bars. Manifest, point-in-time availability, calendar and volume semantics preserved. No bar-to-tick reconstruction. Custom event inputs or registered manifest references follow the same validation contract.

## 07 — Custom strategy (E6.7c)

```python
from invest_engine import Engine, Strategy, indicators

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

engine = Engine()
result = engine.backtest(
    data="datasets/AAPL/manifest.json",
    strategy=MovingAverageCross(),
    capital="100000 USD",
)
```

The high-level Strategy is an adapter to the existing manifest/read-only context/signal/snapshot protocol; existing Strategy implementations remain supported. Data requirements include enough previous observations for crossing, no future bars, and explicit interval/session. Missing values produce abstention. The convenience layer converts intentions to canonical StrategySignal; Risk/Allocator/Execution retain sole authority. Stateful strategies require deterministic snapshot/restore and stable identity; engine should obtain a fresh instance or explicit instance ownership on independent runs. Arbitrary Python plugins are trusted code, not sandboxed.

## 08 — Advanced typed custom policies and dataset (E6.7c)

```python
from invest_engine import Engine, BacktestSpec, profiles
from invest_engine.sdk import data, policies

engine = Engine(profile=profiles.research_v1())
spec = BacktestSpec(
    data=data.from_manifest("datasets/us-2022/manifest.json"),
    strategy=my_strategy,
    capital=opening_cash,
    calendar=exchange_calendar,
    risk=custom_risk,
    execution=policies.execution(fill=fill_policy, fees=fee_policy),
    evaluation=evaluation_window,
    reporting=reporting_policy,
)
result = engine.run(engine.prepare(spec))
```

Named local objects are existing typed components supplied by the application, not magical declarations. Every currently supported underlying policy must map losslessly or remain accessible via a documented advanced entry point. Unsupported combinations remain errors. A replacement fee/fill/risk policy does not replace the engine's mandatory safety constraints.

## 09 — Multi-currency research (E6.7c; only supported combinations)

```python
from invest_engine import Engine, Money, BacktestSpec

engine = Engine()
spec = BacktestSpec(
    data=validated_dataset,
    strategy=my_strategy,
    capital=[Money("100000", "USD"), Money("1000000", "KRW")],
    reporting=fx_reporting_policy,
)
result = engine.run(engine.prepare(spec))
print(result.pnl)
```

Separate currencies remain authoritative for amounts. An optional FX reporting policy uses explicit as-of observations; reporting conversion is not actual FX execution or purchasing power. Unsupported cross-market replay configurations are rejected rather than silently approximated.

## 10 — Multiple strategies and shared risk (target extension, subject to parity and allocation support)

```python
from invest_engine import Engine, strategies, allocation

engine = Engine()
ensemble = strategies.Ensemble(
    strategies=[strategies.orb(), MovingAverageCross()],
    allocation=allocation.Weighted(
        weights=["0.6", "0.4"],
        max_total_exposure="20%",
    ),
)
result = engine.backtest(
    data="datasets/us-market/manifest.json",
    strategy=ensemble,
    capital="100000 USD",
)
print(result.strategies)
print(result.portfolio.exposure)
```

One simulated account and central risk authority, not duplicated capital. Strategy-level attribution is evidence and never creates separate real balances. Exact support for simultaneous multi-instrument, weighted allocation and attribution must be established; if absent, mark as future extension, not pretend the facade implements it.

## 11 — Research workflow (E6.7d)

```python
from invest_engine import Engine, research, strategies

engine = Engine()
study = engine.research.create(
    strategy=strategies.ORB,
    parameters={
        "opening_range": ["5m", "15m", "30m"],
        "volume_multiplier": ["1.5", "2.0", "2.5"],
    },
    data="datasets/us-market/manifest.json",
    capital="100000 USD",
    validation=research.WalkForward(
        train="12M", validation="3M", step="3M",
    ),
    costs=research.CostScenarios(base=True, stress=True),
    max_candidates=9,
)
result = study.run()
print(result.review)
print(result.best_candidate)
result.export("artifacts/research")
```

Engine.research is an instance service, never a class factory. create establishes a registered immutable spec; run uses existing journal reservation and candidate evaluation. Example durations and grid are subject to existing planner limits and timing evidence. Preserve controls, budget, time split, purge/embargo and evidence requirements. An unverified result or no eligible candidate does not return a promoted winner. Holdout execution and operation remain separately gated.

## 12 — Reports and failure handling (E6.7b/d)

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
    print(result.status)
    print(result.evidence)
    print(result.blockers)
    if result.metrics is not None:
        print(result.metrics.max_drawdown)
    result.export("artifacts/audit")
```

Contract/configuration errors raise typed exceptions with stable reason codes; a started run that cannot produce valid evidence returns an explicit blocked/failed state where a result can be safely persisted. No fabricated PnL, no ambiguous empty success, no raw credential/market-data leakage. Typed result handles decisions, orders, fills, equity, per-currency PnL and simulated holdings, with streaming/iterators for large outputs. Metrics unavailable without valid data are None, not zero. Export is explicit and permission-aware.

## 13 — Shared CLI contract (E6.7d)

```bash
invest-engine run --config configs/backtest.json
invest-engine inspect --run-id research-001
invest-engine explain --run-id research-001 --decision-id decision-001
```

Proposed CLI commands and Python facade share the same versioned spec and orchestration; no separate execution semantics. Existing backtest/import-csv/stress/replay-synthetic commands and e5-research-v1 configuration remain compatible. Example run IDs are placeholders, not existing records.

## 14 — Application integration (E6.7d example, surrounding service not part of SDK)

```python
from fastapi import FastAPI
from invest_engine import Engine, strategies

app = FastAPI()

@app.post("/backtest")
def backtest(dataset_id: str, capital: str):
    engine = Engine()
    data = engine.data.load_registered(dataset_id)
    result = engine.backtest(
        data=data,
        strategy=strategies.orb(),
        capital=capital,
    )
    return result.summary.to_dict()
```

Registered dataset resolution must be application-controlled; never accept unchecked arbitrary user filesystem paths. Real deployment needs authenticated tenant/data permissions, bounded job queue, cancellation, quotas and audit. Use isolated run context, not a shared mutable account. This is an integration example, not a deployed service.

## 15 — Decision-only evaluation with broker-provided assets (future; distinct from research)

```python
from invest_engine import Engine, strategies

engine = Engine()
decision = engine.evaluate(
    market_data=market_snapshot,
    portfolio=broker_account_snapshot,
    strategy=strategies.orb(),
)
print(decision.action)
print(decision.reason_codes)
print(decision.proposed_orders)
```

The caller supplies a timestamped, identified broker-authoritative snapshot plus market data; the SDK does not persist a second authoritative live asset database or fetch the account implicitly. Verify freshness, state/version, availability, currency, open orders and reconciliation; reject missing/stale information. A decision is a proposal with submitted=false, never an actual broker order. No broker adapter implemented or authorized by this example. E6.7a determines exact phase and supported decision-only inputs.

## 16 — Paper and Live are capabilities, not constructor modes (future E7/E8)

```python
from invest_engine import Engine

engine = Engine()

# E7 only, after explicit paper capability/configuration:
# await engine.paper.run(spec=paper_spec)

# E8 only, after independent approval and capability attachment:
# await engine.live.run(spec=live_spec, authorization=live_authorization)
```

These are interface placements, not runnable Live instructions. Engine() never has live authority. Paper uses isolated simulated assets; actual broker orders remain zero. Live capability requires separately approved adapters, account authorization, risk, reconciliation, kill switch and operational gates, not merely calling a method or passing a bool/token. Until authorized, no callable live order route is shipped or available. Online market-data transport is orthogonal to execution authority.

## 17 — Independent modules (E6.7c; existing or planned implementations inventoried)

```python
from invest_engine.indicators import sma, atr
from invest_engine import Engine

average = sma(prices, period=20)
volatility = atr(bars, period=14)

engine = Engine()
```

Pure helpers remain independently usable without instantiating the Engine. Do not flatten every internal type into the root or duplicate existing domain models. Unsupported indicators or adapters belong to explicit extension tasks.

## 18 — Explicit advanced extension registration (E6.7c)

```python
from invest_engine import Engine

engine = Engine(
    data=my_data_provider,
    calendar=my_exchange_calendar,
    artifact_store=my_artifact_store,
)
```

These are trusted typed plugin implementations. Construction is inert; the SDK does not call an injected provider until an explicit operation. Stable plugin identity/version and configuration enter the run manifest. No unrestricted kwargs dictionary or silent fallback, no bypass of validation/risk. Existing low-level paths remain usable.

## 19 — Caller-fed real-time decision session (E7 target; no actual orders)

```python
from invest_engine import Engine, strategies, market

engine = Engine()
async with engine.evaluate.session(
    symbols=["AAPL"],
    strategy=strategies.orb(),
) as session:
    await session.warmup(validated_history)
    async for tick in my_websocket:
        result = await session.ingest(
            market.Trade(
                symbol=tick.symbol,
                price=tick.price,            # Decimal or decimal string
                quantity=tick.quantity,
                timestamp=tick.event_time,  # timezone-aware exchange event time
                received_at=tick.received_at,
                event_id=tick.event_id,
                source=tick.source,
            ),
            portfolio=broker.account_snapshot,
        )
        if result.proposed_orders:
            print(result.proposed_orders)
```

Application-provided websocket, historical dataset and broker snapshot are not SDK-owned assets or credentials. The symbol is resolved against a declared market/instrument universe; ambiguous identity or insufficient source/time evidence blocks action. Ingest returns a typed observation/decision outcome even when there is no new order; no network or order routing by this session. Snapshot must be timestamped, versioned, trusted by application policy and reconciled. Warmup uses read-only observations, not simulated orders. See [streaming contract](E6_7_STREAMING_CONTRACT.md).

## 20 — Managed market-data streaming with simulated execution (E7 target)

```python
from invest_engine import Engine, providers, strategies

engine = Engine()
session = await engine.paper.start(
    data=providers.Alpaca(credentials="alpaca-market-data"),
    symbols=["AAPL", "NVDA", "TSLA"],
    strategy=strategies.orb(),
    capital="100000 USD",
)
async with session:
    async for event in session.events():
        print(event)
```

Explicit start performs permitted read-only market-data I/O after validation and initialization. The async context closes the session and joins tasks; cancellation, errors and bounded output delivery are explicit. Paper cash and fills are isolated simulations. No brokerage trading endpoints or actual order submissions. Source, warmup/backfill, rights, clock, fill and risk policies must be resolved before trading; no implicit fallback to a different feed.

## 21 — Custom strategy, same contract in replay and streaming (E6.7c design / E7 streaming)

```python
from invest_engine import Strategy, indicators

class MovingAverageCross(Strategy):
    def setup(self):
        self.require_bars("1m", warmup=21)

    def on_bar(self, ctx):
        close = ctx.bars("1m").close
        average = indicators.sma(close, 20)
        if indicators.cross_above(close, average):
            return ctx.long(target="5%", stop_loss="1%")
        if indicators.cross_below(close, average):
            return ctx.exit()
        return ctx.no_action()
```

One strategy implementation, deterministic state and shared risk boundary regardless of input transport. Current core's on_event protocol remains the underlying contract. Bar callbacks are only for finalized declared bars; optional tick, quote, order-book and timer callbacks are capability-specific proposals, never implicit subscriptions. A 21-bar warmup supplies two valid 20-period SMA points. Actual historical and streaming fills need not match unless the identical normalized tape and execution/account policies are used.

## 22 — External normalized events and snapshot updates (E7 target)

```python
async with engine.evaluate.session(
    symbols=["AAPL"],
    strategy=my_strategy,
    calendar=my_exchange_calendar,
) as session:
    await session.warmup(validated_history)
    await session.update_portfolio(verified_account_snapshot)
    async for event in normalized_event_stream:
        result = await session.ingest(event)
        if result.blockers:
            print(result.blockers)
        if result.proposed_orders:
            print(result.proposed_orders)
```

Existing typed EventEnvelope input remains an advanced path; the SDK must not invent a source sequence or publication timestamp. An attached snapshot is not silently reused beyond freshness/causal/reconciliation constraints. Portfolio refresh and market input serialize through the same session writer. No actual submission, no auto-repeat of an old proposal, no mutable broker ledger.

## 23 — Stream recovery and shutdown (E7 target)

```python
async with engine.evaluate.session(
    symbols=["AAPL"],
    strategy=my_strategy,
    journal=my_session_journal,
) as session:
    await session.warmup(validated_history)
    async for event in normalized_event_stream:
        result = await session.ingest(event)
        if result.blockers:
            print(result.blockers)
            break
    print(session.status)
```

The context drains or explicitly cancels pending work and closes the session. A restart requires verified source cursor/history, journal/state restoration, refreshed authoritative account snapshot and operator-reviewed resume where required; no automatic replay of prior proposals as orders. Gap or conflict cannot be cleared by merely reconnecting. The precise recovery interface remains an E6.7a signature-design item.

## Contract enforcement and change process

Examples 01–04, 06–09, 11–13, 17–18 are implementation targets subject to documented supported combinations and capabilities. Example 05 requires provider adapter and rights, 10 requires actual allocation support, 14 is external integration, 15 is decision-only future scope, 16 belongs to E7/E8. Examples 19–23 extend the agreed API design to streaming and caller-driven observation; E6.7a defines typed lifecycle and parity fixtures, E7 implements only after its gate. See [streaming contract](E6_7_STREAMING_CONTRACT.md). These flags prevent planning examples from being presented as available features. Maintain a test manifest linking each example to phase, fixture, expected API signatures and evidence. E6.7a implements signature snapshots and executable synthetic golden examples; E6.7b–e enable tests for each completed capability. Use fixed versions/hashes for deterministic parity, no network credentials in CI tests. The SDK contract and examples are normative DX targets; changes to Engine() constructor semantics, top-level call model, mode separation, names in the frozen examples, defaults, safety or compatibility require a documented ADR amendment/replacement, explicit user review/approval and coordinated issue/roadmap/spec/example/test updates before implementation. If an example is impractical or unsupported, report the conflict and propose a change rather than silently rewrite it. Do not claim planned examples already run. Existing #57 and E5/E6 gates are unchanged.
