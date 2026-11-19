"""E5.13 preregistered provisional historical study. No raw data publication."""
from __future__ import annotations

import csv
from collections import Counter
import hashlib
import io
import json
import os
import sys
from time import perf_counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from zipfile import ZipFile

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market, Money
from invest_engine.research.backtest import BacktestSettings, HistoricalBacktest
from invest_engine.research.evaluation import EvaluationWindow, validate_window
from invest_engine.research.fills import BarFillPolicy
from invest_engine.research.protection import ProtectionPolicy
from invest_engine.research.us_fee_audit import FeeAssumption, audit_us_fixed_fills
from invest_engine.strategies.allocation import AllocationPolicy
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import (
    DataRequirement, SignalDirection, StrategyManifest, StrategySignal,
)
from invest_engine.strategies.orb import ORBLongStrategy
from invest_engine.trading.dated_fees import USDatedFeeConfig
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits

TZ = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
MINUTE = timedelta(minutes=1)
DAY = timedelta(minutes=390)
CAPITAL = D("100000")
TARGET = D("0.05")
SOURCE = "https://historicaldata.net/file/stocks_sample_2022H2.zip"
DAILY_REF = "e31dd3817bb2eccaa10d3b01c6f2efdbca5d3abf"
DAILY_SYMBOLS = ("AAPL", "MSFT", "NVDA", "TSLA", "GOOG", "META")
RULES = ("no-trade", "hold", "momentum2", "sma3_7", "breakout3", "meanrev5", "trend5")
COSTS = {"low": ("0.0005", "2", "3"), "base": ("0.001", "5", "5"),
         "stress": ("0.0025", "20", "20")}
HOLIDAYS_2022 = {date(2022, 7, 4), date(2022, 9, 5), date(2022, 11, 24),
                 date(2022, 12, 26)}
HALF_2022 = {date(2022, 11, 25)}
HALF_2025 = {date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24)}
OUT = Path("research-output")


def download(url, limit):
    req = Request(url, headers={"User-Agent": "invest-engine-research/1.0"})
    with urlopen(req, timeout=45) as response:
        data = response.read(limit+1)
    if len(data) > limit:
        raise ValueError("download exceeds cap")
    return data


def instrument(symbol):
    venue = "ARCX" if symbol == "SPY" else "XNAS" if symbol in DAILY_SYMBOLS else "XNYS"
    asset = AssetClass.ETF if symbol == "SPY" else AssetClass.EQUITY
    return InstrumentId(Market.US, venue, symbol, symbol, "USD", asset)


def stamp(day, hh, mm):
    return datetime.combine(day, time(hh, mm), TZ).astimezone(UTC)


def session(inst, day, half=False):
    return TradingSession(inst.market, inst.venue, stamp(day, 9, 30),
                          stamp(day, 13 if half else 16, 0))


def event(inst, row, start, end, index, span):
    values = tuple(D(row[k]) for k in ("open", "high", "low", "close", "volume"))
    bar = Bar(start, end, *values, interval=span)
    # Bar-end availability is explicitly an assumption, not historical PIT evidence.
    return EventEnvelope(f"{inst.symbol}:{start.isoformat()}", "market.bar",
                         "retrospective-public-sample", inst, end, end, end, index, bar)


