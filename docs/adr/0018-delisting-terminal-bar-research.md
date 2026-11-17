# ADR-0018 — Narrow terminal-delisting gate for offline research

- Date: 2026-11-17
- Status: Accepted (offline research only)
- Supersedes: no earlier corporate action accounting policy; extends ADR-0014/0015/0017

## Context

E5.6 refused unmodeled delistings. E5.7 provided E3 `DelistingObserved`, but E5 historical strategy replay did not connect it. Automatically treating a delisted holding as worth its last print or zero is both economically ungrounded and potentially optimistic. Ignoring delisted securities can introduce survivorship bias.

## Decision

1. Support strictly evidenced *unheld* delisting at the terminal confirmed historical bar only, with immutable source/hash + matching PIT event and timestamp contract.
2. The E3 reducer records the delisting and prevents later trading; the E5 coordinator suppresses last-bar strategy signals for that instrument.
3. Refuse unresolved orders, held positions, post-delisting market data, unknown/future publication timing, and conflicting simultaneous corporate actions. No guessed exit/zero-price liquidation, recovery amount, cash-in-lieu or reverse-adjustment.
4. Keep all prior E5 research config SHA values when the extension is absent.
5. Treat even a passing synthetic PIT gate as **unverified real-world completeness**. Do not close E5 on this narrow scope.

## Alternatives rejected

- Implicit 0 recovery (may misprice actual recovery and cannot be verified from OHLCV).
- Carrying forward last price after listing termination (falsely assumes liquidity).
- Removing delisted symbols from the benchmark dataset (survivorship bias).
- Retroactive end-of-period forced sell at last bar (ignores queue/availability).

## Consequences and revisit

Fail-closed research runs for delisted holdings until independently validated, versioned issuer-cash and corporate settlement information is available. Add explicit settlement accounting, multiple-security recovery terms, delisting/delayed action timestamps, transaction costs, and complete provider universe coverage before broadening this ADR. No broker or live-trading privileges are introduced.
