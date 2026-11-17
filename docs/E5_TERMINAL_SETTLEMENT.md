# E5.11 — Terminal delisting cash resolution (offline research only)

**Implementation scope:** a deliberately narrow, evidence-declared *cash receipt* for a delisted long position. This is **not** an order fill, an automatic liquidation, issuer authentication, or a prediction of eventual recovery.

## Reconciliation contract

- The E5.10 `delisting` record remains mandatory, point-in-time checked, SHA-pinned alongside `pit_evidence`.
- An optional second tagged row in the same `delisting_replay.records_jsonl` can explicitly record the already **paid** terminal recovery:

```json
{"kind":"cash_resolution","action_id":"delist-123","instrument_key":"US:XNAS:EXAMPLE","quantity":"10","net_cash":"0","paid_at":"2026-11-17T16:00:00Z","available_at":"2026-11-17T16:00:00Z","source":"declared-issuer-payment-witness","evidence_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

- All decimals are JSON **strings**; all instants are aware **UTC**. `quantity` must match the E3 position **exactly**; `net_cash` must be nonnegative and an exact supported currency quantum. `0` denotes **an explicitly witnessed zero receipt**, not a default assumption. The `source` and witness SHA are declarations; the software does not authenticate them against the issuer.
- This first bridge requires `paid_at <= delisting.effective_at` and `available_at <= delisting.effective_at`. A payment announced or received **after** the last market bar must **not** be backdated into that bar. Such a case fails with `TERMINAL_SETTLEMENT_AFTER_LAST_BAR_REQUIRES_CASH_EVENT_REPLAY`; a future version must add a separate market-independent post-delisting settlement event timeline.
- The E3 event `DelistingCashResolved` can only follow matching `DelistingObserved`, with no outstanding orders. It records exact net cash, closes the held inventory, and computes realized difference from historical acquisition basis. It **never** emits `OrderIntent`, `SimulatedFill`, fabricated final share price, tax estimate or brokerage command.
- E4 strategy-level virtual inventory is zeroed with cash divided proportionally across existing virtual holdings; account and virtual quantities are reconciled. The strategy receipt does **not** create a simulated SELL. The event is deterministic, journaled, canonical-codec roundtrippable and safe under restart. Exact duplicate terms are idempotent at the runtime API, a conflicting repeated receipt halts simulation.
- `BacktestReport.terminal_settlements` holds an auditable per-action quantity, currency, cash and realized P&L record. It is distinct from ordinary market exit fills. The `run_sha256` and `manifest.json` pin the experiment identity; the manifest retains `research_data_release_verified=false`.

## Explicit unsupported cases

1. **Most real-world delisting settlements**, which pay after the last trading bar: rejected until post-delisting event-clock support is built.
2. Cash-in-lieu, conversions/mergers, worthless-security writeoffs without an independently evidenced receipt, share reconciliation disputes, and withheld taxes/fees not already captured in the *net* receipt.
3. Corporate-action truth/completeness, legal use rights, source authenticity and broker account accuracy are **not** established by a hash or synthetic unit tests.
4. LIVE execution remains **NOT AUTHORIZED**. The entire E5 research acceptance gate stays open.

## Validation

`tests/test_terminal_settlement_e5.py` covers held and unheld paths, quantity and currency mismatch, cash conservation, no fictitious SELL fill, cash receipt time, duplicate/changed receipt, two-strategy virtual attribution, PIT schedule loader hash, canonical E3 codec, and SQLite restart recovery. Existing E5 synthetic and historical daily regressions must remain green.
