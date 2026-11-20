# ADR-0034 — Unified typed SDK and shared orchestration

Status: Proposed (planning only; #59). 2026-11-20.

Context: core is modular but public Python root is version-only; E4 strategy, E5 experiment and E6 research require separate wiring. Users need a simple entry point without losing existing capabilities.

Decision proposed: one thin offline SDK facade with a versioned normalized spec shared with CLI, explicit immutable research profiles and typed advanced settings. SDK delegates to the existing core/research runtime; preserve existing import paths and strict decode; expose stable namespaces and documented extension protocols. No hidden I/O, no default live mode, no risk bypass, no duplicate real-asset ledger. Capability parity and deterministic output reconciliation are mandatory before release. See [E6.7](../E6_7_UNIFIED_SDK.md).

Alternatives: flatten all internal classes into root (poor discoverability/contract churn); replace core with new high-level engine (duplicates state and risk); CLI-only wrappers (insufficient programmatic flexibility). Reject these in favor of shared facade composition.

Consequences: requires API inventory, explicit supported combinations, profile expansion, migration tests and public contract documentation; additional surface is versioned. New underlying functionality and release gates remain independent.

Revisit: parity gaps, measurable orchestration overhead, incompatible external adapter lifecycle, or required security boundary changes. Final acceptance requires E6.7 implementation evidence and review, not this planning PR.
