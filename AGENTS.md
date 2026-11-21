# AGENTS.md — 작업 에이전트용 지속 컨텍스트

**Latest / 2026-11-21:** #65 multi-symbol intraday foundation PR 1 is implemented on local branch `feat/multisymbol-portfolio-contracts`; initial implementation ends at `0049b56` and final-review fixes/documentation are at the branch tip. Fixed-universe explicit-watermark frames and portfolio batch validation only. Local 433 tests, Ruff, mypy 78 files, secret/diff checks pass; PR/CI pending. PR 2 shared-account backtest and PR 3 strategy/data study remain unimplemented. #62/#63 are separate green Draft PRs. E5 #6 / E6 #7 OPEN; LIVE NOT AUTHORIZED. Read [STATUS](docs/STATUS.md) for authoritative state.


이 파일은 채팅 메모리에 의존하지 않고 invest-engine을 이어 개발하기 위한 작업 규칙이다.

## 매번 시작
1. README.md 읽기 (프로젝트 범위/원칙)
2. docs/STATUS.md 읽기 (현재 단계·다음 실행 항목·블로커)
3. docs/ROADMAP.md 읽기 (Epic 순서/DoD/의존성)
4. E3 이하 개발 전 docs/ENGINE_IO.md · docs/ML_RESEARCH.md · docs/E3_SIMULATION.md · docs/E3_MONITORING.md · docs/E3_SETTLEMENT.md · ADR-0005/0006/0007/0008을 확인한다. E3의 엄격한 주문 JSON만 구현돼 있고, Run/Prediction JSON 예시는 아직 설계안이다.
5. 수정할 모듈의 docs/ARCHITECTURE.md, DOMAIN.md, STRATEGIES.md, RISK_EXECUTION.md, VALIDATION.md, INTEGRATIONS.md와 docs/adr/ 읽기.
6. GitHub의 열린 Issue/PR/CI 확인하여 진행 중 작업·실패를 먼저 해결. 의존 PR은 선행 검증 후 병합 또는 명시적 보류 사유를 기록한다.

## 고정된 사용자 합의
- 1분 OHLCV는 코어 제한이 아니다: TradeTick, QuoteTick, Bar(임의 주기), 기업·공시·거시 관측까지 타입 안전하게 받아야 한다.
- 엔진 먼저: UI/SaaS보다 정확한 이벤트/자금/주문/백테스트 및 몇 주 Forward Paper를 우선.
- 국내·미국 주식, 초기 Long only/day trading, ORB는 최초 전략 실험용이며 수익이 검증된 전략이 아님.
- Toss-specific 구현은 독립 어댑터로; API key 없이 코어와 시뮬레이션을 구현.
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

## E6.7 통합 SDK 계획 (Issue #59)
- 사용자 확정 API: `Engine()` 기본 생성자는 중립적이고 I/O 없는 구성 진입점. `Engine.offline()/online()/research()` 형태나 필수 mode 인자를 도입하지 않는다. 기능 호출(백테스트/연구/판단/향후 Paper/Live)에서 목적·권한을 구분한다.
- [SDK 코드 예제 18개](docs/E6_7_SDK_EXAMPLES.md)는 구현 목표 계약이다. 구현 단계에서 임의로 API 명칭·기본값·권한 모델·호환성·예제를 변경하지 않는다. 변경 필요 시 먼저 사용자 승인 + ADR/명세/이슈/로드맵/예제/계약 테스트를 함께 갱신한다. 미지원 예제는 미지원으로 표시하며 기능을 숨기거나 안전 제한을 풀지 않는다.
- [계획](docs/E6_7_UNIFIED_SDK.md) / [ADR-0034](docs/adr/0034-unified-sdk.md): E7 전 별도 오프라인 SDK 단계. 현재 #57 병합 완료, 저빈도 전략/증거 검증 우선; 계획 추가만으로 구현 완료 또는 실거래 승인 아님.
- 단순 API와 고급 API는 같은 typed spec·검증 경로·기존 코어를 사용한다. SDK에서 내부 모듈 기능을 제거하거나 위험/증거 게이트를 우회하지 않는다. 기본값은 명시적 버전 프로필로 공개하고 기능 동등성/기존 CLI 호환성을 테스트한다.

## 다중종목 인트라데이 연구 기반 (Issue #65)

