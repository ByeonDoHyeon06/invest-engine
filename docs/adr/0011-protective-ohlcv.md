# ADR-0011 — Opt-in conservative protection for historical OHLCV (E5.3)

- Date: 2026-11-17
- Status: Accepted for offline synthetic research only

## Context

E4 provides planned stop prices, while E5.1/2 only simulated ordinary limit orders and position marks. The lack of stop/target exits can distort backtest results. However OHLCV does not reveal whether a target or stop occurred first, whether a broker order existed, or the actual fill price.

## Decision

1. E5 may explicitly opt into a versioned **protection hypothesis**, disabled by default for backward compatibility. This is not a broker stop order.
2. Track each observed BUY Fill as an immutable source-lot with its planned stop; calculate a target only when a reward multiple is configured. A lot becomes eligible only in bars that start after its entry Fill was observed.
3. A stop triggers at low <= stop; target fills require strict high penetration. In a stop/target collision choose the stop as the worst-case ordering assumption.
4. An opening gap below stop is modeled at the worse opening price, never the stop itself. Apply a separately configured adverse basis-point buffer and round SELL prices down to a valid tick.
5. Cap protective exits by the same per-bar participation budget as existing limit fills, allowing multi-bar partial exits. Protect only inventory actually purchased and attribute exits to both E3 account and E4 virtual strategy positions.
6. Route modeled exits through E3's explicit simulated SELL risk, position reservation, fee/tax and Fill accounting. Never connect to the broker.
7. An existing competing SELL order and a protective trigger are historically unresolvable with OHLCV; fail closed instead of assuming a convenient order.
8. Report trigger reason and policy version in decision/fill traces, config hash, and experiment manifest. Legacy experiment settings remain parseable.

## Alternatives

- Treat the planned stop as guaranteed immediate execution at its trigger price (optimistic, rejected).
- Assume favorable target-first ordering in bars touching both boundaries (rejected).
- Backdate a protective sell into the entry-fill bar (future information leakage, rejected).
- Infer a precise trade/quote tape from 1-minute OHLCV (impossible, rejected).
- Change E3 to support actual stop-market orders now (outside E5's simulated-only scope).

## Consequences and follow-ups

The simulator can now stress adverse price paths but **is not a reliable market microstructure or order-management replica**. It may be conservative about collision ordering while still too optimistic about volume and execution. If a protective order conflicts with an existing EXIT order, the research run intentionally errors. More detailed tick/quote data, market calendars, real broker order semantics, provider fees, FX and corporate actions require separate validation before paper/live deployment.
