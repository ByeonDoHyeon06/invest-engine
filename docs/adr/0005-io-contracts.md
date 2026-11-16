# ADR-0005: Explicit external I/O vs internal event contracts

- Date: 2026-11-16
- Status: Accepted (2026-11-16, boundary separation; Run/Prediction wire APIs remain proposed)
- Context: Pre-E3 Engine API gap; research reference https://codingapple.com/unit/deep-learning-stock-price-ai/

## Context
E0~E2 implemented typed market EventEnvelope, data processing, deterministic state transition/replay, SQLite journal. They did not establish a documented external RunRequest/RunResult interface, order/portfolio DomainEvent contracts or ML PredictionResult. E3 will add cash, order, fill, risk states. If it silently overloads market event schemas or treats all output as BUY/SELL, contracts will couple unrelated layers and break restart/replay semantics.

## Decision proposed
1. Three distinct boundaries: Run API (orchestration), Event/Command API (runtime), Prediction API (research).
2. Pure core remains State + DomainEvent + VersionedConfig -> State + Outcomes + Commands (no side effects). Shell delivers commands/results as events.
3. Explicit typed outcomes OK, NO_ACTION, REJECTED, DATA_UNAVAILABLE, UNSUPPORTED, HALTED, FAILED. DecisionTrace links event/feature/strategy/risk/order/fill.
4. Decimal string + ISO UTC timestamp + versioned typed payloads as wire serialization conventions; Python dataclasses/Protocols remain internal API. Input availability and market instrument identity are preserved.
5. E3 extends event payloads/codec/journal via versioned migration, not unchecked storage of dict blobs, and does not introduce strategies/ML/backtest prematurely.
6. ML predictor emits a target/horizon/value/uncertainty/ABSTAIN artifact, not an order. Strategy may use it, Risk and Execution remain the only path to a broker.
7. All hypothetical JSON examples are marked DRAFT and must not be described as implemented until validation tests exist.

## Alternatives considered
- A single gigantic trade(inputs) -> BUY/SELL/SELL_NOW function: lacks reproducibility, risk/account separation, no-trade outcome.
- Direct Broker API from AI strategy: invalidates Risk boundary and event journal safety.
- Fixing a single 1m OHLCV schema: violates ADR-0002 and limits future ML signals/market data resolution.
- Building public FastAPI/HTTP before Python core contract: needless scope at current stage.

## Consequences
Greater clarity and potential JSON migration work during E3; prevents APIs from silently binding to Toss/1m bars or over-promising model predictions. Tests can validate golden fixtures and deterministic replay through E3+. Independent ML work can be deferred to E6 without rearchitecting order execution.

## Review gates
- Verify current codec/journal compatibility & migration strategy.
- Approve E3 money/rounding and account/order/fill invariants.
- Verify schema golden fixtures and error cases.
- Accept ADR before marking E3 contracts stable; until then external JSON is design proposal.

## Reference specifications
- docs/ENGINE_IO.md
- docs/ML_RESEARCH.md
- docs/DOMAIN.md
- docs/RISK_EXECUTION.md
