# E6.2 — Durable offline research journal and E5 report bridge

**Status:** implementation candidate; CI pending. E5 issue #6 remains OPEN; E6/G2 NOT accepted. No real-account, broker, Shadow or LIVE authority.

## Verified previous stages

[#43](https://github.com/ByeonDoHyeon06/invest-engine/pull/43) merged cbb8800 after all six workflows succeeded (338 tests per Python 3.12/3.13). All 42 eligible historical fee-aware regression rows matched #42 on common numeric fields, excluding revision-dependent hashes and durations. Independent Kibot sample downloads succeeded, all four fixed windows blocked and no actual independent strategy runs. [#44](https://github.com/ByeonDoHyeon06/invest-engine/pull/44) merged 13e615f after Ruff B905 correction and [Core CI](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44505913031) 344 passed each, style/types/secrets. [Gap diagnostic](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44505912989) confirmed IBM Oct 16 isolated one-minute gaps, OIH Oct maximum eight-minute gaps, both September samples 13 entire missing sessions. These are absent observations, not verified no-trade intervals. No relaxed sparse-window execution.

## Design

`ResearchJournal` is local SQLite, with explicitly serialized writer transactions. Register the immutable research plan; record candidate/benchmark arms; lock validation; finalize selected holdout. Persist canonical JSON command payloads, consecutive sequence, previous digest, current digest, and separate head row atomically. On read/write/reopen replay every command and validate canonical form, identities, transitions, hash chain and head; reject corrupted history, trailing deletion without head modification, duplicate/conflicting evidence and invalid transitions. Equal registration and pre-lock arm retransmission are idempotent. Failed writes roll back; no mutation/delete API. Holdout reservation is global within this database and checked at registration against prior plans' test or development windows, using declared stable instrument identity plus overlapping interval or exact event-tape digest. Within a plan reject an identical tape in development and test. Reject cross-plan duplicate run SHA. This is deliberately conservative: an abandoned registered holdout remains reserved, and old development data cannot be renamed into a future holdout.

`ReportBinding` identifies plan digest, window, candidate/cost and expected full E5 report config digest. `report_context_sha256` pins the explicit calendar/window and caller-declared scenario identity. `evidence_from_report` verifies plan and binding, single instrument/currency, dataset hash recomputed from exact events, strict minute coverage including warmup, event/decision ordering, equity times/currency/final value, PnL, MDD, unique fill IDs and valid source event membership, BUY/SELL counts and total fees/taxes. Store canonical report SHA alongside the arm. `record_report` bridges to durable transaction; caller retains raw events and report privately. No raw market data or order transport in journal.

The bridge is **structural reconciliation**, not proof of strategy identity or independently witnessed execution. Expected full report config digest and scenario digest are caller-supplied, not yet a signed pre-run manifest or independent replay certificate. All imported reports set provenance_verified, cost_verified and execution_validated false; a high return cannot bypass the evaluator's INCONCLUSIVE gate. The generic `record` surface is for explicit caller-supplied evidence (including synthetic tests), not an attestation service; it cannot authenticate true flags. Before genuine E6 acceptance, implement independently verified evidence/manifest binding, explicit holdout isolation, feature-level leakage controls and authenticated approval. Hash chain detects corruption, not a privileged rewrite or whole DB rollback; no cross-database or instrument-alias enforcement, external timestamp/anchor, data-access control or database-level immutable service. Replay cost grows with history; prototype for local research. A one-use holdout rule does not prevent someone inspecting files outside this journal. No claim that these safeguards certify profitable strategies.

## Example

    with ResearchJournal("research.sqlite") as journal:
        journal.register(plan)
        journal.record_report(plan.plan_id, binding, report, events, calendar,
                              window, scenario_identity=scenario_digest)
        snapshot = journal.get(plan.plan_id)

Once all registered validation comparison arms are recorded with adequate evidence, lock validation; only the selected candidate and controls may submit holdout outcomes to the state machine. Provisional imports cannot themselves achieve a research pass. Do not set verification flags to true as a shortcut.

## Next

E6.3 walk-forward fold planning with sample-level label purge and explicit disjoint final holdout, E6.4 market regime analysis with as-of inputs, E6.5 controlled strategy/parameter generation. E5 independently licensed complete/meaningfully sparse data, issuer actions, actual dated fees and PIT evidence remain release blockers. More tests and real source acquisition needed; no strategy promotions.
