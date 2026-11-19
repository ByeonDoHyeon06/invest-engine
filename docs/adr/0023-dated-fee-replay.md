# ADR-0023 — Opt-in dated fee-aware simulation

**Status:** Proposed, offline only; CI pending.

Preserve existing E3 journal and E5 config identity by keeping the legacy config dataclass unchanged and opting into a versioned subclass with explicit dated regulatory schedule evidence. Use policy hooks in pretrade reservation, pure reducer and simulation runtime; calculate cumulative rounded order commission and SEC increments from prior fills rather than per-fill repeated minimums. TAF uses modeled execution as trade proxy. Journal restores verify config identity. Existing levy field holds combined SEC/TAF; separate research audit checks actual components. Fail closed for unsupported precision/date, cross-day fills and negative proceeds. No claim about actual retail pass-through.

See [E5.14b.2](../E5_14B_FEE_REPLAY.md). No real account, broker integration or live authorization.
