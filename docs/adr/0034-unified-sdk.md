# ADR-0034 — Unified typed SDK and shared orchestration

Status: Accepted design direction by user (planning only; #59); SDK implementation and acceptance tests pending. 2026-11-20.

Context: core is modular but public Python root is version-only; E4 strategy, E5 experiment and E6 research require separate wiring. Users need a simple entry point without losing existing capabilities.

Decision: one thin, mode-neutral SDK facade with a versioned normalized spec shared with CLI, explicit immutable research profiles and typed advanced settings. SDK delegates to the existing core/research runtime; preserve existing import paths and strict decode; expose stable namespaces and documented extension protocols. Canonical `Engine()` constructor is inert and mode-neutral (no offline()/online()/research() class factory or mandatory mode); explicit operations determine capability. `engine.backtest`, `engine.research`, `engine.evaluate`, future `engine.paper` / `engine.live` are the intended entry points. Data-provider connectivity does not grant trading permission. No hidden I/O, no default live mode, no risk bypass, no duplicate real-asset ledger. Capability parity and deterministic output reconciliation are mandatory before release. See [E6.7](../E6_7_UNIFIED_SDK.md).

Alternatives: flatten all internal classes into root (poor discoverability/contract churn); replace core with new high-level engine (duplicates state and risk); CLI-only wrappers (insufficient programmatic flexibility). Reject these in favor of shared facade composition.

Consequences: requires API inventory, explicit supported combinations, profile expansion, migration tests and public contract documentation; additional surface is versioned. New underlying functionality and release gates remain independent.

Revisit: parity gaps, measurable orchestration overhead, incompatible external adapter lifecycle, or required security boundary changes. [Normative examples](../E6_7_SDK_EXAMPLES.md) define target DX. Changes to constructor, method/namespace names in frozen examples, defaults, safety and compatibility need explicit user approval and an ADR amendment/replacement with synchronized spec/issue/roadmap/examples/tests before implementation. Final acceptance requires E6.7 implementation evidence and review, not this planning PR.

## 2026-11-20 amendment — streaming-compatible facade (user-approved direction)

Keep `engine.evaluate(...)` callable with its existing single-decision semantics; a callable service may also expose `engine.evaluate.session(...)`. Caller-fed sessions own bounded observation/feature/strategy state, never authoritative live holdings or order authority. `engine.paper.start(...)` is an explicit async lifecycle operation for simulated execution with managed market data. Provider and caller transports converge at canonical EventEnvelope ingress; replay, paper and future live share deterministic decisions/risk where supported but execution policies remain separate. See [streaming contract](../E6_7_STREAMING_CONTRACT.md) and examples 19–23. E6.7a defines exact types, compatibility and test matrix; E7 implementation separate, E8 live explicitly unauthorized. All previously approved examples unchanged except expanded reference count. This does not grant provider access or alter research gates.
