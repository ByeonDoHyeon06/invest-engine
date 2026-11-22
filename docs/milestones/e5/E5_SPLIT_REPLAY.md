# E5.8 — Point-in-time session-open split replay (offline research only)

**Status:** Limited implementation, synthetic/PIT-declared inputs. Not an exchange data certification, dividend engine, or live execution capability.

## Why this exists

E5.6's PIT gate rejected all in-window issuer actions. E5.7 implemented a simulated `SplitApplied` portfolio journal event, but E5's historical runner did not consume it. E5.8 adds a **split-only, session-open** bridge: during replay, the portfolio, strategy virtual inventory and feature warmup move together. Unsupported actions **still fail the full run**. This is not blanket corporate-action support.

## API / input contract

The existing `e5-research-v1` config accepts one additional **optional** object, requiring `pit_evidence` as well:

```json
"split_replay": {
  "records_jsonl": "splits.jsonl",
  "sha256": "<lowercase exact-file SHA-256>",
  "source": "caller-declared issuer feed",
  "license": "caller-declared license",
  "price_basis": "RAW_UNADJUSTED"
}
```

The `splits.jsonl` file contains one tagged JSON object per action with **exact** fields:

```json
{"kind":"split","action_id":"split-1","instrument_key":"US:XNAS:US0378331005","numerator":2,"denominator":1,"effective_at":"2026-10-01T13:30:00Z","available_at":"2026-09-30T19:00:00Z","source":"caller-declared issuer feed"}
```

An independently supplied `pit_evidence` file must contain the *same* `action_id`, `instrument_key`, `SPLIT` kind, `effective_at`, `received_at` (= `available_at`) and `source`, plus full vintage/universe/action-catalog coverage as in E5.6. Source/license strings alone **do not prove provider rights or authenticity**. `RAW_UNADJUSTED` is a caller-attested price-basis convention; pre-split historical prices must not already be split-adjusted. There is no automatic adjusted-to-raw conversion.

## Replay boundary / failure policy

- Split terms must be received **no later than** the effective time; they are not backfilled from future disclosures.
- The split must occur **at the start of an explicitly declared trading session and exactly at the opening time of an observed finalized bar**. Intrabar, non-session-open, missing-boundary and post-effective disclosures are rejected before or during replay.
- E3 applies the versioned `SplitApplied` event before processing the first post-split bar, not at a fictitious intrabar timestamp. It rejects open orders, invalid fractional lots and conflicting action identity.
- E4 virtual inventory scales `quantity × numerator/denominator`, `average_cost × denominator/numerator`, preserving total basis. Total virtual shares must match E3 inventory immediately after every action. No synthetic fill/fee/cash is created.
- E4 strategy bar history, warmup counts, and prior marks for that instrument are cleared to avoid mixing pre/post-split price scales. Each strategy must earn new warmup observations. Strategy-owned custom caches are **not automatically rewritten**; unsupported custom strategies need a separate `on_corporate_action` contract before use.
- E5 standing protective stop/target simulation cannot yet adjust previously armed stop/target lots, so **protection-enabled runs with a split schedule fail closed**.
- `CASH_DIVIDEND`, `DELIST`, `MERGER`, `SYMBOL_CHANGE`, out-of-range or undeclared actions remain hard failures. No price, dividend, entitlement or delisting consideration is invented.
- All runs are still offline historical simulations. `config_sha256`, E3 state digest and report/manifest hashes bind the split schedule. The action is visible in the affected `decisions.jsonl` row as `SPLIT_APPLIED:<action_id>`. `split_replay_data_verified=false` is always written in the manifest.

## What this does **not** prove

The PIT declaration and SHA checks prove internal consistency only. Completeness of issuer actions, data vintage truth, corporate-action adjustment conventions, market calendar, actual fee/tax, and actual execution remain unverified until an independently reviewed, licensed historical feed is available. Dividends and delistings remain entirely blocked in the historical runner. The E5 epic is still open, and E7/E8 must not assume live safety from these tests.

## Tests

`tests/test_split_replay_e5.py`: 2:1 overnight split with already filled synthetic inventory, equity/basis preservation, virtual book matching, determinism, CLI+PIT+SHA roundtrip, future disclosure, wrong session boundary, invalid price-basis, tampered schedule and unsupported corporate actions. Existing E0–E5 regressions must remain green.
