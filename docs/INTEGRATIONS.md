# 외부 API · 데이터 소스 연동 계획

**상태:** 후보·통합 계약 정의. 실제 토스증권 연동은 E8에서 시행한다. E0~E5는 외부 인증키 없이 개발·테스트 가능해야 한다.

## 1. BrokerAdapter Protocol
핵심 엔진의 BrokerProtocol 인터페이스:
- submit_order(intent), cancel_order(broker_order_id), get_order, list_open_orders
- get_account/positions/balances, stream_order_events
- capabilities() → 지원 주문 유형/시간대/소수점/정정/조회/멱등성 범위
- health() → 인증/네트워크/시장 상태

SimBroker / PaperBroker / TossLiveAdapter가 구현. SDK별 인증/예외/식별자 변환은 Adapter에서 끝난다. 코어에서 토스 SDK 직접 import 금지.

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

**실거래 준비 체크리스트:** 사용자 본인 명시적 승인, 비밀키 로컬/서버 secrets에 저장, key rotation, outgoing IP 고정, 외부 주문/잔고 조회 consistency tests, paper→live 차이 로그, 비상정지 Runbook.

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
