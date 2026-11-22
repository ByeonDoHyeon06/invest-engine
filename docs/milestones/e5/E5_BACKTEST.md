# E5 — Historical backtest runner (E5.1–E5.3)

**Status:** Initial implementation, synthetic/offline only. No brokerage access or live orders.

## Inputs

- Finite immutable sequence of historical `EventEnvelope[MarketPayload]`, strictly contiguous journal ordinals, point-in-time `available_at`/`received_at`, finalized bars, source provenance supplied by caller.
- `StaticSessionCalendar` or another authoritative session calendar. Calendar version must be pinned by the research operator. Holidays/DST/session constraints are checked before generating an execution.
- An independent, freshly instantiated strategy for every run, declared `StrategyManifest` / `DataRequirement` (any interval). E4 `StrategyRunner` + `FeatureRegistry` are reused.
- E3 `TradingConfig` including per-currency synthetic fee/tax/rounding rules, initial settled cash, explicit `RiskLimits`. `require_monitoring=True` is **not** yet supported by the replay runner: it rejects this input, rather than pretending to provide real account marks.
- `BarFillPolicy`: participation cap, spread/impact assumption in basis points, fixed version. `BacktestSettings`: run version, mark freshness, code SHA and data provenance labels. The default `UNPINNED` code SHA must not be used for released research conclusions.

## Data flow

    historical market events (E0/E1 validated)
        → E2 EventRuntime (ordinal/dedup/quality/timing)
        → E5 fills for orders already active at bar START
        → E3 TradingRuntime (limits, reserves, fills, balances)
        → E4 StrategyRunner and Feature calculations
        → signals → allocator → E3 OrderIntent/risk check
        → E3 simulated ACCEPTED (no real broker)
        → next eligible closed bar and above pipeline
        → immutable BacktestReport

Events are processed at the **observation time**, not retroactively at each intrabar price. A signal generated at bar close is never filled using that same bar. The later bar must begin at/after the order submission time. The fill candidate is booked at the later bar's observed/available time (no backdated fills).

## Fill model limitations

- E5.1 supports **finalized time-bar LIMIT orders only**. The bar's low must **strictly penetrate below** BUY limit minus `(spread_bps+impact_bps)` buffer. SELL requires high to exceed limit plus buffer. A price touch alone is not considered a fill.
- Price is the order's **limit** (never a better execution price invented from OHLC); the spread/impact parameter increases the amount of required price penetration and can turn a candidate into no fill. This is a deliberately simplified fill probability proxy, **not a market microstructure or slippage reconstruction**.
- Max participation is a fraction of historical bar volume, rounded down to the instrument lot size. Volume availability is shared among orders in deterministic order. Partial fills are allowed, fees/taxes are charged by E3.
- Stops from E4 are **risk proposals** by default. E5.3 adds an **opt-in offline-only protection hypothesis**, described in [E5_PROTECTION.md](E5_PROTECTION.md), for stop-first collision handling, adverse gaps, volume-limited partial exits, and no same-entry-bar protection. No actual broker stop is submitted. A strategy's EXIT still produces a later SELL limit proposal; an unresolvable same-bar conflict with protection errors rather than inventing an intrabar sequence.
- DAY limit orders are canceled on the final bar of a declared session; no instant fills inferred from market status/zero-volume bars. If a dataset ends during a session, open reservations remain and must be interpreted as incomplete research.
- Tick/quote-assisted execution, dynamic transaction-cost model, exchange-realistic partial queue modeling, real-data license validation and settlement-aware forward simulation remain separate E5.2+ tasks.

## Outputs

`HistoricalBacktest.run()` returns immutable `BacktestReport`:
- `dataset_sha256`, `config_sha256`, `state_digest`, `run_sha256`, market event count.
- Per-currency initial/evaluated final cash+positions, net P&L, drawdown, fees, synthetic taxes, turnover, per-exit-fill expectancy and profit factor (`null` if undefined).
- Decision trace: market event ID → signal ID → proposed intent ID/risk decision/reasons → fill event ID, plus equity snapshots and fill details.
- `export(path)` writes deterministic `report.json`, `decisions.jsonl`, `equity.jsonl`, `fills.jsonl` to caller-controlled storage.
- Multi-currency performance is **never summed without a qualified as-of FX series**. If a held position lacks a fresh final mark, the runner refuses to produce a misleading final total.

## Validation performed/needed

- Synthetic no-trade, rejection, no-look-ahead, same-bar no-fill, strictly penetrated limit, volume cap + partial fills, fee and spread sensitivity, exit after later bar, deterministic rerun.
- Must pass full E0~E4 regression tests on Python 3.12/3.13 + Ruff/mypy/secrets CI.
- E5.2: CLI RunRequest/RunResult with code/calendar/fill/dataset/version identifiers and deterministic report artifacts (implemented; see [E5_EXPERIMENT.md](E5_EXPERIMENT.md)).
- E5.3: opt-in synthetic protective stop/target ambiguity, adverse gaps, volume caps, reason tracing and repeatability (see [E5_PROTECTION.md](E5_PROTECTION.md)).
- Still needed before final E5 sign-off: wider cross-market cost stress, realistic historical data/fee/FX/corporate-action provenance, tick/quote interfaces and open-order conflict-model improvements.

**E5 is not complete at E5.1.** Neither positive PnL nor backtest hash is evidence of live profitability.
