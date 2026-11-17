# ADR-0012: Internal provenance audit and repeatable synthetic stress

- Date: 2026-11-17
- Status: Accepted for offline E5.4 research; **not proof of verified live-market data**

## Context
E5 historical backtest supports limit and opt-in protective fill assumptions. Reproducible run hashes alone do not prove that input data is accurate or legally reusable. A model may appear profitable because of narrow participation, unverified fee assumptions or missing historical bars. Results need defensible audit evidence before adding automated candidate research in E6.

## Decision
1. Record missing bars grouped by exact instrument/timeframe/session, without inventing price data.
2. Include a data audit and file-level SHA256 for output reports, plus an installed-Python-source tree SHA. Do not confuse these hashes with independently attested producer identity or verified Git provenance.
3. Compare frozen dataset/strategy/risk with four deterministic cost/participation scenarios using the *same* offline RunRequest. Isolate intermediate artifacts and preserve original baseline inputs/results.
4. Explicitly label market-specific fees/taxes/FX, corporate-action adjustments and historical symbol universe as UNVERIFIED unless independently validated.
5. Keep currencies separate, Live unavailable, and E5 acceptance gate OPEN until remaining data/FX/quote modeling requirements are resolved or formally rescoped.

## Alternatives
- Backtest once with one fee/slippage value and call it reliable (reject: hides assumptions).
- Convert synthetic input metadata into a release-approved truth value (reject: unsupported claims).
- Infer missing bar prices/corporate actions from OHLCV (reject: lookahead/false data risk).
- Fetch current broker fee schedules at runtime for historical fills (reject: not as-of reliable).

## Consequences
The run output adds deterministic `audit.json`, actual code-tree fingerprint and file hashes. Stress runs are slower because each scenario replays the full dataset rather than approximating impact from the original P&L. This is deliberate: changed fees or liquidity may change which orders execute.

## Revisit
Use point-in-time licensed datasets with corporate actions and verified instrument universes; add Tick/Quote models and PIT FX to validate real-market cost calibration. E6 should evaluate OOS/walk-forward and holdout without reusing the final test period for tuning.
