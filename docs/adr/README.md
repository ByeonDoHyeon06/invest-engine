# Architecture Decision Records

설계를 변경하려면 기존 기록을 무언가 없었던 것처럼 수정하지 말고 새로운 ADR로 대체/수정 관계를 남긴다.

| ADR | 상태 | 주제 |
| --- | --- | --- |
| [0001](0001-engine-first.md) | Accepted | Engine-first + 결정론적 코어 |
| [0002](0002-event-resolution.md) | Accepted | 이벤트/시간/해상도 비종속 |
| [0003](0003-personal-first.md) | Accepted | 개인용 우선, 브로커 분리, SaaS 보류 |
| [0009](0009-strategy-boundary.md) | Accepted | 전략 SDK·ORB 연구 기준선·배분 권한 경계 |
| [0004](0004-controlled-adaptation.md) | Accepted | Research와 Live 분리 및 자기개선 통제 |
| [0005](0005-io-contracts.md) | Accepted | Run/Runtime/Prediction 입출력 경계 분리 |
| [0006](0006-monetary-rules.md) | Accepted (simulation) | 금액 반올림/호가/수량 및 비용기준 risk 정책 |
| [0007](0007-monitored-risk.md) | Accepted (simulation) | 시세·환율 관측 기반 위험 관리 및 대조 검토 |
| [0008](0008-synthetic-settlement.md) | Accepted (simulation; PR #20 CI verified) | 합성 매도 거래세, 미결제금, 확인 이벤트 및 장부 감사 |

각 ADR은 Context, Decision, Consequences, Alternatives, Revisit trigger를 포함한다. 날짜가 아닌 명시적 조건으로 변경 여부를 판단한다.

- [ADR-0010](0010-bar-fill-assumptions.md) — E5.1 보수적 바 체결, stop/target 미구현 범위 (Accepted research-only)

- [0011](0011-protective-ohlcv.md) — Accepted (offline simulation only): opt-in OHLCV stop-first/gap/volume model, no guaranteed execution.

- [0012](0012-audit-stress.md) — Accepted (offline research only): dataset audit, artifact integrity hashes and synthetic cost/liquidity stress; real data remain unverified.

- [0013](0013-point-in-time-fx-reporting.md) — Accepted (offline research): direct-pair as-of FX valuation, no order execution or implied buying power.

- [0014](0014-pit-universe-vintage-gate.md) — Accepted (offline research metadata gate only): fail-closed as-of membership/vintage and issuer-action coverage. Provider completeness/rights and corporate accounting not verified.

- [0015](0015-synthetic-corporate-action-ledger.md) — Accepted for synthetic/offline E5.7 research only: journaled issuer action/accounting and explicit CSV volume semantics; PIT action-aware backtest not yet authorized.

- [0016](0016-session-open-split-replay.md) — Accepted (offline research only): as-of session-open split with E3/E4 inventory parity and feature invalidation. All other issuer actions blocked.

- [0017](0017-dividend-research-replay.md) — Accepted offline research only: PIT entitlement/payment and net receivable; delisted holdings unsupported.\n\n- [0018](0018-delisting-terminal-bar-research.md) — Accepted (offline research): PIT-pinned unheld terminal delisting; held shares/unsettled orders fail closed, no implied recovery.\n
- [0019](0019-terminal-delisting-cash-receipt.md) — Accepted (offline research): witnessed net receipt for held delisting; later payments unsupported.

- [0020](0020-fixed-evaluation-window.md) — Accepted (offline research): strict warm-up/evaluation session boundary; real data validation remains open.

- [0021](0021-session-flat-research.md) — Accepted (offline research; PR #40 verified): opt-in first-fill comparator and schedule-bound session-flat protection.

- [0022](0022-fixed-fill-dated-fees.md) — Accepted for offline research (PR #41 verified): dated regulatory fixed-fill sensitivity.

- [0023](0023-dated-fee-replay.md) — Accepted for offline research (PR #42 verified): versioned fee-aware reserve and cumulative order charges.

- [0024](0024-independent-provider-diagnostic.md) — Accepted offline diagnostic (#43 verified; no eligible external strategy windows).

- [0025](0025-offline-candidate-gates.md) — Accepted offline research foundation (#44 verified only).

- [0026](0026-durable-research-journal.md) — Proposed: durable local experiment journal and provisional E5 report reconciliation.

- [0027](0027-temporal-walk-forward.md) — Proposed: deterministic temporal folds, label purge, embargo and logical final partition.

- [0028](0028-fixed-rule-fold-replay.md) — Proposed: fixed-rule, preregistered E5 replay across strict temporal validation folds.

- [0029](0029-causal-market-regimes.md) — Proposed: causal two-axis intraday regime annotations and fill attribution.

- [0030](0030-regime-exposure-cohorts.md) — Proposed: observed regime exposure denominators and quantity-cohort realized attribution.

- [0031](0031-bounded-parameter-grid.md) — Proposed: budgeted deterministic rule grid and validation replay.

- [0032](0032-search-lineage-stability.md) — Proposed: durable local search lineage, full outcomes and descriptive temporal-block stability.