@dataclass
class DailyRule:
    kind: str
    inst: InstrumentId

    @property
    def manifest(self):
        need = {"momentum2": 3, "sma3_7": 7, "breakout3": 4,
                "meanrev5": 5, "trend5": 5}.get(self.kind, 1)
        return StrategyManifest(self.kind, "study-v1", frozenset({Market.US}),
                                (DataRequirement("market.bar", DAY, warmup=need),))

    def snapshot(self):
        return self.kind.encode()

    def restore(self, data):
        if data != self.snapshot():
            raise ValueError("strategy snapshot mismatch")

    def on_event(self, ev, ctx):
        bars = [v.bar for v in ctx.bars_for(self.inst, DAY)]
        closes = [b.close for b in bars]
        n = len(bars)
        long = SignalDirection.LONG
        exit_ = SignalDirection.EXIT
        direction = None
        if self.kind == "hold":
            if n <= 3:
                direction = long
        elif self.kind == "momentum2":
            direction = long if closes[-1] > closes[-2] > closes[-3] else exit_
        elif self.kind == "sma3_7":
            direction = long if sum(closes[-3:])/3 > sum(closes[-7:])/7 else exit_
        elif self.kind == "breakout3":
            if closes[-1] > max(b.high for b in bars[-4:-1]):
                direction = long
            elif closes[-1] < min(b.low for b in bars[-4:-1]):
                direction = exit_
        elif self.kind == "meanrev5":
            direction = long if closes[-1] < sum(closes[-5:])/5*D("0.995") else exit_
        elif self.kind == "trend5":
            direction = long if (closes[-1] > sum(closes[-5:])/5
                and (bars[-1].high-bars[-1].low)/closes[-1] < D("0.02")) else exit_
        if direction is None:
            return ()
        return (StrategySignal(f"{self.kind}:{ev.event_id}", self.kind, "study-v1",
                self.inst, direction, TARGET if direction is long else D(0),
                ctx.as_of, ctx.as_of+timedelta(days=8), ev.event_id,
                stop_price=closes[-1]*D("0.985") if direction is long else None),)


