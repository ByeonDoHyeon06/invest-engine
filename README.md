# invest-engine

**Engine first. Evidence before trading.**

국내·미국 주식 대상으로 시장 데이터, 전략, 위험관리, 주문·체결, 포트폴리오, 연구·자기개선을 분리한 독립형 적응형 트레이딩 엔진.

**현재 상태:** PLANNING (2026-11-15). 실거래 기능 없음. 개인용·headless·검증 우선.

## 설계 원칙
- 해상도 비종속: Tick/Quote/OrderBook/Bar/재무·공시 이벤트를 각각 정확한 타입으로 처리한다. 1분봉은 전략 설정이지 엔진 제한이 아니다.
- 브로커 비종속: 토스증권 연결은 어댑터. API 키 없이 Simulation부터 구현한다.
- 결정론적 코어: 같은 데이터·설정·버전·이벤트 순서는 같은 상태와 결과를 낸다.
- 책임 분리: 전략은 신호만 제안하며 Risk → Execution이 주문을 통제한다.
- Point-in-time: 당시 알 수 없었던 데이터, 과적합, 생존편향을 방지한다.
- 자기개선의 통제: Research가 후보를 탐색해도 운영 전략을 무승인 변경하지 않는다.
- 엔진 우선: UI/SaaS/고객 계좌 관리는 엔진 검증 이후로 미룬다.

## 프로젝트 문서 (진실 공급원)
- [현재 상태·다음 작업](docs/STATUS.md)
- [단계별 로드맵 및 완료 조건](docs/ROADMAP.md)
- [전체 아키텍처](docs/ARCHITECTURE.md)
- [기술 스택/선택 근거](docs/TECH_STACK.md)
- [도메인·이벤트·시간 계약](docs/DOMAIN.md)
- [전략·지능·연구](docs/STRATEGIES.md)
- [위험·주문·포트폴리오](docs/RISK_EXECUTION.md)
- [백테스트·Forward·검증 게이트](docs/VALIDATION.md)
- [외부 데이터·증권사 연동](docs/INTEGRATIONS.md)
- [개발·리뷰 규칙](docs/CONTRIBUTING.md)
- [ADR 인덱스](docs/adr/README.md)
- [작업 에이전트 가이드](AGENTS.md)

Roadmap은 순서와 완료 기준을, Status는 진행 상태를, ADR은 결정 근거를 기록한다. 실제 완료 여부는 테스트와 코드로 검증한다.

## 예정 순서
E0 기초 계약 → E1 데이터 → E2 이벤트 코어 → E3 모의 주문·위험·회계 → E4 전략 API/ORB → E5 백테스팅 → E6 리서치·자동 후보 평가 → E7 실시간 Paper/Shadow → E8 통제된 소액 실거래 → E9 후속 고도화.

**초기 제외:** 실제 주문, 자동 코드 수정/무검증 전략 배포, 대시보드, SaaS, HFT, 공매도·레버리지, 수익 보장.

**보안:** API key/secret/token, 계좌정보, 비공개 시세 원본은 저장소에 커밋하지 않는다. 공개/배포 권리가 있는 데이터 또는 합성 테스트 데이터만 사용한다.

## E0 — 오프라인 이벤트 검증기 (PR #11, 병합 전)

이 단계에는 **시장 데이터 수신·전략·백테스트·주문 기능이 없다**. 순수 합성 데이터의 이벤트 정렬·검증·결정론적 결과 해시만 제공한다.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
mypy src
invest-engine replay-synthetic --count 500 --market KR
invest-engine replay-synthetic --count 1000 --market US
```

정상적인 실행에서는 거래 0건, API 호출 0건이며 JSON에 count, events_by_type, state_hash가 출력된다. 해시의 같음은 **입력 이벤트의 정합/재현성**을 의미하지 매매 수익성을 의미하지 않는다. 

[구현 PR #11](https://github.com/ByeonDoHyeon06/invest-engine/pull/11) · [E0 Epic #1](https://github.com/ByeonDoHyeon06/invest-engine/issues/1)
