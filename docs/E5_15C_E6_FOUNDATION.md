# E5.15c / E6 foundation — gap evidence and offline candidate registry

Status: candidate only; E5 issue #6 remains open. E6/G2 is NOT accepted. No strategy promotion, broker access, real-account state or live trading.

## E5.15b independent source outcome

[PR #43](https://github.com/ByeonDoHyeon06/invest-engine/pull/43) [Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44504600006) 338 tests each on 3.12/3.13, Ruff/mypy/secrets successful. [Kibot source diagnostic](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44504600594) downloaded and parsed both public samples. Four preregistered windows, zero eligible, zero executed arms; no profitability observations. Regression workflows separately still pending at time of writing.

| Fixed 2026 window | Observed / expected | Missing | Whole complete sessions |
|---|---:|---:|---:|
| IBM Sep (includes known Aug dividend in warm-up) | 10,908 / 15,990 | 5,082 | 20 / 41 |
| IBM Oct | 16,364 / 16,380 | 16 | 33 / 42 |
| OIH Sep | 8,735 / 15,990 | 7,255 | 0 / 41 |
| OIH Oct | 13,186 / 16,380 | 3,194 | 0 / 42 |

IBM sample SHA256 e8b3f6a961d638229e48567877eefa1003f2c45b9a5af7dddaaf51c811a1f3c2, OIH sample 42f5807e5d214a644b846829fb8856a122883b68e1d806bd120768ac51183891 (rolling vendor file). No extra minutes recorded. Missing minutes can mean no trades, omitted prints, incomplete retention or interruptions; not enough evidence to choose. No OHLC or volume fabrication. No moving dates to make results look better.

E5.15c extends loader with explicit consecutive absent-minute intervals, session boundaries, isolated gaps, longest gap and whole missing days. No change to strict E5.12 acceptance; missing data still returns zero executable event streams. Aggregate-only outputs (no price rows). A future sparse event model needs evidence of *known* no-print periods vs unknown provider outages, feature invalidation, pending order handling, stale marks, protective stops and session-close guarantees. Until then no in-gap simulated execution.

## E6 foundation (offline only)

`research/candidates.py` provides immutable dataclasses and pure snapshot transitions. Supports:
- Candidate strategy version, code digest, config digest and training cutoff, baseline config digests.
- Declared window IDs, instrument, currency, explicit dataset/context digests and train/validation/test splits. Cross-instrument chronological partition boundaries require at least label horizon + embargo between splits; duplicate overlapping symbol intervals rejected. This is a conservative **partition-level** gap guard, not yet sample-wise feature provenance, automatic walk-forward generation or actual model training.
- Each candidate must be compared against NoTrade and a genuinely entered BuyHold on all prescribed validation windows and base/stress costs, matching declared dataset/context, currency, start cash and candidate config. Duplicate keys/run IDs fail, exact retransmission is idempotent prior to lock. No zero-return unfilled hold masquerading as an investment baseline.
- Return is account PnL/opening cash; equally weighted independent windows, no FX mixing or compounding. Per-window base and stress exit count and MDD gates, mean excess over the better of both matched controls, worst MDD report. All thresholds explicit; fixture defaults are not policy recommendations. Missing/incomplete/unverified data/cost/execution or inadequate fills -> INCONCLUSIVE; valid evidence but below criteria -> REJECTED; otherwise RESEARCH_PASS (research-only, not a Shadow release).
- Freeze validation before accepting any test records; choose strongest weakest-cost mean excess, deterministic ID tie-break; only selected candidate plus controls may submit holdout records. Finalize test once per immutable snapshot lineage. Reject missing matched arms. Failed candidates remain in evidence.

Important boundary: caller must store snapshots in a durable append-only registry, independently verify referenced report/config/data identities and attestations, ensure unseen holdout data is not accessible before evaluation and prevent a fresh registry from repeating the same holdout. Pure Python values are not an authorization or anti-tampering boundary. This foundation does not train models, generate signals/orders, acquire client assets, decide live policy, supply actual verified evidence, or certify any strategy. Do not mark E6 roadmap DoD complete. Next build report-to-evidence adapter, durable registry/one-use holdout identity, walk-forward generator and market-regime stratification, but keep actual E6 acceptance behind E5 data/cost/PIT gates.
