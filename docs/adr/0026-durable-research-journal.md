# ADR-0026 — Durable offline research registry and report reconciliation

Status: Proposed; CI pending.

Persist the pure candidate state machine as an append-only canonical command history using SQLite transactional writes, hash chain and head. Reserve holdouts across plans in the same database using explicit instrument interval and event digest; reject same tape in development and test. Restore by replay, not mutable snapshots. Bridge E5 strict reports using explicit bindings and structurally reconcile event/trace/metric data; imported evidence remains provisional. No automatic certification or orders. Local hash integrity is not privileged tamper-proofing, trusted timestamp, signed manifest or data-access isolation. See [E6.2](../E6_2_RESEARCH_JOURNAL.md). E5 release still blocked.
