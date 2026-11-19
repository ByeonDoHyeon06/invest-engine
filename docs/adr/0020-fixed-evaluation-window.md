# ADR-0020 — Research-only evaluation boundaries

Status: Accepted (implementation scope, external data verification open)

## Decision

Require an opt-in, SHA/PIT-pinned single-instrument one-minute raw-share-volume study; full declared sessions with at least twenty prior sessions, explicit evaluation boundaries and market coverage. Warm-up populates histories but never invokes strategy callbacks or the trading ledger. A missing minute is an error, never interpolated. Corporate-action windows remain unsupported in this initial strict mode. Maintain existing E5 APIs when the option is absent.

## Consequences

Evaluation equity and costs are separate from warm-up; the manifest pins evaluation coverage. A historical source can still misstate timestamps or omit exchange sessions. Source rights, completeness, exchange calendars and real costs require independent evidence. A declared no-action test is not a general survivorship-free validation. No E6 promotion or Live authorization.

## Revisit

When a licensed independently verified dataset is available, compare independently predeclared ORB, NoTrade and initial-entry-and-hold, model actual costs, examine out-of-sample results and verify runtime performance. Extend to mixed instruments/actions only with explicit temporal and valuation contracts.
