# E5.3 — Conservative protective exits and sensitivity (offline only)

**Status:** implemented as an **opt-in synthetic OHLCV research model**. This is not a real stop order, execution guarantee, or evidence of trading profitability. `LIVE` remains unsupported.

## Problem and scope

E5.1/2 accepted strategy stop prices as *risk/sizing plans*, but did not use them to close positions. This left profitability and drawdown sensitive to missing exits. E5.3 adds a separate **standing protection hypothesis** with deterministic accounting, and preserves the old E5 runner by disabling this feature by default.

The E3 single-writer simulation and cash/position ledger remain authoritative. E4 strategy code cannot submit a protective broker order. Each protective exit passes through the E3 simulated SELL risk gate and ledger and is attributed to the E4 virtual positions.

## Policy configuration

Add optional `fill_model.protective_exit` to the existing `e5-research-v1` experiment configuration:

```json
{
  "fill_model": {
    "version": "penetration-limit-v1",
    "participation": "0.05",
    "spread_bps": "5",
    "impact_bps": "5",
    "protective_exit": {
      "enabled": true,
      "reward_multiple": "1.5",
      "adverse_bps": "10",
      "version": "protective-ohlcv-v1"
    }
  }
}
```

- This snippet replaces only the `fill_model` value in a complete run config; other top-level required fields are unchanged.
- Omit `protective_exit` for legacy behavior, or set `enabled: false`.
- `reward_multiple: null` enables **stop only** (no automatic take-profit).
- `adverse_bps` is a synthetic, nonnegative adverse-price haircut to a protective fill, **not a broker's quoted spread**. It does not supersede the entry limit's spread/impact crossing test.
- A new opt-in version/parameter change affects `config_sha256`/`run_sha256` and manifest (`protective_exit_version`), allowing separate experiment comparisons. The same data/code/config gives the same run hash.

## Causal lifecycle

1. BUY signal at finalized bar `A` → E3-approved LIMIT intent; no same-bar fill.
2. Valid BUY fill in later bar `B` → source execution ID, quantity, entry price, **original planned stop**, and target (`entry + (entry-stop)*reward_multiple`) become a tracked protection lot.
3. Protection is armed only **after** `B` has been observed. It cannot retroactively fill in bar `B`, even if that bar's low was below the stop.
4. For later, finalized, eligible same-instrument bar `C`, determine triggers: low <= stop means stop triggered; high must **strictly exceed** target + adverse buffer to imply a target fill. If both occur, use **stop first** as a conservative unknown-path assumption.
5. Gap down: if `C.open < stop`, fill at `open` *minus* adverse-price haircut; do not pretend the stop price was achievable.
6. Ordinary stop: fill at stop minus haircut. Target: fill at target minus haircut, never a more favorable gap-open price. Always round the resulting SELL price **down** to a valid tick.
7. Protective exits share the same available per-bar participation volume as other synthetic orders, rounded down by lot size. Unfilled protected quantity remains held/eligible in future bars; new market information can worsen its price.
8. A synthetic SELL order is created, risk approved and fully filled for the *available candidate quantity* at the bar's observation time. This stands in for a pre-existing synthetic protection hypothesis, **not** an observed intrabar order-submission latency or an actual broker stop-limit/stop-market behavior.
9. The virtual strategy ledger and E3 physical synthetic ledger both reflect each protection Fill; report `FillTrace.reason_code` includes `STOP_TRIGGERED`, `GAP_BELOW_STOP`, `STOP_FIRST_COLLISION`, `TARGET_TRIGGERED`.

### Fundamental limits

**OHLCV cannot reveal intrabar ordering.** Stop-first collisions are a stress assumption, not historical fact. A bar's reported volume does not prove fills were possible at the modeled price. Gaps, halts, price-limit behavior, market-impact nonlinearity, historical spread, and order queue priority are unknown. Real stops can slip substantially more, fail, or fill at several prices.

**Conflict fail-closed:** when an old regular SELL order might have executed in the same bar as protection, the simulation **raises `InvalidEvent`** instead of inventing which occurred first. The research operator must resolve the modeling limitation or obtain higher-resolution data. This is a known open execution-model limitation, not a live-ready protective-order implementation.

No automatic corporate-action adjustment of existing protective lots. Input historical bars and instrument/tick metadata must already represent a consistent, verified adjusted/unadjusted policy.

## Validation and sensitivity

Test groups:

- Entry bar's low crossing stop **does not** cause a protective exit in the same bar.
- Stop and target touched in one future bar → stop first.
- Downward gap past stop → worse price than planned stop.
- Target touch without penetration → no assumed fill; target-only crossing has no favorable price improvement.
- Protective fill volume cap → partial exits remain tracked into later bars, including further adverse gaps.
- Conflicting existing SELL reservations → explicit error rather than optimistic double execution.
- Ordinary strategy EXIT consumes protected shares and prevents a later duplicate stop.
- `adverse_bps` sensitivity, synthetic fees, spread/impact, same-seed/data/config hashes and manifest pinning.
- Backward-compatible E5.1/2 config without protection, no real Broker API access, full E0–E4 regression tests.

Compare experiments with identical dataset/strategy/version/fees but different `adverse_bps`, participation, reward multiple, and historical time windows. Do not select the best curve on the final holdout; E6 will supply walk-forward and multiple-testing controls.

## Remaining E5 gates

- Repeatability/cost stress across more realistic multi-session and multi-instrument data.
- Provenance + dataset license + corporate actions + fee/FX policy validation, and richer fill benchmarks.
- Higher-resolution tick/quote fill interface and order-conflict resolution are not present. Actual market live/paper is E7/E8.
- E5 should not be marked *fully* complete solely because this opt-in model and synthetic tests pass.
