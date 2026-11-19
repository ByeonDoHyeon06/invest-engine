"""E5.13 preregistered provisional historical study. No raw data publication."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
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
from invest_engine.strategies.allocation import AllocationPolicy
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import (
    DataRequirement, SignalDirection, StrategyManifest, StrategySignal,
)
from invest_engine.strategies.orb import ORBLongStrategy
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
HOLIDAYS_2022 = {date(2022, 7, 4), date(2022, 9, 5), date(2022, 11, 24)}
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
    venue = "XNAS" if symbol in DAILY_SYMBOLS else "XNYS"
    asset = AssetClass.EQUITY
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


def run(inst, events, calendar, strategy, cost, source, window=None):
    fee, spread, impact = COSTS[cost]
    config = TradingConfig("e513-study", (MonetaryRules("USD", D("0.01")),),
                 ((inst.key, InstrumentRules(D("0.01"), D(1))),),
                 fee_rate=D(fee), sell_tax_rate=D(0))
    risk = RiskLimits(per_trade_planned_loss=D("0.005"), max_symbol_cost_fraction=D("0.12"),
                      max_total_cost_fraction=D("0.20"), max_open_positions=1)
    settings = BacktestSettings(code_sha=os.environ.get("GITHUB_SHA", "local"),
                dataset_source=source, data_license="evaluation only; rights not independently certified",
                max_mark_age=timedelta(days=7) if window is None else timedelta(minutes=5))
    report = HistoricalBacktest(calendar=calendar, strategies=(strategy,), config=config,
        opening_cash=(Money(CAPITAL, "USD"),), risk=risk,
        fill_policy=BarFillPolicy(D("0.05"), D(spread), D(impact)),
        allocation_policy=AllocationPolicy(TARGET, TARGET),
        settings=settings, evaluation_window=window).run(events)
    by_id = {i: d.event_id for d in report.decisions for i in d.intent_ids}
    assert all(by_id.get(f.intent_id) != f.market_event_id for f in report.fills)
    eq = dict(report.by_currency_end)["USD"]
    pnl = eq-CAPITAL
    real = dict(report.realized_exit_pnl).get("USD", D(0))
    return {"return_pct": float(pnl/CAPITAL*100), "pnl": str(pnl),
            "mdd_pct": float(dict(report.max_drawdown)["USD"]*100),
            "fills": len(report.fills), "buys": sum(f.side == "BUY" for f in report.fills),
            "sells": sum(f.side == "SELL" for f in report.fills),
            "fees": str(dict(report.total_fees).get("USD", D(0))),
            "realized_exit_pnl": str(real), "residual_pnl": str(pnl-real),
            "signals": sum(bool(d.signal_ids) for d in report.decisions),
            "equity_points": len(report.equity), "events": report.event_count,
            "sha256": report.run_sha256}


def summarize(rows):
    result = {}
    for cost in COSTS:
        for kind in sorted({r["strategy"] for r in rows}):
            group = [r for r in rows if r["cost"] == cost and r["strategy"] == kind]
            if not group:
                continue
            vals = [r["return_pct"] for r in group]
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
    result = {"schema": "e5.13-provisional-study-v1", "provider_verified": False,
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
         "source_commit": DAILY_REF, "source_hashes": hashes, "errors": errors[:50],
         "error_count": len(errors), "planned": 6*12*len(RULES)*len(COSTS),
         "limitations": "cold-start independent months; unverified adjustment basis, actions and vintage"})


def minute(symbol, month):
    inst = instrument(symbol)
    rows = []
    extra = {"symbol": symbol, "month": month, "source": "https://historicaldata.net/stocks.html",
             "status": "BLOCKED", "time_assumption": "bar-end receipt, no historical publication evidence"}
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
            until = date(2022, month+1, 1)
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
            for kind, cost in (("no-trade", "base"), ("hold", "base"), ("orb", "base"), ("orb", "stress")):
                try:
                    strat = (NoTradeStrategy(DataRequirement("market.bar", MINUTE)) if kind == "no-trade"
                             else BuyHoldBaseline(MINUTE, TARGET, D("0.015")) if kind == "hold"
                             else ORBLongStrategy())
                    result = run(inst, tuple(events), cal, strat, cost,
                                 "HistoricalData.net free 2022H2 sample", window)
                    rows.append({"symbol": symbol, "month": month, "strategy": kind, "cost": cost, **result})
                    print("MINUTE_RUN "+json.dumps(rows[-1]), flush=True)
                except Exception as exc:
                    extra.setdefault("errors", []).append({"strategy": kind, "cost": cost,
                        "error": type(exc).__name__+":"+str(exc)[:160]})
            extra["status"] = "PROVISIONAL_COMPLETE" if len(rows) == 4 else "PARTIAL"
    except Exception as exc:
        extra["error"] = type(exc).__name__+":"+str(exc)[:240]
    save(f"minute-{symbol}-{month}", rows, extra)


if __name__ == "__main__":
    if sys.argv[1] == "daily":
        daily()
    else:
        minute(sys.argv[2], int(sys.argv[3]))
