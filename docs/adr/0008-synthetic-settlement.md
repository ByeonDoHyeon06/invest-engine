# ADR-0008: Synthetic sell charges and explicit settlement confirmation

- Date: 2026-11-16
- Status: Accepted for **simulation only** (E3.4 PR #20 verified/merged)

## Context

E3.1 immediately credited all synthetic SELL proceeds to spendable `CashLedger.settled`, while `unsettled` existed but was not used. This hid the distinction between equity and buying power and did not provide a per-execution synthetic tax audit. Actual settlement dates, fees, tax treatment and ability to reuse sale proceeds vary by market, instrument, broker, account permissions and regulations.

## Decision

1. Keep the old simulation's `IMMEDIATE` mode as default for backward compatible replay. Add opt-in `SellSettlementMode.EXPLICIT_CONFIRMATION`, not an unsupported assumption of T+2.
2. In explicit mode, a SELL Fill posts its net proceeds to `unsettled`, linked to the immutable `execution_id`. Only an auditable `CashSettlementConfirmed` event moves them to `settled`, one time per execution.
3. Add `TradingConfig.sell_tax_rate` for synthetic SELL levy only. Use the existing explicit `Decimal` settlement and fee-rounding rules, and audit gross, fee, synthetic tax and cash delta per Fill. Never label the configured number as actual tax or brokerage rate.
4. Preserve historical E3 journal bytes, digests and old default config identities. New opt-in policy must be part of the journal identity and refuse reinterpretation of stored fills.
5. Audit reservations, outstanding settlements, fill totals, positions and spendable cash after every deterministic transition.
6. Do not implement an exchange calendar, T+N auto settlement, margin/instant reuse of unsettled proceeds, or actual broker synchronization in E3. These require market/broker evidence in E7/E8.

## Alternatives

- Implicit automatic T+2 assumption without verified market calendar: rejected.
- Credit unsettled proceeds as usable buying power: rejected in conservative synthetic model.
- Reinterpret historical FillRecorded bytes with an optional tax field: rejected as replay hash breaking.
- Apply ad hoc tax in a performance report but not the cash ledger: rejected for cash/PnL inconsistency.

## Consequences

Existing simulation behavior and journal replay remain compatible by default. New explicit settlement mode exercises more realistic cash availability constraints but **does not claim** to reproduce a Toss live account. Each policy change requires a new experiment/journal identity. Reconciliation with actual broker settled/unsettled fields remains E8 work.

## Revisit

When actual market + broker fee/tax/settlement schedules and account buying-power semantics have been verified, create a new versioned policy/ADR and update simulations plus compatibility tests.
