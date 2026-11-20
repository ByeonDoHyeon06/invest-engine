# E6.7a / E7 — Continuous event ingress and session contract

Status: user-approved design direction, 2026-11-20. Not executable SDK or approved live/paper deployment. Tracks #59; existing [SDK examples](E6_7_SDK_EXAMPLES.md) 15–16 remain compatible and 19–23 extend the design. Existing #62 historical run retains its frozen research gate. No implementation prerequisite waived.

## 1. Architecture and scope

HistoricalBacktest.run currently iterates a finite canonical tape, calls EventRuntime.accept and StrategyRunner.accept, and owns simulated execution orchestration. EventRuntime is an observation reducer with durable journal support; it is not itself the full trading engine. StrategyRunner consumes visible observations, builds read-only context and emits signals. EventEnvelope supports typed TradeTick, QuoteTick, Bar, OrderBookSnapshot and MarketStatus with event_time, available_at, received_at, source_sequence and identity. HistoricalDataProvider currently supplies finite records. No production streaming provider/session, live order adapter or streaming finalizer is implemented merely by these contracts. Explicit event/time/timer capabilities must be inventoried, including unsupported event types. Current E5 has specific bar-oriented simulation restrictions; do not claim all tick/quote execution combinations are implemented.

Target: input transport → bounded ingestion/normalization → canonical ordered event → shared observation/features/strategy → sizing/risk → proposal or explicit simulation/execution adapter. Backtest uses a historical tape and virtual clock; caller-fed evaluation uses real observations and externally authoritative account snapshots; managed Paper uses explicit data I/O and isolated simulation; Live E8 separate. No duplicate core implementation or hidden mode. Extract per-event orchestration only where proven necessary; preserve old import paths, economic outputs and deterministic evidence.

## 2. Public surface and lifecycle

| Operation | State & authority | Phase |
|---|---|---|
| Engine() | Inert; no credentials, I/O, tasks or account | E6.7b |
| engine.evaluate(market_data=..., portfolio=..., strategy=...) | Existing planned one-shot proposal; fresh valid context or explicit blocker | E6.7a signature, future implementation |
| engine.evaluate.session(...) | Callable evaluation service with synchronous factory returning async context-manageable decision-only session; no implicit network | E6.7a design / E7 implementation |
| session.warmup(history) | Causal history validation, observation only; explicit no-trade warmup | E7 |
| session.ingest(event, *, portfolio=None) | Await serialized acceptance; typed outcome, optional snapshot binding; no real submit | E7 |
| session.update_portfolio(snapshot) | Await serialized snapshot refresh; never mutate original account | E7 |
| engine.paper.start(...) | Explicit async managed provider lifecycle, local simulated cash | E7 |
| session.events() | Async iterator of typed outcome/status events; bounded, cancellation-aware | E7 |
| session.status / context exit | Inspect state; close/join tasks, preserve stop reason and audit | E7 |
| engine.live | No callable order route until separately authorized | E8 |

Single-call evaluate remains callable (service __call__ or equivalent typed interface) with the prior names and semantics, not an incompatible namespace replacement. Existing user-approved Engine() and examples unchanged. Factory config is validated and inert; no background task starts on import. Injected caller owns transport unless explicitly transferred. Managed Paper start connects only after data rights, scope, account simulation, policy validation and warmup resolution. If a source cannot supply required evidence, block rather than auto-fallback. Session states: created → warming → ready → paused/halted → explicitly reviewed resume or closed. No implicit resume after a fault; close is idempotent; pending work is either durably settled or explicitly cancelled. Exact typed signature/defaults, exceptions/outcome schema and lifecycle ownership finalized at E6.7a, before code and contract freeze tests.

## 3. Event and time contract

Accept existing EventEnvelope at the advanced boundary. Convenience market.Trade and future quote/bar helpers map losslessly into known instruments and canonical types; use Decimal or decimal string amounts, aware UTC timestamps and explicit source identity. Symbol aliases only resolve in a declared unambiguous universe (market, venue, security identifier, currency). Do not fabricate source sequence, event ID, publication time, trade quantity or market venue. If availability is not independently known, label the evidence limitation, use only justified conservative visibility and never claim verified PIT. Engine clock injected; decision visibility is max(available_at, received_at) under existing core semantics, never future observations. Capture original source timestamp and actual receipt; ingest time, processing latency and clock skew diagnostics remain separate. Replaying captured stream uses the same known availability/receipt ordering, not hindsight exchange-time resorting.

Single writer per session; portfolio refresh, timers and data events also serialize. Multiple producers enqueue to bounded ingress; stable source cursor/ordinal resolves ordering within supported stream; no unknowable cross-source total ordering claim. Exact duplicate retransmissions may be deduplicated at validated ingress only when canonical identity/content agree; current reducer rejects duplicate IDs, so do not relax it. Conflicting duplicate, unresolvable gap, late/corrected observation or sequence regression is a typed blocker/halt per documented provider policy; never patch prior decisions silently. Checkpoint + cursor + journal commit ordering must prevent replay of already-consumed proposals; no claim of cross-process exactly-once brokerage execution. Backpressure pauses safe sources; non-pausable overflow triggers explicit gap/HALT, not drop or compress ticks invisibly.

## 4. State, warmup and subscriptions

