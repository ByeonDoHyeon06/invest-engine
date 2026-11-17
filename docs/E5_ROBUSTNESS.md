# E5.4 — Data Audit, Integrity & Cost Stress

**Status:** implemented for synthetic/offline historical research (2026-11-17). **No Live API or real-money trading.**  
**Related:** [E5_BACKTEST](E5_BACKTEST.md), [E5_EXPERIMENT](E5_EXPERIMENT.md), [E5_PROTECTION](E5_PROTECTION.md), [ADR-0012](adr/0012-audit-stress.md).

## 1. What changed

- `research.audit.inspect_dataset(...)` computes bar coverage by `InstrumentId + interval + session`. It records intra-session missing intervals and partial sessions; it does **not** create synthetic candles or pretend missing bars had zero price change.
- `research.audit.source_tree_sha256()` hashes actually installed `invest_engine` Python sources. It is **not** a verified Git commit, publisher signature, package SBOM or guarantee that `code_sha` supplied by a user matches Git.
- Offline `run_experiment(...)` now writes `audit.json` and SHA-256 for `report.json`, `decisions.jsonl`, `fills.jsonl`, `equity.jsonl`, `audit.json` inside `manifest.json`. `verify_exported_artifacts(dir)` checks accidental corruption/tampering after export; a user who can alter manifest and files can generate matching hashes, so this is not a signed attestment.
- New `stress` CLI runs the original input dataset, strategy, initial cash and risk limits repeatedly, modifying **only declared synthetic execution assumptions**. Intermediate experiments use an isolated temporary directory; they never overwrite the original dataset or its baseline results. Output JSON has case-by-case `run_sha256`, currency-specific P&L/drawdown, fill counts and explicit assumption values.

## 2. Example workflow

```bash
invest-engine backtest --config ./research/run.json
invest-engine stress --config ./research/run.json --output ./research/stress.json
```

The `run.json` is the E5.2 `e5-research-v1` specification. `stress` introduces no credentials, network requests, providers, prediction models or Live mode.

The stress case table is deliberately **hypothetical, not a calibration**:

| Scenario | Variation from base configuration |
| --- | --- |
| `baseline` | Identical fee, tax, spread, impact, volume participation and protection settings |
| `higher_costs` | +0.05% synthetic fill fee, +10 bps spread buffer and +10 bps impact buffer |
| `lower_liquidity` | 50% of original bar-volume participation limit |
| `joint_adverse` | +0.10% fee and sell tax, +20 bps spread & impact, 25% volume participation, optional +20 bps protective stop adverse execution |

Additional fees are **deltas**, not official Korean/US brokerage rates or accurate transaction taxes. The interpretation of `spread_bps`/`impact_bps` within this bar-only engine is stricter limit penetration; it **does not directly deduct those bps from completed limit prices**. Fewer or more partial fills can change output unpredictably, so do not assume P&L or drawdown is monotonic with higher cost assumptions.

## 3. Research audit status

`audit.json` includes `event_count`, `bar_count`, `coverage`, `gap_count`, `warnings`, and `release_data_verified: false`. This flag is **always false** until data provider/contract, as-of issuer/corporate action, historical universe, market calendar and actual brokerage fee schedules are separately validated through independent evidence.

Audit warnings include:
- `SOURCE_LICENSE_NOT_INDEPENDENTLY_VERIFIED`
- `CORPORATE_ACTIONS_AND_PRICE_ADJUSTMENT_UNVERIFIED`
- `POINT_IN_TIME_UNIVERSE_NOT_VERIFIED`
- `MARKET_SPECIFIC_FEES_TAX_AND_FX_NOT_VERIFIED`
- `CALENDAR_SOURCE_NOT_INDEPENDENTLY_VERIFIED`
- `BAR_GAPS_DETECTED` / `PARTIAL_SESSION_COVERAGE` where applicable

Source/license/adjustment/FX claims in JSON input are **self-declarations**. This audit validates only internal consistency; it does not contact a market data provider or certify legal rights.

## 4. Determinism and safety properties

1. Baseline stress run has same `run_sha256` as an independent plain backtest with the same config and market data, except for external effects not present in this offline engine.
2. Scenario runs use the *same file checksum* and strategy artifact/config (except allowed cost/volume parameters); no automatic data download or regeneration.
3. Original config/dataset and baseline report cannot be overwritten by the stress exporter.
4. The result hash and manifest/artifact hashes allow replay/verification. They are not authenticated signatures.
5. Unverified FX never becomes an implicit conversion. Each currency has its own P&L/drawdown.
6. NoTrade strategies produce an `INCONCLUSIVE_NO_TRADES` result, not a claim that market sensitivity has been demonstrated.
7. E5.3 stop/gap ambiguity remains model-dependent; no OHLCV test can recreate true broker queue priority.

## 5. E5 gate audit — completed vs still open

| Requirement | Status / evidence |
| --- | --- |
| Deterministic E0→E4→E3 backtest replay and next-bar execution | Implemented E5.1, synthetic tests |
| CLI and input/output manifest | Implemented E5.2, synthetic tests |
| Conservative OHLCV stop/target/gap handling | Implemented E5.3, opt-in, synthetic tests |
| Bar coverage + data provenance warning, artifact checksums | Implemented E5.4, synthetic tests |
| Repeatable fee/spread/liquidity/partial fill stress scenarios | Implemented E5.4, synthetic tests |
| Verified real KR/US fee & tax rules, effective-dated corporate actions, historical delistings, data vintage | **NOT VERIFIED** — external data/contract required |
| FX valuation with verified PIT FX rate series for currency aggregation | **NOT IMPLEMENTED** — currency-separated reporting only |
| Quote/tick-assisted fill modeling | **NOT IMPLEMENTED** — documented interface remains later work |
| Statistical multi-period walk-forward and untouched test data | **E6** — NOT IMPLEMENTED |
| Forward Paper and realistic live vs model fill comparison | **E7** — NOT IMPLEMENTED |

**E5 issue should remain open** until its explicitly required data/calendar/FX-cost contracts are either implemented and tested or scope is amended by an ADR. This is a research-engine correctness milestone, **not evidence that a strategy can make money**. E8 real orders remain DISABLED.

## 6. Regression test policy

- Test base fixture, data-gap detection, tampered artifacts, unchanged input, repeated stress output hash, CLI export and no-trade inconclusiveness.
- Test at least one **real strategy signal generated from synthetic events** so cost assumptions actually change executed fills/P&L.
- Test invalid scenario/Live input rejection and accidental overwrite prevention.
- CI must pass Python 3.12 + 3.13, Ruff, mypy, pytest and secret guard.
