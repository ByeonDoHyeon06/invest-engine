# 개발 마일스톤 문서

기본 프로젝트 문서는 [docs/README](../README.md)에, **기능 단계별 명세와 사용 예제는 여기에** 둡니다.

| 단계 | 범위 | 시작 문서 |
|---|---|---|
| **E3** | 가상 거래·정산·위험·모니터링 | [Simulation](e3/E3_SIMULATION.md) · [Settlement](e3/E3_SETTLEMENT.md) · [Monitoring](e3/E3_MONITORING.md) |
| **E4** | 전략 신호 및 실행 인터페이스 | [Strategy](e4/E4_STRATEGY.md) |
| **E5** | Historical Backtest·경제적 검증 | [Backtest](e5/E5_BACKTEST.md) · [Experiment](e5/E5_EXPERIMENT.md) |
| **E6** | 후보 연구·시장 국면·Walk-forward | [Research Pipeline](e6/E6_6A_RESEARCH_PIPELINE.md) |
| **E6.7** | 신규 통합 SDK (아직 미구현) | [SDK 설계](e6.7/E6_7_UNIFIED_SDK.md) · [예제 23개](e6.7/E6_7_SDK_EXAMPLES.md) |

E3/E4의 기존 **저수준 Python 예제**도 각 단계 폴더에 함께 보존합니다. 반면 E6.7 예제집의 새 `Engine()` 호출들은 아직 설계 목표이며 현재 실행 가능한 API로 표시하면 안 됩니다.

실험의 과거 실행 결과·데이터 수집 감사·연구 계획은 [`evidence/`](../../evidence/README.md)에만 보관합니다. 기존 E5/E6 내부 API를 전면 통일하는 계획은 [ENGINE_IO](../ENGINE_IO.md)에 있으며, 새 SDK의 하위 호환 정책과 구분해야 합니다.
