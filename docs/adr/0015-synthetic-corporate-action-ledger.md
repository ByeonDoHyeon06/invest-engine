# ADR-0015 — Explicit synthetic issuer actions and real CSV volume provenance

- Date: 2026-11-17
- Status: Accepted for E5.7 synthetic/offline research **only**; not a real-data verification certificate

## Problem

A historical price series can hide splits, dividends, delistings and adjusted-price vintages. Pretending a delisted share vanishes or letting split quantities modify open broker orders would falsify both execution and ledger state. Real OHLCV CSVs also sometimes use `volume` to mean *tick count*, which is not traded shares.

## Decision

1. E3 TradingState accepts immutable, versioned, replayable `SplitApplied`, `DividendEntitled`, `DividendPaymentConfirmed`, `DelistingObserved` event payloads from an **explicitly trusted caller**. No provider requests or automatic issuer inference.
2. Reject a split with open orders or fractional share results absent cash-in-lieu; preserve position total acquisition cost, realized PnL and existing cash. Persist quantity adjustments and enforce audit after every event.
3. Dividend entitlement is a memo receivable until payment is confirmed, independent from settled/unsettled sale cash. Withholding is a configured **synthetic** example. Delisting blocks new orders but does not guess a terminal market value.
4. Corporate events can only be applied after their effective and available timestamps. Duplicate IDs must match exact payload fingerprints; otherwise halt and require operator review.
5. CSV converter requires explicit UTC timestamps and declared `SHARES`/`TICK_COUNT`. `TICK_COUNT` can only be used with `no-trade` in the JSON backtest boundary. A declared volume unit is not source verification.
6. The E5.6 PIT gate remains fail-closed for any corporate action in the tested time range until a historical price-adjustment and E4 attribution bridge is separately implemented and independently tested.

## Rejected alternatives

- Automatically split-adjust all historical quotes without authoritative effective dates or a price adjustment policy.
- Immediately credit dividend cash at declared entitlement time.
- Book a delisted position at zero or last price as realized loss without a terminal settlement or corporate action.
- Treat broker quote/tick volume as exchange share volume and advertise ORB profitability.

## Consequences

The E3 event journal remains deterministic, older events remain decodable, and the accounting boundary is ready for a later PIT-aware replay integration. This is not an end-to-end issuer-action-adjusted historical backtest. For this reason E5 remains **in progress**, and Live is **NOT AUTHORIZED**.
