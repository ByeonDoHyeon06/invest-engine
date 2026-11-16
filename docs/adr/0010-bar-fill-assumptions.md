# ADR-0010 — Conservative observable-bar fill model for E5 research

- Date: 2026-11-16
- Status: Proposed for E5.1

## Context

E0/E1 market bars and E4 signals exist, and E3 has a simulated ledger, but no order fill based on historical events. An OHLC bar cannot reveal exact intrabar path, queue position, liquidity and spread. Filling a signal at the price of the bar that generated it introduces look-ahead.

## Decision

1. E5.1 reuses the existing E2→E4→E3 boundaries. It does not import any real broker or connect a private account.
2. All fills are evaluated for orders already approved before the eligible bar began; the fill event is timestamped at bar observation.
3. Require strict limit penetration adjusted for configurable spread/impact bps and cap fills by fraction of bar volume; reject touch-only, missing/zero volume, partial and non-time bars.
4. Report no-slippage price improvement assumption: fill at limit only, with additional crossing buffer as conservative filter. This must be described as a model, not an actual fill guarantee.
5. Reserve/cash/positions/fees/taxes are administered only by E3. E4 Strategy/Allocator cannot bypass Risk.
6. Valuations are per currency and require complete fresh price marks. Missing prices never become zero; unverified FX never gets invented.
7. E5.1 does NOT support executable stop/target or same-bar collision resolution. Those are explicit gates for E5.2 before E5 is marked done.

## Alternatives

- Fill at signal bar close or open (look-ahead and same-bar optimism).
- Fill whenever low/high touches the limit (optimistic and ignores queue).
- Assume tick/quote/order-book data can be reconstructed from bars (false).
- Introduce a live broker to validate fills (unsafe at research stage).

## Consequences

Conservative assumptions reduce false-positive fills but do not guarantee results are pessimistic in all conditions. The model cannot estimate queue priority, market impact or actual execution latency. Cross-model sensitivity and forward-paper comparison are mandatory before real trading.

## Revisit

At E5.2 after separate stop/target/gap model verification; E7 when observed paper fills offer better calibration.
