# E5.13 — Preregistered provisional market study

**Scope:** Historical-data diagnostic, NOT a provider release approval or trading recommendation. No live connectivity, credentials, paid data, or raw-data redistribution.

## Design fixed before execution

- Daily panel: AAPL, MSFT, NVDA, TSLA, GOOG, META; all calendar months of 2025, fresh $100,000 cash per run, 5% maximum target, seven named rules, three cost assumptions, 1,512 planned independent trials. No training/optimization or warm-up outside each month. Nominal daily interval and source-reported dates. Unknown corporate action and adjustment/vintage provenance; returns are diagnostic only, not total returns. No forced close of open positions. Public Pubmarks source pinned to e31dd3817bb2eccaa10d3b01c6f2efdbca5d3abf.
- Minute panel: HistoricalData.net public 2022H2 stock sample (https://historicaldata.net/stocks.html). TSLA, SPY, KO, TWTR × September, October, November 2022 with exactly 20 preceding exchange sessions. Strict complete-minute preflight and daily issuer action check; no missing prices or dates invented. Reject incomplete/action windows. All eligible windows run NoTrade, entry-hold and ORB, plus stressed ORB. Use raw price/share volume, regular session ET, receipt at bar end explicitly assumed. No invented actual PIT evidence; bypass strict CLI only for clearly labeled provisional programmatic study. No raw files in artifacts, logs or repo.
- Cost scenarios: low 0.05% fee/5 bp penetration buffer, base 0.10%/10 bp, stress 0.25%/40 bp; 5% volume participation, tick $0.01, lot one share, tax zero placeholder. Actual costs and exchange ticks not independently verified; sub-cent marks may reject proposed orders. ORB is a long-entry signal hypothesis and not a session-flat round-trip strategy. Full-period return uses marked open holdings and costs; fill count not completed trade count.
- Every failure/blocked window is reported. No success inferred from CI exit status; inspect per-study status/results. External vintage, coverage, legal/license requirements and costs need independent verification. E5 Issue #6 remains open. No E6 promotion based on this study alone.

## First-run finding and correction

The first diagnostic completed 1,445/1,512 daily trials; 67 failed with `intent and allocation plan mismatch`. Root cause: a positive long target may generate a SELL trim after price appreciation, but the attribution ticket previously allowed SELL only for a zero target. E5.13 accepts the valid reduction and attributes it to existing virtual holdings; tests cover account/virtual parity. The same fixed study is rerun without tuning strategy parameters. Correct SPY venue/class metadata (NYSE Arca ETF). The first-run partial strategy rankings are not used as final evidence.

## Completed provisional results (2026-11-19)

[Study workflow 44494674899](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44494674899); [core CI 44494674900](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44494674900): 301 passed per Python version. PR #38 merged at `d2550bb98e7a197975da5799a0044dca35404878`.

Daily: 1,512/1,512 cases completed after the attribution correction; 3,732 simulated fills, no exceptions. The 21 strategy/cost aggregate summaries and all source hashes match the corrected pre-performance-change study. All daily active rules had negative mean monthly net returns in the base scenario; initial-entry hold +0.068620%, no-trade 0%. Independent monthly accounts, not an annual compound return.

| Window | Evaluation minutes | Hold return % (fills) | ORB base % (fills) | ORB stress % (fills) | Base MDD % |
|---|---:|---:|---:|---:|---:|
| TSLA Oct 2022 | 8190 | 0 (0) | +0.25317 (5) | +0.24376 (4) | 0.682875 |
| TSLA Nov 2022 | 8010 | 0 (0) | -0.48903 (4) | -0.49765 (4) | 1.362690 |
| SPY Nov 2022 | 8010 | +0.20544 (1) | +0.28974 (2) | +0.27706 (2) | 0.230939 |

NoTrade flat in all three windows; all four arms in each eligible window completed. Nine windows blocked: six action intervals, two missing-session windows after TWTR ceased trading, and two missing bars in one TWTR September window. The three windows include 47,610 window-bars (24,210 evaluation) with overlap; 190,440 visits across 12 arms. Base ORB 11 simulated fills, only two sells across these arms; no standing protection enabled, no daily liquidation. The TSLA entry-hold comparator did not fill in either window: do not interpret zero as buy-and-hold market return. Aggregate net PnL includes unrealized marks.

Performance: exact equality of all 16 common non-hash result fields for all eight matched SPY/TSLA November arms vs study 44493413536. Full run hashes include code revision and thus differ. Base ORB observed old inter-log durations 247.254/219.803 s vs new measured 67.901/63.298 s; stress 265.153/223.262 s vs 67.885/62.929 s. Approximate 3.5–3.9x, not controlled hardware profiling. Previous TSLA October job canceled; no comparable timing. Prefix reuse preserves reference EMA/ATR formulas and retained-bar index semantics with fallback for revised/truncated inputs; exact reference tests pass.

**Gate remains OPEN:** supplier rights, market coverage, actual historical receipt/vintage, ticks and transaction-cost schedule not independently certified. No fabricated bars, no performance recommendation, no live orders. Next E5.14: baseline execution coverage and explicit exit/protection policy, external provenance and expanded fixed studies.
