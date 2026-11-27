# 외부 API · 데이터 소스 연동 계획

**상태:** 후보·통합 경계 정의. 실제 토스증권 주문 API는 **별도 외부 Execution Host/Adapter 프로젝트**에서만 구현 대상이다. E8은 그 외부 연동을 별도로 승인·검증할 수 있는 단계이고, Engine SDK는 실주문을 지원하지 않는다. 엔진 개발/Simulation/Research/Evaluate/Session은 증권사 **주문용** 인증키 없이 사용 가능해야 한다.

## 1. External BrokerAdapter Protocol (optional integration)
기존 저수준 BrokerProtocol 타입의 계약은 외부 Host의 통합 경계/호환을 위한 것으로, Engine SDK의 실제 주문 실행 권한을 뜻하지 않는다:
- submit_order(intent), cancel_order(broker_order_id), get_order, list_open_orders
- get_account/positions/balances, stream_order_events
- capabilities() → 지원 주문 유형/시간대/소수점/정정/조회/멱등성 범위
- health() → 인증/네트워크/시장 상태

SimBroker/PaperBroker는 **합성/가상** 체결 도구이며 TossLiveAdapter 같은 실주문 어댑터는 외부 패키지/프로세스에서만 구현한다. 증권사별 인증·요청·예외·계좌/주문 식별자 변환 및 실주문 조회/대조는 외부 Host 책임. Engine SDK의 네 기본 공개 실행 API에는 실제 `submit_order` 또는 `cancel_order` 효과를 추가하지 않는다.

## 2. Toss Securities Open API (검증 대상)
공식 문서:
- https://developers.tossinvest.com/docs/auth
- https://developers.tossinvest.com/docs/market-data
- https://developers.tossinvest.com/docs/connection
- https://developers.tossinvest.com/docs/order-event
- https://developers.tossinvest.com/openapi-docs/latest/openapi.json
- https://developers.tossinvest.com/openapi-docs/latest/asyncapi.json

공식 가이드에서 OAuth2 token, 허용 IP, REST current prices/orderbook/trades/candles, WebSocket 시세/주문 이벤트 지원을 확인. 문서 스키마는 **실제 개발 시 다시 내려받아 버전/해시 고정**한다.

주의:
- API 인증은 등록된 허용 공인 IP에 묶일 수 있어 초기 클라우드 고정 송신 IP 방안 필요.
- access token 중앙 관리, 만료·인증 오류 처리. 중복 발급 및 토큰 경쟁 방지.
- WebSocket subscribe ack, keepalive, 연결 수/구독 수 한도는 최신 스펙에서 테스트.
- REST Rate Limit은 엔드포인트/그룹/응답 헤더 중심으로 동적 적용; 코드에 추정한 초당 요청 숫자 하드코딩 금지.
- 1분봉/일봉 캔들 API는 최대 200개/요청 및 페이지네이션 제공. 충분한 과거 분봉 데이터 보유 여부는 미검증.
- 실시간 미국 데이터는 적용 거래소 범위 확인. 통합 NBBO나 체결 보장 가정 금지.
- 주문 timeout은 주문 미접수의 증거가 아니며, 주문 조회/계좌 대조·idempotency policy 필수.
- KR/US session/calendar, 시장별 TIF, 주문 정정, 현금 결제/달러 보유/수수료/세금 적용 가능성 검증.

**외부 Host 실거래 준비 체크리스트 (Engine SDK 범위 외):** 사용자 본인 명시적 승인, 비밀키 독립 보관/회전, 고정 egress IP, 외부 주문/잔고 정합성, 영속 outbox/idempotency/UNKNOWN 상태 복구, Paper↔외부 실행 결과 비교, 킬스위치 Runbook. SDK가 제공하는 결정/OrderIntent는 승인되거나 전송된 주문이 아니다.

## 3. 시장 데이터 공급자
- Toss는 개발/실시간 데이터 후보지만 수년치 체결·분봉의 완전한 공급원으로 전제하지 않음.
- historical 데이터는 허가받은 공급자 또는 공개 배포가 허용된 자료로 수집; source·license·coverage·timezone·revision을 manifest에 기록.
- 사업화 전 시세 원본/재가공물 이용·재배포 권한 별도 계약 확인. 개인용 API/시세를 SaaS 기본 데이터 파이프라인으로 사용할 계획 없음.
- 백테스트 예제는 합성/사용 허가된 데이터 사용; 실제 계좌 관련 로그 공개 금지.

## 4. 기업·공시 데이터
KR: 금융감독원 OpenDART — https://opendart.fss.or.kr/intro/main.do
US: SEC EDGAR APIs — https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- 공시/재무 데이터는 회계기간 vs filed/published/available-at을 반드시 구분.
- 정정 신고/데이터 빈티지, 단위(원/달러/천단위 등), 회사 식별자(CIK/corp_code) 유지.
- SEC 등 제공자의 자동접근·rate/fair-access 정책 준수.
- LLM 추출 결과는 출처/문서 인용·정형 데이터 검증. 실거래 주문권한 없음.

## 5. 인증/보안/라이선스
- GitHub 저장소에는 API key, secret, bearer token, 실제 주문/계좌 정보 업로드 금지.
- .env 같은 secret 파일, raw proprietary market data, 실험 산출물에 계좌식별정보가 포함되면 제외.
- 라이선스/계약/법률 검토 없이 3자 자동매매 SaaS/시세재배포 금지.
- SEC/DART의 이용 정책 및 Toss Open API 최신 약관을 검증 항목으로 유지; 문서 링크만으로 상용 이용허락을 추정하지 않음.

## 4. SDK와 외부 실행 서비스 분리 (2026-11-22)

- **Engine:** `simulation(...).historical()`, `simulation(...).paper()`, `research(...)`, `evaluate(...)`, `session(...)`를 통해 분석/가상 계좌 시뮬레이션/판단 제안을 제공한다. `engine.live`, `simulation(...).live()`와 실제 주문·증권사 인증 I/O를 제공하지 않는다.
- **외부 Execution Host:** 별도 브로커 API 어댑터, 실주문 승인, 주문 outbox/재시도·대조, 계좌 원본, 권한·비밀키·감사·킬스위치를 담당한다. 엔진의 제안만으로 주문이 실행되지 않는다.
- **연동 계약:** 외부 앱이 공급하는 검증된 계좌/주문 관측 이벤트는 엔진 입력으로 사용할 수 있으나 실계좌의 권위 있는 원본은 브로커다.
- **E8:** 선택적 외부 연동 검증 단계. 기존 저수준 BrokerProtocol 타입을 일괄 제거하거나 실주문 실행기를 코어 안에 이식한다는 뜻이 아니다.
