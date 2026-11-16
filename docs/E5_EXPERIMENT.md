# E5.2 — Repeatable historical RunRequest and offline CLI

**Status:** offline-only research adapter. This is not an order-execution service and never requests broker/API credentials.

## Usage

    invest-engine backtest --config ./research/run.json

The config is a strict `e5-research-v1` JSON object with exact top-level fields:

- `schema_version`: `e5-research-v1` only.
- `run_id`: nonempty experiment identifier.
- `mode`: **BACKTEST only**. `PAPER`, `LIVE`, credentials and unknown fields rejected.
- `code_sha`: pinned source version **provided by experiment author** (the CLI does not independently verify the local git commit).
- `dataset`: `events_jsonl` (path relative to config directory), `source`, `license`, `sha256` of exact file bytes. History must use **canonical E0/E2 market event JSON**, one per line, and contain valid consecutive ingestion ordinals. The CLI verifies the file hash before reading events.
- `sessions`: authoritative list `{market,venue,start,end}` in UTC. No inferred holidays/DST/session closures; provenance must be checked by experiment author.
- `strategy`: `id`, `version`, `parameters` (allowed: `no-trade@1.0.0` with `interval: PT1M` or other whole-minute interval, and `orb-long@1.0.0` with explicit interval, opening_kr/us, prior_sessions, volume_multiplier, target_fraction, atr_period). No arbitrary import/LLM strategies.
- `account`: account ID (synthetic), explicit `cash`, currency `cash_rules`, `instruments` tick/lot, synthetic `fee_rate` and `sell_tax_rate` Decimal strings.
- `risk`: explicit per-trade, per-symbol, account exposure fractions and max positions. E3's hard risk gate remains mandatory.
- `fill_model`: exact model version, participation and spread/impact bps Decimal strings.
- `output_dir`: caller-controlled output destination relative to config directory.

Outputs:
- `report.json`: immutable backtest report; trade counts in report are **fill counts**, not number of round-trip trades.
- `decisions.jsonl`: event ID → strategy signal → intent → risk rejection/approval → fill IDs.
- `equity.jsonl`: point-in-time per-currency marked equity; incomplete marks are not invented.
- `fills.jsonl`: execution details and synthetic fee/tax/realized exit P&L.
- `manifest.json`: data file and event hashes, pinned code string, strategy/fill versions, cost assumption identifiers, run hash and safety limitations.

The CLI prints the run ID, run hash, manifest hash, and local artifact directory. Two runs with identical code/inputs/config produce identical run artifacts; updating a data file invalidates the pinned SHA256.

**Provenance caveat:** the supplied `code_sha` is a user assertion, not cross-checked with Git; source/feed rights, corporate actions and historical exchange/calendar details are not automatically verified. Historical bars cannot reconstruct original spread/queue. Output is **research only**.

## Testing

- Canonical JSONL E0 decoder → E2 observation → E4 NoTrade/ORB → E3 simulation → report/manifest/CLI.
- Negative: LIVE mode, unapproved strategy, float prices/cash, unknown fields, incorrect file hash, noncanonical data, invalid session.
- Deterministic multiple-run comparison with unchanged inputs.

## Outstanding E5 closure gate

Stop/target collision and gap-through-stop execution are **not modeled**. Complex partial-fill queue/slippage and FX conversion remain unverified. They must be validated and documented in a future PR before claiming E5 complete; do not substitute the limit-fill crossing model for a guaranteed stop-order execution.
