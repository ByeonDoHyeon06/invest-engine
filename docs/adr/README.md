# Architecture Decision Records

설계를 변경하려면 기존 기록을 무언가 없었던 것처럼 수정하지 말고 새로운 ADR로 대체/수정 관계를 남긴다.

| ADR | 상태 | 주제 |
| --- | --- | --- |
| [0001](0001-engine-first.md) | Accepted | Engine-first + 결정론적 코어 |
| [0002](0002-event-resolution.md) | Accepted | 이벤트/시간/해상도 비종속 |
| [0003](0003-personal-first.md) | Accepted | 개인용 우선, 브로커 분리, SaaS 보류 |
| [0004](0004-controlled-adaptation.md) | Accepted | Research와 Live 분리 및 자기개선 통제 |
| [0005](0005-io-contracts.md) | Accepted | Run/Runtime/Prediction 입출력 경계 분리 |
| [0006](0006-monetary-rules.md) | Accepted (simulation) | 금액 반올림/호가/수량 및 비용기준 risk 정책 |
| [0007](0007-monitored-risk.md) | Accepted (simulation) | 시세·환율 관측 기반 위험 관리 및 대조 검토 |

각 ADR은 Context, Decision, Consequences, Alternatives, Revisit trigger를 포함한다. 날짜가 아닌 명시적 조건으로 변경 여부를 판단한다.