def run(inst, events, calendar, strategy, cost, source, window=None, *,
        first_entry_only=False, session_flat=False, e514=False, fee_audit=False,
        fee_replay=False, independent_diagnostics=False):
    fee, spread, impact = COSTS[cost]
    config_cls = USDatedFeeConfig if fee_replay else TradingConfig
    config = config_cls("e514b-replay" if fee_replay else "e514-study" if e514 else "e513-study", (MonetaryRules("USD", D("0.01")),),
                 ((inst.key, InstrumentRules(D("0.01"), D(1))),),
                 fee_rate=D(fee), sell_tax_rate=D(0))
    risk = RiskLimits(per_trade_planned_loss=D("0.005"), max_symbol_cost_fraction=D("0.12"),
                      max_total_cost_fraction=D("0.20"), max_open_positions=1)
    settings = BacktestSettings(code_sha=os.environ.get("GITHUB_SHA", "local"),
                run_version=("e514b-fee-aware-v1" if fee_replay else
                             "e514-provisional-v1" if e514 else "e5-research-v1"),
                dataset_source=source, data_license="evaluation only; rights not independently certified",
                max_mark_age=timedelta(days=7) if window is None else timedelta(minutes=5))
    started = perf_counter()
    report = HistoricalBacktest(calendar=calendar, strategies=(strategy,), config=config,
        opening_cash=(Money(CAPITAL, "USD"),), risk=risk,
        fill_policy=BarFillPolicy(D("0.05"), D(spread), D(impact)),
        allocation_policy=AllocationPolicy(TARGET, TARGET),
        protection_policy=ProtectionPolicy(enabled=True, adverse_bps=D(spread)+D(impact))
            if session_flat else None,
        settings=settings, evaluation_window=window, first_entry_only=first_entry_only,
        session_flat=session_flat).run(events)
    by_id = {i: d.event_id for d in report.decisions for i in d.intent_ids}
    assert all(by_id.get(f.intent_id) != f.market_event_id for f in report.fills
               if f.reason_code == "LIMIT_FILLED")
    eq = dict(report.by_currency_end)["USD"]
    pnl = eq-CAPITAL
    real = dict(report.realized_exit_pnl).get("USD", D(0))
    result = {"elapsed_seconds": round(perf_counter()-started, 3),
            "return_pct": float(pnl/CAPITAL*100), "pnl": str(pnl),
            "mdd_pct": float(dict(report.max_drawdown)["USD"]*100),
            "fills": len(report.fills), "buys": sum(f.side == "BUY" for f in report.fills),
            "sells": sum(f.side == "SELL" for f in report.fills),
            "fees": str(dict(report.total_fees).get("USD", D(0))),
            "realized_exit_pnl": str(real), "residual_pnl": str(pnl-real),
            "signals": sum(bool(d.signal_ids) for d in report.decisions),
            "equity_points": len(report.equity), "events": report.event_count,
            "sha256": report.run_sha256}
    if e514:
        buys = [f for f in report.fills if f.side == "BUY"]
        sells = [f for f in report.fills if f.side == "SELL"]
        held = sum((f.quantity for f in buys), D(0)) - sum((f.quantity for f in sells), D(0))
        if session_flat and held != 0:
            raise RuntimeError("session-flat report has residual inventory")
        # Account cash performance can be zero without entry. The comparable
        # buy-and-hold return is undefined in that case, not an outperformable zero.
        status = ("NO_ENTRY_FILL" if not buys else "ENTRY_FILLED") if first_entry_only else "NOT_HOLD"
        result.update({
            "entry_coverage": status,
            "comparison_return_pct": None if status == "NO_ENTRY_FILL" else result["return_pct"],
            "filled_buy_orders": len({f.intent_id for f in buys}),
            "entry_intents": sum(len(d.intent_ids) for d in report.decisions)
                if first_entry_only else None,
            "buy_quantity": str(sum((f.quantity for f in buys), D(0))),
            "sell_quantity": str(sum((f.quantity for f in sells), D(0))),
            "held_quantity_end": str(held),
            "stop_exits": sum(f.reason_code in ("STOP_TRIGGERED", "GAP_BELOW_STOP",
                                              "STOP_FIRST_COLLISION") for f in sells),
            "session_close_exits": sum(f.reason_code == "SESSION_CLOSE_LIQUIDATION" for f in sells),
            "config_sha256": report.config_sha256,
        })
    if independent_diagnostics:
        result.update({
            "signal_records": len([d for d in report.decisions if d.signal_ids]),
            "intent_count": sum(len(d.intent_ids) for d in report.decisions),
            "signal_records_without_intent": sum(bool(d.signal_ids) and not d.intent_ids
                                                 for d in report.decisions),
            "decision_reasons": dict(sorted(Counter(
                reason for d in report.decisions for reason in d.reason_codes).items())),
            "subcent_close_observations": sum(
                isinstance(e.payload, Bar) and e.payload.close % D("0.01") != 0
                for e in events),
        })
    if fee_replay:
        audit = audit_us_fixed_fills(report, events, FeeAssumption(D(fee)))
        if audit.original_total != audit.repriced_total or audit.fixed_fill_net_pnl != pnl:
            raise RuntimeError("fee-aware replay does not reconcile to cumulative charge audit")
        result.update({
            "fee_replay_model": config.fee_policy_version,
            "regulatory_sec_usd": str(sum((o.sec_fee for o in audit.orders), D(0))),
            "regulatory_taf_usd": str(sum((o.taf for o in audit.orders), D(0))),
            "total_cost_usd": str(audit.original_total),
            "fee_audit_sha256": audit.audit_sha256,
            "fee_broker_verified": False,
            "fee_charge_date_verified": False,
            "fee_replayed_with_cost_policy": True,
        })
    elif fee_audit:
        audit = audit_us_fixed_fills(report, events, FeeAssumption(D(fee)))
        result.update({
            "fixed_fill_original_cost_usd": str(audit.original_total),
            "fixed_fill_repriced_cost_usd": str(audit.repriced_total),
            "fixed_fill_commission_usd": str(sum((o.commission for o in audit.orders), D(0))),
            "fixed_fill_sec_usd": str(sum((o.sec_fee for o in audit.orders), D(0))),
            "fixed_fill_taf_usd": str(sum((o.taf for o in audit.orders), D(0))),
            "fixed_fill_net_pnl_usd": str(audit.fixed_fill_net_pnl),
            "fixed_fill_return_pct": float(audit.fixed_fill_net_pnl/CAPITAL*100),
            "fixed_fill_comparison_pct": None if result.get("entry_coverage") == "NO_ENTRY_FILL"
                                         else float(audit.fixed_fill_net_pnl/CAPITAL*100),
            "fee_policy_sha256": audit.policy_sha256,
            "fee_audit_sha256": audit.audit_sha256,
            "fee_broker_verified": audit.broker_verified,
            "fee_charge_date_verified": audit.charge_date_verified,
            "fee_replayed_with_cost_policy": audit.replayed_with_cost_policy,
        })
    return result


