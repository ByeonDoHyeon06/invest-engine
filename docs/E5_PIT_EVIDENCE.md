# E5.6 — Declared Point-in-Time Universe, Vintage and Corporate Action Gate

**Status:** Implemented strict metadata preflight for *offline research only*. It is **not** a historical data provider, corporate-action accounting engine, survivorship-bias certification, exchange authority, or live-trading authorization.

## Problem

An adjusted historical OHLCV dataset may contain prices revised using facts not available at a past decision time. A today's-constituents-only dataset omits delisted firms. Splits, dividends, mergers and symbol changes can invalidate portfolio valuation if the engine ignores them. A simple checksum proves immutability of supplied bytes, **not** that a provider's content was historically correct.

## Contract (optional for legacy synthetic research, opt-in fail-closed)

`e5-research-v1` CLI accepts an additional **optional** top-level object:

```json
"pit_evidence": {
  "records_jsonl": "pit.jsonl",
  "sha256": "<SHA-256 over exact JSONL bytes>",
  "source": "synthetic-evidence-provider",
  "license": "synthetic-test-only"
}
```

The evidence file has one JSON object per line, with **exact** keys depending on `kind`. Dates must be RFC3339 **UTC** (`Z` or `+00:00`), hashes lowercase hex SHA-256. Every market event requires a `vintage` record pointing to the SHA-256 of its canonical full `EventEnvelope` bytes (including event ID, times and ordinal).

```json
{"kind":"membership","instrument_key":"KR:KRX:SYN-E5","effective_from":"2026-11-15T00:00:00Z","effective_until":"2026-11-18T00:00:00Z","published_at":"2026-11-14T00:00:00Z","received_at":"2026-11-14T00:00:00Z","source":"synthetic-universe","included":true}
{"kind":"action_coverage","instrument_key":"KR:KRX:SYN-E5","start":"2026-11-16T00:00:00Z","end":"2026-11-16T02:00:00Z","published_at":"2026-11-15T00:00:00Z","received_at":"2026-11-15T00:00:00Z","source":"synthetic-issuer-catalog"}
{"kind":"vintage","event_id":"e0","payload_sha256":"<actual canonical EventEnvelope hash>","revision":"v1","published_at":"2026-11-16T00:01:00Z","received_at":"2026-11-16T00:01:00Z","source":"synthetic-bars"}
```

A fourth `kind` is `corporate_action`: `action_id`, `instrument_key`, `action_type` (`SPLIT`, `CASH_DIVIDEND`, `DELIST`, `MERGER`, `SYMBOL_CHANGE`), `effective_at`, `published_at`, `received_at`, `source`.

**Checks:**

- One unambiguous **included**, already-published/received membership window per market event at that observation time. Missing memberships and future knowledge **fail the whole run**.
- Each market event is bound one-to-one to exactly one SHA-256 matching vintage record. Revision `published_at` cannot exceed market event `available_at`; revision `received_at` cannot exceed market event `received_at`. Backfilled corrections cannot masquerade as original bars. The revision label is declarative, not a provider endorsement.
- Each instrument's entire event window must fall in one known action-catalog coverage declaration. Missing or late declarations fail; overlapping coverage and overlapping membership windows are rejected rather than guessed.
- **Any corporate action effective inside the test window causes the entire run to fail**, regardless of whether it was known at the time. This is a *model capability check*, not a prediction or a stock-selection filter. We do **not** drop affected symbols (which would introduce survivorship bias), silently adjust prices, invent dividends, or assume a delisted position disappears.
- The complete evidence input file is SHA-pinned and has strict, tagged JSONL parsing. Output `pit_gate.json` is SHA-pinned in `manifest.json` and verified by the existing artifact checker.
- No evidence: legacy synthetic test remains runnable, but the manifest records `PIT_EVIDENCE_NOT_SUPPLIED`. All releases stay `pit_data_release_verified=false` even after a synthetically successful gate.

## Output and threat model

`pit_gate.json` contains `event_count`, `instrument_count`, `evidence_sha256`, `reason_codes`, `data_release_verified=false`. The `manifest.json` retains `pit_dataset_file_sha256`, `pit_evidence_sha256`, `pit_gate_checked_events`, source/license declarations and unverified flags.

The gate checks *internal causal consistency* only. Data providers may omit corporate actions, declare false no-action coverage, backdate publication times, or supply survivor-only universes. A historical catalog created after the fact cannot prove that all its data existed at a past timestamp. **Independent provider license, issuer-record completeness, raw/adjusted price policy, actual listing/delisting history and correction feed must be verified separately.** It is not valid to call this 'real-market verified' without that evidence.

## Still required before E5 research acceptance

1. Authenticated historical provider vintage/coverage, delisted-symbol inclusion and market-specific listings. Build an ingest adapter from actual license-permitted sources.
2. Deterministic split/corporate-action-adjusted inventory, cash dividends and broker/tax treatment including price basis versions **or** explicitly limit a study to a predeclared, justified no-action interval and report restrictions.
3. Exchange- and broker-specific fee/tax and PIT FX source validation; Tick/Quote assisted execution model and intrabar ambiguity policy.
4. Full run reproducibility with data license records, universe definitions, held-out periods and robust research diagnostics before any E6 candidate promotion.

No live brokerage or operational credentials are introduced.

## E5.7 후속 메모 (2026-11-17)

[E5_CORPORATE_ACTIONS.md](E5_CORPORATE_ACTIONS.md)의 E3 장부는 합성적인 split, dividend entitlement/payment, delisting 이벤트를 독립 처리할 수 있다. **이 문서의 E5.6 PIT 전수 게이트는 기업행동이 있는 실데이터 백테스트를 계속 중단한다.** 발행사 확인 기업행동 조건, 가격/거래량 보정, 가상 전략별 잔고 귀속, vintage/지급·정산 일정을 결합한 통합 테스트 전에는 우회하지 않는다. PR #29.
