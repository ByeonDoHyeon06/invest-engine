# ADR-0019 — Explicit witnessed cash recovery for terminal delisting

- **Date:** 2026-11-17
- **Status:** Accepted for synthetic offline research ONLY; external source verification OPEN
- **Supersedes:** No existing ADR; adds to [ADR-0018](0018-delisting-terminal-bar-research.md)

## Context

ADR-0018 rejects delistings with remaining holdings rather than inventing final sale prices. E5.11 permits a narrowly evidenced net cash receipt while keeping the accounting distinct from exchange fills. A file SHA ensures integrity of declared bytes, not the issuer's truth.

## Decision

An `E3 DelistingCashResolved` event linked to a previously journaled `DelistingObserved` may close the entire held quantity and deposit a declared exact net cash amount, provided the receipt was **already paid and observable by the last replayed bar**. It is not modeled as a SELL; E4 virtual allocations follow exact share closure. The receipt uses a versioned typed event, identity hash, append-only ledger and journal replay. Records with missing, late, future, mismatched, duplicate or changed evidence fail closed.

## Alternatives rejected

- Selling at last OHLC close, silently treating delistings as -100% loss, or always writing off to zero: unsupported, optimistic/pessimistic without proof.
- Charging assumed taxes and fees to a *net* recovery receipt: double counting.
- Replaying post-delisting cash on the last trade day: look-ahead bias.

## Consequences and revisit

The E5.11 scope covers a minority of realistic corporate actions; its first case is primarily an accounting contract with synthetic tests. Post-terminal asynchronous cash events, delayed court/issuer distributions and position recovery state require a separate chronological event stream. Real provider data, fee terms, trading-volume quality and forward paper validation remain open E5/E7 gates. No live orders.