def summarize(rows):
    result = {}
    for cost in COSTS:
        for kind in sorted({r["strategy"] for r in rows}):
            group = [r for r in rows if r["cost"] == cost and r["strategy"] == kind]
            if not group:
                continue
            vals = [r.get("comparison_return_pct", r["return_pct"]) for r in group]
            vals = [v for v in vals if v is not None]
            if not vals:
                result[f"{cost}:{kind}"] = {"n": len(group), "comparable_n": 0,
                                             "mean_pct": None, "reason": "NO_ENTRY_FILL"}
                continue
            result[f"{cost}:{kind}"] = {"n": len(group), "mean_pct": round(sum(vals)/len(vals), 6),
              "median_pct": round(median(vals), 6), "positive": sum(v > 0 for v in vals),
              "negative": sum(v < 0 for v in vals), "zero": sum(v == 0 for v in vals),
              "worst_pct": round(min(vals), 6), "best_pct": round(max(vals), 6),
              "max_mdd_pct": round(max(r["mdd_pct"] for r in group), 6),
              "fills": sum(r["fills"] for r in group),
              "fees_usd": str(sum(D(r["fees"]) for r in group))}
    return result


def save(name, rows, extra):
    OUT.mkdir(exist_ok=True)
    result = {"schema": extra.get("study_schema", "e5.13-provisional-study-v1"),
              "provider_verified": False,
              "point_in_time_verified": False, "execution_cost_verified": False,
              "source_data_redistributed": False, "capital_usd": str(CAPITAL),
              "target_fraction": str(TARGET), "rows": rows, "summary": summarize(rows), **extra}
    (OUT/f"{name}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("STUDY_RESULT " + json.dumps({"name": name, "n": len(rows), "summary": result["summary"],
                      **extra}, separators=(",", ":")), flush=True)
    if rows:
        with (OUT/f"{name}.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def daily():
    rows = []
    errors = []
    hashes = {}
    # All 12 calendar months of 2025 and all six named securities, independent cash reset.
    for symbol in DAILY_SYMBOLS:
        inst = instrument(symbol)
        url = f"https://raw.githubusercontent.com/Pubmarks/datasets/{DAILY_REF}/data/stocks/{symbol}/2025/ohlcv.csv"
        try:
            raw = download(url, 100000)
            hashes[symbol] = hashlib.sha256(raw).hexdigest()
            data = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
            if len(data) < 200:
                raise ValueError("daily data too short")
            assert len({r["date"] for r in data}) == len(data)
            for month in range(1, 13):
                selected = [r for r in data if date.fromisoformat(r["date"]).month == month]
                if len(selected) < 15:
                    raise ValueError("missing daily month")
                events = []
                sessions = []
                for r in selected:
                    day = date.fromisoformat(r["date"])
                    sess = session(inst, day, day in HALF_2025)
                    sessions.append(sess)
                    events.append(event(inst, r, sess.start, sess.end, len(events), DAY))
                cal = StaticSessionCalendar(tuple(sessions))
                # Half-day bars retain the daily strategy's nominal daily interval.
                for cost in COSTS:
                    for kind in RULES:
                        strat = (NoTradeStrategy(DataRequirement("market.bar", DAY))
                                 if kind == "no-trade" else DailyRule(kind, inst))
                        try:
                            res = run(inst, tuple(events), cal, strat, cost,
                                      "Pubmarks daily 2025 retrospective")
                            rows.append({"symbol": symbol, "month": month, "strategy": kind,
                                         "cost": cost, **res})
                        except Exception as exc:
                            errors.append({"symbol": symbol, "month": month, "strategy": kind,
                                           "cost": cost, "error": type(exc).__name__+":"+str(exc)[:160]})
            print("DAILY_SYMBOL_DONE", symbol, len(rows), len(errors), flush=True)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": type(exc).__name__+":"+str(exc)[:160]})
    save("daily", rows, {"source": "https://github.com/Pubmarks/datasets",
         "source_commit": DAILY_REF, "source_hashes": hashes, "errors": errors,
         "error_count": len(errors), "planned": 6*12*len(RULES)*len(COSTS),
         "limitations": "cold-start independent months; unverified adjustment basis, actions and vintage"})


def minute(symbol, month, *, e514=False, fee_audit=False, fee_replay=False):
    if (fee_audit or fee_replay) and not e514:
        raise ValueError("fee audit requires E5.14 experiment arms")
    inst = instrument(symbol)
    rows = []
    extra = {"symbol": symbol, "month": month, "source": "https://historicaldata.net/stocks.html",
             "status": "BLOCKED", "time_assumption": "bar-end receipt, no historical publication evidence"}
    if e514:
        extra["study_schema"] = ("e5.14b-fee-aware-replay-v1" if fee_replay else
                                 "e5.14b-fixed-fill-cost-v1" if fee_audit else
                                 "e5.14-provisional-study-v1")
        extra["planned_arms"] = 7
        extra["liquidation_assumption"] = "precommitted final-bar open, adverse price and minute volume cap"
    if fee_audit or fee_replay:
        extra["fee_scope"] = ("dated modeled fees change reservations and execution accounting; not broker-certified"
                              if fee_replay else "fixed fill repricing; not broker-certified or re-simulated")
        extra["panel"] = "extension" if month in (8, 12) else "matched-control"
    try:
        raw = download(SOURCE, 30_000_000)
        extra["archive_sha256"] = hashlib.sha256(raw).hexdigest()
        with ZipFile(io.BytesIO(raw)) as archive:
            candidates = []
            for item in archive.infolist():
                name = Path(item.filename).name
                if name.upper().startswith(symbol+"_") and name.lower().endswith(".csv"):
                    if item.file_size > 100_000_000:
                        raise ValueError("sample file exceeds cap")
                    content = archive.read(item)
                    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
                    if reader.fieldnames:
                        candidates.append((name, content, reader.fieldnames))
            m = next((v for v in candidates if "timestamp" in v[2] and "session" in v[2]), None)
            d = next((v for v in candidates if "date" in v[2] and "timestamp" not in v[2]), None)
            if m is None or d is None:
                raise ValueError("sample expected minute and daily files absent: "+str([v[0] for v in candidates]))
            extra["minute_sha256"] = hashlib.sha256(m[1]).hexdigest()
            extra["daily_sha256"] = hashlib.sha256(d[1]).hexdigest()
            daily_rows = list(csv.DictReader(io.StringIO(d[1].decode("utf-8-sig"))))
            all_days = []
            day = date(2022, 7, 1)
            until = date(2023, 1, 1) if month == 12 else date(2022, month+1, 1)
            while day < until:
                if day.weekday() < 5 and day not in HOLIDAYS_2022:
                    all_days.append(day)
                day += timedelta(days=1)
            before = [day for day in all_days if day.month < month][-20:]
            inside = [day for day in all_days if day.month == month]
            selected = set(before + inside)
            by_day = {date.fromisoformat(r["date"]): r for r in daily_rows}
            missing = sorted(selected-set(by_day))
            actions = sorted(str(day) for day in selected if day in by_day and
                      any(by_day[day].get(k, "").strip() not in ("", "0", "0.0", "0:0")
                          for k in ("dividend", "split")))
            extra.update({"warmup_sessions": len(before), "eval_sessions": len(inside),
                          "missing_daily_sessions": [str(day) for day in missing], "action_dates": actions})
            if len(before) != 20 or missing or actions:
                raise ValueError("predeclared window lacks complete action-free daily coverage")
            sessions = tuple(session(inst, day, day in HALF_2022) for day in before+inside)
            cal = StaticSessionCalendar(sessions)
            window = EvaluationWindow(sessions[20].start, sessions[-1].end)
            events = []
            for r in csv.DictReader(io.StringIO(m[1].decode("utf-8-sig"))):
                if r["session"] != "reg":
                    continue
                local = datetime.fromisoformat(r["timestamp"])
                if local.date() not in selected:
                    continue
                if local.tzinfo is not None:
                    raise ValueError("unexpected timestamp timezone")
                start = local.replace(tzinfo=TZ).astimezone(UTC)
                events.append(event(inst, r, start, start+MINUTE, len(events), MINUTE))
            extra["actual_bars"] = len(events)
            extra["expected_bars"] = sum((s.end-s.start)//MINUTE for s in sessions)
            try:
                coverage = validate_window(tuple(events), cal, window)
                extra["warmup_bars"] = coverage.warmup_bars
                extra["evaluation_bars"] = coverage.evaluation_bars
            except Exception as exc:
                raise ValueError("strict complete-minute preflight: "+str(exc)) from exc
            extra["status"] = "PREFLIGHT_PASS"
            print("MINUTE_PREFLIGHT "+json.dumps(extra), flush=True)
            arms = (("no-trade", "base"), ("hold-retry", "base"), ("hold-retry", "stress"),
                    ("orb-entry", "base"), ("orb-entry", "stress"),
                    ("orb-session-flat", "base"), ("orb-session-flat", "stress")) if e514 else (
                    ("no-trade", "base"), ("hold", "base"), ("orb", "base"), ("orb", "stress"))
            for kind, cost in arms:
                try:
                    strat = (NoTradeStrategy(DataRequirement("market.bar", MINUTE)) if kind == "no-trade"
                             else BuyHoldBaseline(MINUTE, TARGET, D("0.015"),
                                                  retry_each_session=kind == "hold-retry")
                             if kind in ("hold", "hold-retry") else ORBLongStrategy())
                    result = run(inst, tuple(events), cal, strat, cost,
                                 "HistoricalData.net free 2022H2 sample", window,
                                 first_entry_only=kind == "hold-retry",
                                 session_flat=kind == "orb-session-flat", e514=e514,
                                 fee_audit=fee_audit, fee_replay=fee_replay)
                    rows.append({"symbol": symbol, "month": month, "strategy": kind, "cost": cost, **result})
                    print("MINUTE_RUN "+json.dumps(rows[-1]), flush=True)
                except Exception as exc:
                    extra.setdefault("errors", []).append({"strategy": kind, "cost": cost,
                        "error": type(exc).__name__+":"+str(exc)[:160]})
            extra["status"] = "PROVISIONAL_COMPLETE" if len(rows) == len(arms) else "PARTIAL"
            if e514:
                extra["hold_entry_coverage"] = {row["cost"]: row["entry_coverage"]
                                                for row in rows if row["strategy"] == "hold-retry"}
                extra["comparator_complete"] = (
                    extra["hold_entry_coverage"] == {"base": "ENTRY_FILLED", "stress": "ENTRY_FILLED"})
    except Exception as exc:
        extra["error"] = type(exc).__name__+":"+str(exc)[:240]
    prefix = ("e514b-replay-minute" if fee_replay else "e514b-minute" if fee_audit
              else "e514-minute" if e514 else "minute")
    save(f"{prefix}-{symbol}-{month}", rows, extra)


if __name__ == "__main__":
    if sys.argv[1] == "daily":
        daily()
    else:
        mode = sys.argv[1]
        if mode not in ("minute", "minute-e514", "minute-e514b", "minute-fee-replay"):
            raise ValueError("unknown study mode")
        minute(sys.argv[2], int(sys.argv[3]), e514=mode != "minute",
               fee_audit=mode == "minute-e514b", fee_replay=mode == "minute-fee-replay")
