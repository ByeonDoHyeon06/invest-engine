# ADR-0007: Explicit, journaled market risk observations for simulated trading

- Date: 2026-11-16
- Status: Accepted (E3 simulation only)

## Context

E3.1/E3.2 evaluate pretrade risk using acquisition-cost exposure and have no current prices, FX marks or broker snapshot. E3.3 needs an accurate baseline for a daily-loss gate, stale-feed detection and account-mismatch response without changing core data resolution assumptions or authorizing live trading.

## Decision

1. Create typed, immutable `MonitorInput` (price/FX marks, daily equity baselines, optional reference snapshot) and compute `MonitorResult` by a pure evaluator.
2. Journal **inputs**, not an untrusted claimed `OK` result. Recompute the result during replay from the preceding TradingState with the pinned RiskLimits.
3. Monitoring is opt-in in existing synthetic runtimes for E3 backward compatibility (`require_monitoring=False`); **never permit live trading to inherit this opt-out**.
4. For monitored new BUYs, require recent healthy risk observation, a fresh symbol mark, and unchanged ledger since the last check. SELL risk reduction remains permitted even on data outage.
5. The daily loss stop is per currency from an explicit trusted session baseline. Once breached, latch the session, even if equity subsequently recovers. This prevents a market bounce from re-enabling entries.
6. Missing/stale positions or FX never yield a partial aggregated equity presented as complete. No implied currency conversion.
7. Reference mismatches persist as a reconciliation hold until a clean subsequent reference and a recorded manual operator review event.
8. Actual broker connectivity, session calendar authority, multi-currency consolidated loss guard, exchange/settlement/tax conventions, and human authentication remain future work.

## Rejected alternatives

- Assume missing position marks are zero (false PnL/loss triggers), or silently use historical purchase price (stale valuation).
- Allow model/strategy to disable the monitor or risk policy (breaks risk boundary).
- Read external broker/account state directly inside a pure reducer (side effects and replay non-determinism).
- Automatically re-enable trading after a rejected account reference disappears (unsafe without review).
- Force monitoring on legacy E3 synthetic fixtures without supplying a market data source (breaks existing valid tests and migration).

## Consequences

Additional typed E3 events and policy-specific journal identity. Existing unmonitored test scenarios continue; monitored code requires caller-supplied as-of price, FX and baseline information. Session IDs are **not trusted trading-calendar evidence** until E7. Risk estimates are model outputs and do not guarantee a maximum realized loss.

**See:** `docs/milestones/e3/E3_MONITORING.md`, `docs/RISK_EXECUTION.md`, `docs/ENGINE_IO.md`.
