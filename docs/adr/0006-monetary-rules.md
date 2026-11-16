# ADR-0006: Explicit cash quantum, order increments and simulated cost-basis risk

- Date: 2026-11-16
- Status: Accepted (simulation only)

## Context

E3 requires correct amount, fee, position, order quantity and cash reservation math. Different markets and brokers may support different tick sizes, lot sizes, settlement precision and rounding. Binary floats and implicit currency exchange produce silent incorrect accounting.

## Decision

1. All internal money, prices, quantities and fee rates are finite `Decimal`; floats are rejected by domain primitives.
2. The simulated account requires explicit `MonetaryRules(currency, cash_step, rounding)`. The fixture policy uses KRW 1 and USD 0.01, `ROUND_HALF_UP`, **not broker/tax/FX rules**.
3. Instrument tick and lot increments are explicitly supplied as `InstrumentRules`, not inferred from currency or current ticker.
4. High precision local decimal context is used for trade cost, fee/position-average arithmetic; cash movements round **at defined settlement/fee boundaries**, not on every intermediate operation.
5. For E3 only, risk exposure uses cost basis in the instrument currency; never auto-converts KRW/USD. Real-time mark, FX and actual brokerage buying power are mandatory before a live authorization.
6. Inventory cost policy for E3's synthetic long-only ledger is moving average including acquisition fees. Tax accounting and brokerage reconciliation may use different rules; changing this requires a new policy/version.
7. No margin, short sales, fractional lots absent instrument capability, real broker orders, or implied stop execution.

## Alternatives

- float for convenience (rejected: precision error)
- auto-round all prices to current currency's minor unit (rejected: invalid broker tick sizes)
- implicit FX for foreign positions (rejected: false buying power)
- fixed decimal scale globally (rejected: incompatible venues/fees)

## Consequences

More configuration and validation, but deterministic and testable accounting. The current implementation is **simulation-only**: rounding, tax and actual brokerage buying power must be verified before E8. Minimum/maximum supported decimal magnitude and Decimal context are engineering constraints for later stress tests, not arbitrary precision guarantees.