Retain bounded history/feature state, strategy snapshots, source cursors, last eligible mark and event decisions. No full historical re-run per tick; incremental calculation only if numerically equivalent to supported existing indicators, otherwise bounded deterministic recompute. Explicit warmup length, interval, calendar and source basis; buffered live events during backfill must bridge with identity/order/coverage checks; no lookahead, no warmup trading. If requirements unmet, outcome is WARMING/BLOCKED not a false NO_TRADE. Validate complete calendar and gaps as required by each strategy. Real-time finalized bars: native final bars or policy-versioned trade aggregation anchored to exchange session, with completeness, boundary, allowed lateness and watermark/finalization evidence; no synthetic bars/volume or tick reconstruction. Late correction does not retroactively place orders. Distinguish incomplete provisional bars from finalized bars; finalized-bar strategy must run only on eligible finalization. Timers are explicit causal events with injected clock; no wall-clock calls from deterministic strategy.

Use existing Strategy.on_event protocol and DataRequirement. High-level on_bar/on_tick/on_quote/on_order_book/on_timer adapt to declared event subscriptions and required inputs; only supported callbacks published, no unconditional callback on every tick. Read-only causal context, no provider/network/order calls from strategy contract; plugins are trusted Python code, not a security sandbox. Strategy state isolated by session/run, fixed version/config and deterministic restore. Multi-instrument/shared allocation only supported combinations; no implicit capital duplication.

## 5. Account and execution boundaries

Caller supplies broker-authoritative account snapshot, not opening fictitious cash. Snapshot must bind broker/account identity, currency, available cash/buying power, positions, open/pending orders and relevant account state version/as-of/receipt times, trusted source and reconciliation evidence. Validate freshness against decision time, monotonicity, coverage, outstanding orders, unresolved submissions and causal availability. Snapshot is immutable observation (may cache a short-lived version for decision use); broker remains source of truth. No asset database duplication, no generated balance for real holdings. Missing, stale, conflicting or unknown account state blocks new exposure; continue observation safely where permitted. Never silently treat zero or old snapshot as trustworthy.

Decision session returns proposal + reason codes + input/snapshot identity + expiry/validity and submitted=false, not a fill or actual order. Application must reconcile/revalidate any proposed action against current broker/account conditions; actual execution requires approved adapter and separate authority, not a bool flag. Repeated proposals have stable identities and are invalidated by relevant state changes; no auto-submission path in E7. Paper uses separate internally simulated ledger and same mandatory risk logic with modeled fee/fill/liquidity gates; never present simulated assets as real. Protective actions under stale conditions require separately specified policy, not risky implicit market orders. Live broker reconciliation/kill switch/idempotency/authorization E8.

## 6. Recovery and operational safety

Heartbeats, data staleness and transport health per source, bounded queues and observable metrics. Reconnect is not proof of completeness. Validate gap-free resume cursor or explicit backfill, checkpoint config/state hash, broker snapshot and order reconciliation; if source has no sufficient proof, explicit pause/halt and operator-reviewed recovery. Distinguish provider failure, stale quote, invalid data, blocked context and valid no-signal. Journal safe canonical evidence (source rights respected; secrets excluded); retain only allowed raw data and avoid sensitive snapshot export. Session close cancels/joins managed tasks and preserves audit; external transport ownership stays with caller. Monitor latency distribution, queue depth, stale age, missed/duplicate counts, time skew, decision latency, actual memory and CPU; choose SLO from measurements, not invented rates. Do not promise HFT/latency or real execution support.

## 7. E6.7a design and E7 acceptance mapping

| Fixture | Required evidence |
|---|---|
| API signatures and import | old evaluate call still callable; 19–23 typed future design; zero import/factory I/O, no live route |
| Canonical event tape parity | exact same ordered available/received input, state, deterministic strategy/sizing/risk policies and identical simulated execution policy → equivalent decisions, fills, ledger and PnL where supported; explain version hashes |
| Chunking / external input | different transport batch boundaries, same canonical events = same decisions; no full history access or future leakage |
| Warmup + stream handoff | missing history blocks; valid gap-free handoff; cross-session, DST, early close, finalized bars, late arrivals |
| Snapshot lifecycle | stale, wrong account, missing buying power, open orders, out-of-order snapshots → no new exposure; valid refresh; no local authoritative assets |
| Duplicate/conflict/gap/pressure | equal retry accepted at ingress without second application; conflict/overflow/gap explicit typed halt; no silent data loss |
| Disconnect/restart/shutdown | cursor/ledger/strategy reconciliation, idempotent close, no unjoined owned tasks, no duplicated proposal; no real orders |
| Strategy subscriptions | same strategy across replay and streamed normalized observations, callbacks only for declared supported data; state isolation |
| Simulated stream | Paper fill/fee policy parity on matched simulated tape; real observations do not certify real fills; zero broker trade calls |
| Performance & evidence | bounded memory/queue, measured p50/p95/p99 event processing/decision latency, explicit data rights and source provenance; no arbitrary target |

E6.7a inventories all current runtime, journal, provider, strategy and backtest signatures and maps exact fixtures/types/unsupported paths. E6.7b–e preserve offline functionality and parity; no streaming implementation required or authorized by this document. E7 requires separately approved scope and tests, fault injection, recorded-stream parity and forward real-time observation under existing roadmap: each market >=20 trading days and adequate trades/regimes, not merely elapsed time. E8 separate. Current research losses, unresolved external evidence and actual fee/provider certification remain independent blockers.

## 8. Non-goals

No new strategy tuning, #62 gate modification, provider credential access, live adapter, production execution, implicit capital, universal exchange feed or promise of performance. The synchronous offline SDK remains supported, with async lifecycle at explicit I/O/continuous boundaries.
