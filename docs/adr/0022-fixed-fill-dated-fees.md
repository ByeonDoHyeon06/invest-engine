# ADR-0022 — Fixed-fill dated fee sensitivity

Status: Accepted for offline research (PR #41 verified)

Context: E5.14a demonstrated technical session liquidation and unchanged legacy controls, but the base/stress fee rate is synthetic and does not separate SEC/TAF.

Decision: use an explicit dated schedule for a bounded historical interval, distinguish regulatory rates from retail pass-through, and reprice a fixed simulated fill tape with deterministic charge breakdowns. Separate report values from original ledger/MDD; unsupported dates and input integrity mismatches fail closed. Preserve legacy settings and replay output. Do not add cost changes to cash/risk execution without a dedicated replay/reservation design.

Consequences: fixed-fill audit is suitable for comparing direct cost assumptions on a known tape but not proving identical orders or actual broker billing. Full accounting integration remains E5.14b.2.
