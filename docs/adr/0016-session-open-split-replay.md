# ADR-0016 — Narrow PIT session-open split replay

- Date: 2026-11-17
- Status: Accepted (offline research, split-only, not certified market data)

## Context

Existing synthetic share split accounting is journaled in E3, but E5.6 intentionally rejected all PIT corporate actions, preventing any replay across a known split. Treating a raw 2:1 split as a 50% trading loss or retroactively modifying all past bars both produce misleading strategy research.

## Decision

1. Only explicit, **PIT-declared, session-open** `SPLIT` actions can cross E5's PIT gate, with a second SHA-pinned file containing numeric ratio. Both sources must agree on ID, instrument, effective time, receipt time, and source.
2. Require caller-attested **raw, unadjusted** prices and previously available split terms; never infer ratios from bars or automatically rewrite historical prices.
3. Reuse E3 `SplitApplied`, then scale E4 virtual strategy inventory, verify E3/E4 quantity parity and clear pre-split feature history. No synthetic cash or execution at split.
4. Do not adjust already-active stop/target simulations or open orders; fail closed until a more complete policy is modeled.
5. Keep dividend, merger, symbol change, delisting, intraday split, inaccessible market information and unknown provider adjustments unsupported.
6. Keep E5 issue open until licensed market data, full issuer coverage, risk and execution policies are independently verified.

## Alternatives

- Blindly skip the split date (rejected: survivor and performance bias).
- Divide all prior bars using today's split ratio (rejected: as-of ambiguity and future leakage).
- Automatically cancel and replace standing orders (rejected: invents broker behavior).
- Support dividends/delistings without entitlement and settlement data (rejected).

## Consequences / revisit

Tests can exercise a well-defined raw-price split crossing, but this is **not market correctness certification**. Real feed integration must establish raw-vs-adjusted rules, timestamp provenance, symbol master and corporate-action completeness. Future versioned strategy cache migration and protection-lot repricing must be designed before supporting unrestricted split replay.
