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
