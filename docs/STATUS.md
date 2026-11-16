# 프로젝트 현황 및 재개 지점

**기준일:** 2026-11-16
**현재:** E0/E1/E2 VERIFIED. E3.1~3.3 PR #17~#19 main 병합·검증. **E3.4 PR #20 합성 세금/정산/감사 구현, CI 검토 중.** 실제 주문·전략·백테스트 없음.
**현재 Stage:** [E3 Issue #4](https://github.com/ByeonDoHyeon06/invest-engine/issues/4) IN PROGRESS · E3.4 [PR #20](https://github.com/ByeonDoHyeon06/invest-engine/pull/20) CI/REVIEW. **병합 전 E3 완료 처리 금지.**
**실거래 승인 상태:** NOT AUTHORIZED

## 완료된 E0/E1와 다음 실행 지점 (2026-11-15)

- E0 Epic: https://github.com/ByeonDoHyeon06/invest-engine/issues/1 (CLOSED)
- 병합 PR: https://github.com/ByeonDoHyeon06/invest-engine/pull/11
- Squash merge: https://github.com/ByeonDoHyeon06/invest-engine/commit/aae7bf7838c0abe8eeea6363461a358cb70db974
- **검증된 구현:** Python 패키지/CLI, InstrumentId·Money·Price·Quantity, MarketEvent 타입, UTC Clock, deterministic synthetic Replay, 기본 secret guard.
- **GitHub CI:** https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708153842 — Python 3.12 및 3.13 **각 37 passed**; Ruff / mypy / credential guard 통과.
- E0 범위: **계좌/주문/위험·거래전략/백테스트 없음**. Replay는 이벤트의 일관된 해시를 검증할 뿐 실제 체결 시뮬레이터가 아님.
- 로컬: Python 3.13에서 36 passed + Hypothesis 미설치로 1 skipped. CI는 Hypothesis 포함 37 passed.
- **검증 완료:** [PR #12](https://github.com/ByeonDoHyeon06/invest-engine/pull/12) — DataProvider/Normalizer/Quality/PIT 계약. GitHub CI [run 43712325371](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43712325371): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 전부 통과; PR #12 merged (13cb52d).
- **검증 완료:** [PR #13](https://github.com/ByeonDoHyeon06/invest-engine/pull/13), squash [1d8756c](https://github.com/ByeonDoHyeon06/invest-engine/commit/1d8756c6ae13fffdb79d39ecf33fdc0f9d443611). [GitHub CI 43713285009](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43713285009): Python 3.12/3.13 Ruff/mypy/pytest/secret guard 통과. 로컬 66 passed, 1 skipped(로컬 Hypothesis 미설치).
- **검증 완료:** [PR #14](https://github.com/ByeonDoHyeon06/invest-engine/pull/14), squash [77e7aab](https://github.com/ByeonDoHyeon06/invest-engine/commit/77e7aab5fb9433edbe53f084d800e52dd051cae2). [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109): Python 3.12/3.13 각각 76 passed + Ruff/mypy/secret guard. 로컬 73 passed, 3 skipped(로컬 의존성 미설치). Parquet 실제 저장/복원 테스트는 CI에서 실행됨.
- **E2 구현:** [PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) immutable State/Reducer + pure observation routing, DAG scheduler skeleton, SQLite event journal/atomic checkpoints/restart verification, fail-closed halt.
- **E2 CI:** [run 43834211614](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834211614): Python 3.12/3.13 각각 99 passed + Ruff/mypy/secret guard. 로컬은 96 passed, 3 skipped (선택 라이브러리 미설치).
- **E2 병합 증거:** [PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) squash commit [7d1b814](https://github.com/ByeonDoHyeon06/invest-engine/commit/7d1b814366cb5b4c4976db04ecbddf764c65ef82). 최종 PR CI [43834608280](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834608280), Python 3.12/3.13 각 99 passed, Ruff/mypy/secret guard green.
- **다음 단일 작업:** E3.4 [PR #20](https://github.com/ByeonDoHyeon06/invest-engine/pull/20)의 Python 3.12/3.13 CI·리뷰/호환성 검증, main 병합 및 E3 Issue #4 완료 Gate 검토. 그 후 [E4 Issue #5](https://github.com/ByeonDoHyeon06/invest-engine/issues/5) Strategy SDK 개발. 실제 브로커는 E8, 자동 체결 가격모델은 E5.
- 미래 개선 TODO: Decimal 자릿수/통화별 반올림 정책은 E3 money ledger 이전에 별도 ADR 결정. 단순 범위 제한된 속성 테스트를 모든 입력에 대한 임의 정밀도 보장으로 해석하지 말 것.
- LIVE: NOT AUTHORIZED, 브로커 주문 호출 경로 없음.

## 기술 선택 상태
| 주제 | 상태 | 출처 |
| --- | --- | --- |
| Event-driven deterministic core | 채택 | ADR-0001 |
| Resolution-agnostic market events | 채택 | ADR-0002 |
| Personal-first, broker-independent | 채택 | ADR-0003 |
| Research/Live 분리, 승인된 전략만 Live | 채택 | ADR-0004 |
| ORM/DB/메시징/모델 | 미확정 | 필요 시 ADR |
| 실제 토스 API 계약·Rate limit 상세 | 검증 필요 | INTEGRATIONS.md |
| 주문 실거래 허용 | 미승인 | E8 Gate |


## GitHub Epic 추적
- [E0 — Issue #1](https://github.com/ByeonDoHyeon06/invest-engine/issues/1)
- [E1 — Issue #2](https://github.com/ByeonDoHyeon06/invest-engine/issues/2)
- [E2 — Issue #3](https://github.com/ByeonDoHyeon06/invest-engine/issues/3)
- [E3 — Issue #4](https://github.com/ByeonDoHyeon06/invest-engine/issues/4)
- [E4 — Issue #5](https://github.com/ByeonDoHyeon06/invest-engine/issues/5)
- [E5 — Issue #6](https://github.com/ByeonDoHyeon06/invest-engine/issues/6)
- [E6 — Issue #7](https://github.com/ByeonDoHyeon06/invest-engine/issues/7)
- [E7 — Issue #8](https://github.com/ByeonDoHyeon06/invest-engine/issues/8)
- [E8 — Issue #9](https://github.com/ByeonDoHyeon06/invest-engine/issues/9)
- [E9 — Issue #10](https://github.com/ByeonDoHyeon06/invest-engine/issues/10)

## Pre-E3 인터페이스 검토 (2026-11-16)

- 문서: [Engine Run/Runtime I/O](ENGINE_IO.md), [ML 연구 I/O/검증](ML_RESEARCH.md), [ADR-0005 Proposed](adr/0005-io-contracts.md).
- 목적: E0~E2 시장 데이터 이벤트/저널은 구현되었지만 외부 RunRequest/RunResult, 주문 이벤트, AI PredictionResult API는 **미구현**임을 명확히 구분.
- 검토 상태: Design proposal (NOT MERGED until review). **E3 개발·Live 주문은 시작하지 않음**.
- E3 연결 시 E2 SQLite journal/codec가 MarketPayload만 지원하므로 버전 있는 확장·복구 테스트 필수.

## E3 진행 기록 (2026-11-16)

- [PR #16](https://github.com/ByeonDoHyeon06/invest-engine/pull/16) 입출력·ML 설계 문서 2026-11-16 병합 완료. ADR-0005 boundary 원칙 승인; Run/ML 구현은 추후.
- [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17) (MERGED): simulated-only OrderIntent/Fill/Portfolio Ledger, RiskLimits(cost basis), Decimal·currency precision (ADR-0006), 별도 versioned SQLite trading journal/outbox 및 복구, strict e3-sim-v1 JSON wire.
- E3.1 로컬 테스트: Python 3.13 **122 passed, 3 skipped**(Hypothesis/PyArrow 로컬 미설치). GitHub CI [run 43843169134](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43843169134) Python 3.12/3.13 Ruff/mypy/pytest/secret guard 모두 통과. [PR #17](https://github.com/ByeonDoHyeon06/invest-engine/pull/17) squash merged as [d49f95f](https://github.com/ByeonDoHyeon06/invest-engine/commit/d49f95f34001e0b0695e8565f1b14e1f108f231c).
- E3 잔여: mark-to-market equity/FX와 시장 세션 평가, 실시간 데이터로 모의 체결 결정하는 모델(E5), 실제 broker sync(E8), 전략/E2 통합 실행(E4~E5). E3 기간에는 적어도 **Pause/Cancel/Reduce/Flatten 명령** 및 위험 상태 정책을 후속 PR로 설계·검증해야 함.
- LIVE: NOT AUTHORIZED. 토스증권 API 모듈 없음.

## E3.2 진행 및 남은 E3.3 (2026-11-16)

- [PR #18](https://github.com/ByeonDoHyeon06/invest-engine/pull/18) (MERGED [96a2366](https://github.com/ByeonDoHyeon06/invest-engine/commit/96a2366a8f9dd57b33554ae08afe6ad28680779c)): 신규 BUY 일시중지/검토 후 재개, 확정 전 예약을 유지하는 일괄 취소 요청, 신선한 가격을 명시 입력받는 제한가 SELL 청산 *계획만* 생성. 새로운 이벤트 타입은 기존 E3 v1을 깨지 않도록 추가.
- 로컬 Python 3.13: **129 passed, 3 skipped**(Hypothesis/PyArrow 미설치). GitHub CI [43844743665](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43844743665): Python 3.12/3.13 각각 **132 passed**, Ruff/mypy/secret guard 성공.
- 다음 단계: Risk monitoring / stale market mark / daily-loss gate / reference broker account mismatch behavior 검증. 실제 시장·브로커 호출은 아직 없는 상태.

## E3.3 시세 평가·계좌 대조 (2026-11-16 · PR #19 MERGED)

- [PR #19](https://github.com/ByeonDoHyeon06/invest-engine/pull/19) **main 병합 / CI 검증 완료**: `MarketMark`, `FxMark`, session baseline, optional synthetic account reference, replayable `RiskObserved`/`AccountReconciliationReviewed`, daily-loss latch, marked equity/entry gate.
- 최종 PR CI [run 43849493669](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43849493669): Python 3.12·3.13 각각 **150 passed**, Ruff/mypy/secret guard 통과. [Squash merge d631e33](https://github.com/ByeonDoHyeon06/invest-engine/commit/d631e33f594448da6f73fac7b465fa0f05f9745b). 로컬 Python 3.13: **147 passed, 3 skipped** (Hypothesis/PyArrow 선택적 패키지 부재); CI에서는 둘 다 설치하여 3.12/3.13 수행.
- [E3_MONITORING.md](E3_MONITORING.md) · [ADR-0007](adr/0007-monitored-risk.md) · 금액/FX/세션 및 외부 스냅샷의 프로덕션 신뢰성은 후속 검증 항목.
- 실거래 연동 및 권한은 **NOT AUTHORIZED**; `require_monitoring=False` 기본값은 E3 합성 fixture 호환용이고 Live 안전성을 의미하지 않음.

## E3.4 — 합성 거래 세금·정산·Audit (2026-11-16)

- [PR #20](https://github.com/ByeonDoHyeon06/invest-engine/pull/20): sell_tax_rate (합성값), 명시적 매도대금 미결제금/현금 정산 이벤트, 각 Fill별 gross/fee/tax 장부, reducer invariants 감사. 문서 [E3_SETTLEMENT](E3_SETTLEMENT.md) · [ADR-0008](adr/0008-synthetic-settlement.md).
- 로컬 Python 3.13: **157 passed, 3 skipped** (Hypothesis/PyArrow 미설치). 이전 E3.3 코드로 작성한 SQLite 저널을 신코드에서 동일 해시/금액으로 복구했음.
- GitHub CI: 최초 PR commit 타입 검사 중 변수 범위 오류 발견 후 수정. 최종 검증/병합 전이며 이 문서는 완료 증거가 아님.
- 정산 방식은 실제 거래소 영업일이나 법적 세금 규정이 아닌 합성 확인 정책이며, 증권사 API나 실제 주문은 없음.

## 변경 기록
- 2026-11-16: E3.3 PR #19 squash merged `d631e33`, PR CI 43849493669 3.12/3.13 각각 150 passed. 잔여 E3.4 점검 후 E4로 이동 예정.
- 2026-11-16: [E2 PR #15](https://github.com/ByeonDoHyeon06/invest-engine/pull/15) squash merged (7d1b814); 최종 [CI 43834608280](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43834608280) Python 3.12/3.13 각 99 passed + Ruff/mypy/secret guard. E2 Issue #3 closed; E3 다음 단계.
- 2026-11-16: E2 코드 PR #15에서 통과(GitHub CI 43834211614). 문서/상태 반영 중, 병합 전. 라이브 기능 없음.
- 2026-11-15: E1.3 PR #14 squash merged (77e7aab), [CI 43714655109](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43714655109) Python 3.12/3.13 각각 76 passed. E1 전체 데이터 기반 검증, Issue #2 종료 및 E2 next.
- 2026-11-15: E1.3 PR #14 생성; immutable Parquet raw/normalized datasets, SHA256 및 provenance 명세. CI 검증 중.
- 2026-11-15: E1.2 PR #13 squash merged (1d8756c), GitHub CI 43713285009 양쪽 Python 버전 통과. E1.3 next.
- 2026-11-15: E1.2 PR #13 구현 중. 세션 기준 시간봉 재구성과 미국 DST/조기폐장 검증(로컬 66 passed + Hypothesis 미설치 1 skipped).
- 2026-11-15: E1.1 PR #12 squash merged (13cb52d), CI run 43712325371 양쪽 Python 버전 정상. E1.2가 다음 작업.
- 2026-11-15: E1.1 브랜치 feat/e1-ingestion-quality-pit 및 Draft PR #12 생성. 엄격한 공급자 원시데이터 정규화·feed quarantine·as-of 관측 경계 추가. 전체 E1은 미완료.
- 2026-11-15: 빈 저장소에서 비전/계획 문서 작성, E0 진입 예정.
- 2026-11-15: E0 도메인/이벤트/결정론적 replay 코드·CLI·테스트·CI 초안, Draft PR #11 (로컬 36 passed, 1 skipped).
- 2026-11-15: [CI run 43708332491](https://github.com/ByeonDoHyeon06/invest-engine/actions/runs/43708332491)에서 Python 3.12/3.13 각 37 passed 및 Ruff/mypy/secret 검사 성공. E0 검증 통과.
- 2026-11-15: PR #11 squash merged (aae7bf7); Issue #1 closed. E1 Issue #2가 다음 작업.

## 회차 종료·재개 기록 템플릿
- 날짜:
- 현재 E단계:
- 완료된 PR/commit:
- 검증 커맨드·결과:
- 미완료 작업:
- 블로커:
- 다음 단일 작업:
- 변경된 ADR:
- 라이브 안전 상태:

**에이전트 및 개발자는 새 작업 시작 전 README → STATUS → ROADMAP → 관련 설계/ADR을 읽고, 끝날 때 STATUS를 갱신한다.**