- [설계](docs/superpowers/specs/2026-11-20-multisymbol-intraday-slot-momentum-design.md)와 [ADR-0035](docs/adr/0035-multisymbol-portfolio-decision-boundary.md)가 권위 있는 경계다. 기존 `StrategyRunner`/`HistoricalBacktest` 계약은 변경하지 않는다.
- PR 1 로컬 구현은 `UniverseFrameCoordinator`의 명시적 watermark, 완전한 고정 universe, `DATA_UNAVAILABLE`/`NO_ACTION` 분리, late-data halt와 `PortfolioStrategyRunner`의 ordered complete-target/trigger/노출 상한 검증까지만 포함한다.
- 결측 종목을 빼고 순위를 계산하거나, watermark 뒤의 bar로 과거 frame을 고치거나, 플러그인 출력을 정렬·수선하지 않는다. 복구는 신뢰된 저널 replay로 새 coordinator를 구성한다.
- 다음 단일 구현은 **PR 2 공유계좌 역사 backtest 조정·position-cycle 보고·기존 hash 호환성**이다. `xs-slot-momentum@1.0.0`, controls 및 실제 데이터 연구는 PR 3 전까지 구현·검증됐다고 쓰지 않는다.
- 현재 근거는 로컬 433 tests/Ruff/mypy 78 files/secret guard뿐이며 PR/CI는 없다. 수익성, 실제 체결 가능성, Paper/Live 권한을 의미하지 않는다.

