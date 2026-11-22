# Research evidence — historical runs and data audits

**This is the canonical index for historical experiment records, validation outcomes and data acquisition audits.** These are **not** SDK API specifications, strategy recommendations, or certified executable profits. Current project contracts live in [docs](../docs/README.md).

## Historical research plans

- [KR/US 80개 종목 연구 계획](plans/market_panel_v1.json): 당시 등록된 종목 구성, 학습·검증 기간 및 홀드아웃 예약 메타데이터. 실행 결과나 검증된 원시 시세는 아님.

## Historical study records (versioned aggregate only)

| Record | Run evidence | Result |
|---|---|---|
| [2022 ORB cost study](records/e6-2022-orb-pr53.json) | [Original report](reports/E6_PROFITABILITY_AUDIT.md) | 72 arms, 6 eligible windows, no profitable active candidate |
| [2021–2025 daily proxy](records/e6-2021-2025-daily-pr56.json) | [Original report](reports/ALPACA_DAILY_STRATEGY_PANEL.md) | 2,674 arms; all active hypotheses fail matched excess |
| [2022 raw-minute pilot](records/e6-2022-raw-minute-pr57.json) | [Original report](reports/ALPACA_RAW_MINUTE_PILOT.md) | 60 arms; modeled costs and corporate-action exclusions |
| [2023 fixed replication](records/e6-2023-frozen-replication-pr62.json) | [Original report](reports/E6_6_REDUCED_TURNOVER.md) | 168 arms; 0/112 active arms beat stronger comparator |

The [reports](reports/) retain original experiment narrative, protocols, negative findings, CI links and corrections. The [data audits](data/) preserve acquisition scope and limitations. 현재 브랜치에서 보고서 원문은 `evidence/reports/`와 `evidence/data/`만 유지하고, `docs/`의 중복 안내 파일은 제거합니다. 기존 PR의 오래된 경로는 병합 시 새 evidence 경로로 다시 연결해야 합니다.

## What is actually preserved?

- **Git:** reviewed report text, aggregate tables, failure/blocked classifications, public CI URLs and the machine-readable summary records in `records/`. The `source_report_original_git_blob_sha` is the Git object ID of the original report **not the market dataset SHA-256**.
- **E5 local/private run output:** the existing `run_experiment()` already writes `manifest.json` (including source and artifact hashes), `report.json`, `audit.json`, `decisions.jsonl`, `fills.jsonl` and `equity.jsonl`. Such content may have licensed data or position details; keep it under ignored private paths (`artifacts/`, `experiments/`, `data/`) and copy to explicitly permitted secure durable storage. GitHub Actions artifacts are temporary and cannot be the only retention mechanism.
- **NOT preserved by public records:** original raw SIP minute bars, true historical point-in-time vintages, corporate-action vendor truth, broker actual fills, real fees, or an independent unseen final holdout. A report record must never imply these exist.

## Policy for new experiments

1. Before running, record an immutable run ID, code/spec/dataset hashes, provider & license classification, time window, strategy/fee/fill model versions, comparator, and planned eligibility gates.
2. Keep private raw data and per-trade traces **outside Git**. The operator must explicitly determine retention/redistribution rights, storage owner, access control, encryption and TTL; do not automatically upload raw samples or private account records.
3. After executing, retain original E5 output manifest and artifact hashes in a secure private store with an immutable retention key, preserving complete artifacts where permitted. Hash-only/public summaries **do not reconstruct** missing raw data or per-order traces.
4. Promote only explicitly safe aggregate metrics and failure/eligibility summaries to `records/` with links to the corresponding versioned report/CI. Distinguish `BLOCKED`, `FAILED`, `NO_TRADE`, completed negative result and unfinished studies.
5. Validate repository records using `python scripts/check_evidence_records.py` and the project's pytest suite. Do not treat green CI, an aggregate PDF/Markdown table, or a modelled PnL as G1/G2 acceptance or permission for E7/E8.

**Historical archive decisions:** the complete original file content is retained under `reports/` and `data/`, and all prior Git commits remain available. Stubs are not duplicate report versions.
