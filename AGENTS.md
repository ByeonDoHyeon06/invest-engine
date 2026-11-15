# AGENTS.md — 작업 에이전트용 지속 컨텍스트

이 파일은 채팅 메모리에 의존하지 않고 invest-engine을 이어 개발하기 위한 작업 규칙이다.

## 매번 시작
1. README.md 읽기 (프로젝트 범위/원칙)
2. docs/STATUS.md 읽기 (현재 단계·다음 실행 항목·블로커)
3. docs/ROADMAP.md 읽기 (Epic 순서/DoD/의존성)
4. 수정할 모듈의 docs/ARCHITECTURE.md, DOMAIN.md, STRATEGIES.md, RISK_EXECUTION.md, VALIDATION.md, INTEGRATIONS.md와 docs/adr/ 읽기.
5. GitHub의 열린 Issue/PR/CI 확인하여 진행 중 작업·실패를 먼저 해결.

## 고정된 사용자 합의
- 1분 OHLCV는 코어 제한이 아니다: TradeTick, QuoteTick, Bar(임의 주기), 기업·공시·거시 관측까지 타입 안전하게 받아야 한다.
- 엔진 먼저: UI/SaaS보다 정확한 이벤트/자금/주문/백테스트 및 몇 주 Forward Paper를 우선.
- 국내·미국 주식, 초기 Long only/day trading, ORB는 최초 전략 실험용이며 수익이 검증된 전략이 아님.
- Tossspecific 구현은 독립 어댑터로; API key 없이 코어와 시뮬레이션을 구현.
- Adaptive 연구는 설계 핵심이나, 모델의 자율 실거래 변경·코드 수정·위험한도 완화 금지.
- 공시/재무정보는 선택적인 Feature Provider이며 Point-in-Time 필수.
- 개인용 headless 시작. SaaS 상용화·시세 재배포는 별도 라이선스/금융법 검토가 끝나기 전 추진하지 않음.

## 코드 아키텍처 규칙
- Domain / TradingCore / Strategy / Risk는 Broker SDK, DB, 네트워크를 직접 import 하지 않는다.
- Pure reducer + async I/O shell; 거래 상태 single-writer.
- 전략은 읽기전용 context → Signal; Risk를 우회한 주문 금지.
- 자료가 부족할 때는 가상의 세부 Tick/호가를 만들어내지 않는다.
- Decimal/aware UTC, 거래소 달력, available_at, 수익 계산 통화 분리.
- 동일 events/config/artifact = deterministic replay. 모든 실험 manifest 작성.
- outbox/idempotency/reconciliation은 Live 전에 필수.

## 작업 완료 시
- 실행한 테스트와 결과를 명확히 보고. 실행 못하면 그 사유 기록.
- docs/STATUS.md의 last commit/PR/next task/blocks/phase 업데이트.
- 해당 Epic의 체크박스는 실제 검증 증거가 있을 때만 체크.
- 계약 변경은 ADR 추가/기존 ADR 상태 변경. 주요 버전 반영.
- Live credential을 요청하거나 commit하지 않는다.

**현재 초기 단계:** E0. 실제 엔진 코드 없음. 자동매매 기능이 있다고 주장하지 말 것.