## E5 연구 엔진 경계
- docs/E5_BACKTEST.md 및 ADR-0010 참고. E5.1은 보수적 Bar LIMIT 모델이지만 실제 체결 가능성을 보장하지 않는다.
- 보고서 PnL은 통화별로 분리, FX 미확인 시 자동 합산 금지. 신호생성 봉과 동일한 봉에서 체결 금지.
- E5.1 (PR #23)은 병합. E5.2 (PR #24)은 오프라인 CLI/실험 manifest. E5.3 stop/target·갭 모델 검증 전 E5 전체를 완료라고 표시하지 않는다.
- 실제 브로커 연결은 E8 승인 전 금지.

## 작업 완료 시
- 실행한 테스트와 결과를 명확히 보고. 실행 못하면 그 사유 기록.
- docs/STATUS.md의 last commit/PR/next task/blocks/phase 업데이트. docs/ROADMAP.md와 해당 Epic Issue에도 동일한 검증 근거 및 미완료 조건을 반영한다.
- PR 본문에 해당 Issue, 변경 문서, CI/실험 근거, 병합 조건을 명시한다. 실행 중인 작업은 pending으로 기록하고, 결과 확인 후 상태/문서를 정리하기 전 다음 작업을 완료 처리하지 않는다.
- 개별 기능 문서와 ADR에 남은 candidate/pending 상태도 실제 병합·검증 결과에 맞춘다. 합성 검증과 실제 데이터/경제적 적격성은 구분한다.
- 해당 Epic의 체크박스는 실제 검증 증거가 있을 때만 체크.
- 계약 변경은 ADR 추가/기존 ADR 상태 변경. 주요 버전 반영.
- Live credential을 요청하거나 commit하지 않는다.

**현재 단계:** E0~E4 완료. E5.1~E5.4 오프라인 백테스트/감사·비용 민감도 검증(PR #23~#26). **다음 E5.5 실제 데이터·비용·FX/기업행동 검증 게이트**, Issue #6 OPEN. STATUS/ROADMAP/PR/CI 먼저 확인.

## E3 구현 경계 및 남은 작업
- E0~E2의 EventEnvelope는 시장 데이터용. E3는 별도 trading_event/event journal namespace에서 simulated order/fill을 구현; E2 시장 이벤트에 대한 실전 주문 전략 통합은 E4/E5 후속 작업.
- 외부 Run API, 내부 Event/Command API, 미래 Prediction API는 서로 다른 계약. ML 출력은 주문이 아니다.
- NoAction / Rejected / DataUnavailable / Halted는 반드시 구분하고 reason_codes·decision trace를 보존한다.
- E3 범위는 simulated order/risk/portfolio 및 외부 계약 fixtures. 예측 모델은 E6 이후에 연구한다.

**현재 재개 지점:** [E3 Issue #4](https://github.com/ByeonDoHyeon06/invest-engine/issues/4), E3.1/2/3 [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17)/[#18](https://github.com/ByeonDoHyeon06/invest-engine/pull/18)/[#19](https://github.com/ByeonDoHyeon06/invest-engine/pull/19) 모두 main 병합. **E3.4 PR #20은 CI 검증 후 main 병합 완료. 다음 E4 Strategy SDK**로 이동. 수익성 검증/전략·Market→Order 자동연결/실거래 기능 없음.

## E3.4 합성 정산 정책
- 기본 IMMEDIATE는 기존 E3 저널과 호환. EXPLICIT_CONFIRMATION은 매도대금 net을 unsettled에 기록하고 CashSettlementConfirmed 이벤트 이후 settled/available로 이동.
- sell_tax_rate는 합성 테스트 비율일 뿐 실제 법적 거래세·토스 수수료가 아님. 수수료·가산세와 정산정책은 버전/저널 identity에 고정.
- 거래소 영업일 T+N, 실제 broker buying power, 실계좌 연동 및 실제 세금정산은 E7/E8 이후 검증.
- 모든 거래 reducer 상태전이에서 cash/주문/포지션/체결/미결제금 불변식을 감사. E4는 E3 실거래 인증을 전제하지 않음.

## E4 시작 조건 (2026-11-16)
- E3는 수동 합성체결 기반 모의 주문/위험/장부 핵심을 검증했으며, 전략→시장 데이터→주문 자동 연결은 아직 없다.
- E4는 `StrategyManifest`, DataRequirements, 읽기 전용 Context, StrategySignal, FeatureGraph와 ORB baseline을 먼저 구현한다. 직접 브로커 접근, 자기개선 자동승격 및 실제 주문 기능은 금지.
- E3.4 성공: [PR #20](https://github.com/ByeonDoHyeon06/invest-engine/pull/20), [CI 43852453688](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43852453688), 기존 E3.3 SQLite journal 해시·잔고 호환성 확인. 합성 세금/정산과 실제 거래소 규칙을 혼동하지 않는다.

## E4 현재 작업 (2026-11-16)
- [PR #21](https://github.com/ByeonDoHyeon06/invest-engine/pull/21): Strategy SDK/FeatureRegistry/ORB/NoTrade/target allocator. E3 모의 주문에는 **제안만** 연결; 실제 체결 결정은 E5 이후.
- E4 전략은 신뢰할 수 있는 내부 Python 플러그인만 허용; Protocol은 샌드박스가 아님.
- E4 필수 검증: 과거 관측만 입력, 시간봉 구성/거래세션/워밍업, 20 이전 세션 거래량, 다중 전략 상한, 신호 결정론.
- E4 잔여: Fill 귀속 strategy-level virtual ledger와 실행·신호 영속 경계 평가. STATUS/ROADMAP 참조. E4 Issue #5를 근거 없이 닫지 말 것.

## Latest state (2026-11-16, supersedes earlier E4 TODO)
- E0~E4 verified and merged. PR #21 strategy SDK + ORB, PR #22 synthetic fill attribution; CI run 43857703057: Python 3.12/3.13 each 191 passed, Ruff/mypy/secret guard green.
- E4 virtual positions are in-memory and research-only. No automatic market fills, brokerage interaction or integrated E2/E4/E3 replay.
- NEXT: E5 Issue #6. First implement deterministic coordination and transaction/recording boundary for strategy signals, allocation tickets and simulated fills, then conservative OHLCV fill+fees/slippage, baseline report and experiment manifest.
- Trusted internal strategies only; no Python code sandbox. LIVE NOT AUTHORIZED.

## E5.3 protection boundary (2026-11-17)
- Read `docs/E5_PROTECTION.md` / ADR-0011 before changing bar-fill/protection logic.
- Protective stop/target is opt-in offline stress approximation, not a broker order; activated only **after** a confirmed entry Fill observation, never same entry bar.
- Unknown bar path uses stop-first, opening gap may be worse than planned stop; target requires strict penetration and adverse fill assumptions; all price/volume assumptions are version-pinned.
- If a competing existing SELL order conflicts with a protective trigger in the same OHLCV bar, fail with explicit InvalidEvent; do not fabricate a causal ordering.
- E5 is still in-progress pending full robustness/data provenance/cost/FX gates; no Live transport.

## E5.4 이후 지속 개발 규칙
- [E5_ROBUSTNESS.md](docs/E5_ROBUSTNESS.md) · ADR-0012 참조. 4종 비용/유동성 스트레스는 합성 연구 가정이며 실제 브로커 체결/수수료의 검증 결과가 아니다.
- data audit은 누락 Bar/partial session과 파일 해시만 검사한다. Corporate actions, PIT issuer/universe, 법적 데이터 라이선스, 실거래 비용·FX는 명시적으로 UNVERIFIED 처리한다.
- 실험 manifest의 사용자 선언 code_sha와 실제 소스트리 sha256은 다르다. 암호서명이나 공급자 원본의 진위를 보증한다고 주장하지 않는다.
- E5 Issue #6은 남은 PIT/FX/비용/Quote·Tick 모델 범위 결정을 완료하기 전까지 닫지 않는다. Live 금지.

### E5.5 FX reporting guard
- docs/E5_FX_REPORTING.md: research-only direct-pair as-of FX marks. Never use converted equity as broker buying power or E3 risk input.
- Missing/stale/unreleased FX implies null base-currency PnL/drawdown; do not silently invert, interpolate, backfill or convert.
- E5 real provider fees, corporate actions, point-in-time universe and tick/quote fill verification gates remain OPEN. LIVE NOT AUTHORIZED.

## E5.6 point-in-time research gate (2026-11-17)
- [PR #28](https://github.com/ByeonDoHyeon06/invest-engine/pull/28), [E5_PIT_EVIDENCE.md](docs/E5_PIT_EVIDENCE.md), [ADR-0014](docs/adr/0014-pit-universe-vintage-gate.md): source-declared membership/vintage/corporate-action catalogue proof is an optional, strictly validated research-only boundary.
- A split, dividend, delisting, merger or symbol change effective in a test window **blocks the whole experiment**, not an individual symbol. This cannot silently filter out delisted firms. Never create prices/dividends/adjustment ratios.
- Metadata hashes/declared dates DO NOT authenticate provider origin, historical universe completeness or rights. Source may be dishonest; all source-release flags remain false. E5 and real market readiness gates stay OPEN.
- E5.6 only validates input metadata; no broker/Live route or E6 automatic strategy promotion.

**E5.6 verified PR CI:** [GitHub Actions 44057468935](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44057468935) passed 245 tests on Python 3.12/3.13, Ruff, mypy and basic secret guard. Next E5.7: independent provider vintage, corporate-action adjusted portfolio accounting, real market fee/tax validation and Tick/Quote execution. Do not mark E5 or Live as verified.

## E5.8 research replay guard (2026-11-17)
- [PR #30](https://github.com/ByeonDoHyeon06/invest-engine/pull/30), [CI 44067166215](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/44067166215). Strict SHA/PIT matched session-open RAW_UNADJUSTED share split only.
- E3/E4 quantity and cost basis parity; invalidate E4 pre-split feature history; reject dividends, delistings, mergers, intraday actions and active protective-lot modeling.
- docs/E5_SPLIT_REPLAY.md and ADR-0016 authoritative. Provider completeness / price convention remain caller-attested, not independently verified. E5 Issue #6 OPEN; LIVE not authorized.

### E5.9 dividend replay boundary (2026-11-17)
- [E5_DIVIDEND_REPLAY.md](docs/E5_DIVIDEND_REPLAY.md) / ADR-0017: PIT/SHA-gated ex-date entitlement at witnessed session-open; payment at a later witnessed bar.
- Net unpaid dividend contributes to research equity but never E3 buying power. Raw unadjusted bars required; tax fraction synthetic.
- PIT delisting/merger remains fail-closed without verified settlement proceeds. E5 Issue #6 OPEN, LIVE NOT AUTHORIZED.

### E5.9 verified status and next gate (2026-11-17)
- [PR #31](https://github.com/ByeonDoHyeon06/invest-engine/pull/31) main merged 963743d. main CI 44070594750: 3.12/3.13 275 passed each; lint/type/secrets passed.
- Next E5.10: decide validated issuer-delisting cash resolution or preserve fail-closed; obtain licensed actual-share-volume 1m market data and independent corporate action and fee provenance before ORB conclusions.
- E5 Issue #6 stays OPEN. E7 realtime forward paper and E8 live remain unimplemented/unauthorized.


## E5.11 verified and next gate (2026-11-19)
- PR #34 merged 7c2e733; PR CI 44489789537: Python 3.12/3.13 each 291 passed; Ruff/mypy/secrets passed.
- Terminal receipt is synthetic research only: exact delisting ID + instrument binding and explicit witnessed cash; no fabricated recovery, no late payment model.
- NEXT E5.12: licensed actual-share-volume 1m history with 20 warm-up sessions + one fixed evaluation month; verify source, market coverage, calendar, issuer actions, costs and compare ORB vs predeclared baselines. E5 remains OPEN if evidence is missing.
- Account authority boundary: the existing E3 ledger is authoritative only for simulated BACKTEST/PAPER accounts; a future live account uses verified read-only broker snapshots as the asset source of truth, not an engine-owned parallel asset ledger. Stale/inconsistent data and unknown orders block new exposure; durable order/audit records serve reconciliation, not replacement of broker balances. No live authorization.


## E5.12 verified and next data gate (2026-11-19)
- PR #36 merged 3146b96; PR CI 44492013440 Python 3.12/3.13 each 298 passed; lint/type/secrets passed.
- Strict fixed-window experiment is single-instrument, one-minute, declared RAW_UNADJUSTED/SHARES/PIT, no issuer actions; history-only warmup does not invoke strategies or generate orders or equity. All external verification flags remain false.
- E5.13: obtain actual permitted bars and run a predeclared one-month study plus 20 prior sessions; independently verify data and cost provenance. Report provisional studies as such; never fabricate PIT timestamps/evidence. E5 Issue #6 stays OPEN, E6 promotion blocked, no LIVE.

## E5.14a verified; E5.14b / E5.15a next (2026-11-19)
- PR #40 merged 1d63a3c; Core CI 44497904693 311 tests per Python. Provisional results in docs/E5_14B_FEE_AUDIT.md. E5.14b.1 fixed-fill costs only, not cash/risk ledger; E5.15a fixed Aug/Dec expansion; complete fees and broader source evidence before E5 release. LIVE NOT AUTHORIZED.
