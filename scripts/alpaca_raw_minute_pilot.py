"""Fixed raw SIP minute pilot: 2022 Oct/Nov, six prespecified US equities.

No raw artifacts or order access; conservative provider corporate-action
screen, strict warmup/evaluation grid, matched E5 fee-aware arms.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal as D
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from e513_market_study import MINUTE, TARGET, run, save
from prepare_market_panel import digest, normalize, request
from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.evaluation import EvaluationWindow, validate_window
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.strategies.orb import ORBLongStrategy, ORBParameters

SYMBOLS = ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOG")
MONTHS = (10, 11)
COSTS = ("base", "stress")
RULES = {"orb-default": (15, "1.5"), "orb-patient": (30, "1.5"),
         "orb-volume": (15, "2")}
SOURCE = "Alpaca SIP raw 2022 retrospective minute pilot"
UTC = ZoneInfo("UTC")


def actions(symbol, first, last, headers):
    # Provider filters on processing dates rather than effective dates.
    # Include a 45-day buffer either side; reject any returned action
    # conservatively, even if it may be irrelevant. No PIT certificate.
    params = {"symbols": symbol, "start": str(first-timedelta(days=45)),
              "end": str(last+timedelta(days=45)), "limit": 1000,
              "data_quality": "all"}
    raw = request("https://data.alpaca.markets/v1/corporate-actions?"+urlencode(params), headers)
    data = json.loads(raw)
    grouped = data["corporate_actions"]
    if (not isinstance(grouped, dict) or any(not isinstance(v, list) for v in grouped.values())
            or data.get("next_page_token")):
        raise ValueError("UNVERIFIABLE_ACTION_RESPONSE")
    return {k: len(v) for k, v in grouped.items() if v}, digest(raw)


def build_grid(symbol, month):
    exchange = xcals.get_calendar("XNYS", start="2022-07-01", end="2022-11-30")
    labels = [x for x in exchange.sessions if x.month < month][-20:]
    start = len(labels)
    labels.extend(x for x in exchange.sessions if x.month == month)
    if start != 20 or len(labels) == 20:
        raise ValueError("CALENDAR_INCOMPLETE")
    inst = InstrumentId(Market.US, "US-SIP", symbol, symbol, "USD")
    sessions = tuple(TradingSession(inst.market, inst.venue,
        exchange.session_open(x).to_pydatetime().astimezone(UTC),
        exchange.session_close(x).to_pydatetime().astimezone(UTC)) for x in labels)
    return inst, sessions, labels[0].date(), labels[-1].date()


def fetch_tape(inst, sessions, headers):
    expected = set()
    for sess in sessions:
        at = sess.start
        while at < sess.end:
            expected.add(at)
            at += MINUTE
    params = {"symbols": inst.symbol, "timeframe": "1Min",
              "start": sessions[0].start.isoformat(), "end": sessions[-1].end.isoformat(),
              "adjustment": "raw", "feed": "sip", "asof": "-", "limit": 10000, "sort": "asc"}
    bars, hashes, tokens = {}, [], set()
    invalid = duplicate = extended = 0
    while True:
        raw = request("https://data.alpaca.markets/v2/stocks/bars?"+urlencode(params), headers)
        hashes.append(digest(raw))
        data = json.loads(raw, parse_float=D)
        result = data["bars"]
        if not isinstance(result, dict) or set(result)-{inst.symbol}:
            raise ValueError("UNEXPECTED_BAR_SCHEMA")
        for bar in result.get(inst.symbol, []):
            try:
                at = datetime.fromisoformat(bar["t"])
                if at.tzinfo is None or at.second or at.microsecond:
                    raise ValueError("INVALID_MINUTE")
                at = at.astimezone(UTC)
                if at not in expected:
                    extended += 1
                    continue
                if at in bars:
                    duplicate += 1
                    continue
                row = normalize(at.date().isoformat(), *(bar[k] for k in ("o","h","l","c","v")))
                if D(row[-1]) == 0:
                    raise ValueError("ZERO_VOLUME")
                bars[at] = tuple(D(x) for x in row[1:])
            except (ValueError, TypeError, KeyError, ArithmeticError):
                invalid += 1
        token = data.get("next_page_token")
        if not token:
            break
        if token in tokens or len(tokens) == 100:
            raise ValueError("PAGINATION_LOOP")
        tokens.add(token)
        params["page_token"] = token
    audit = {"expected_minutes": len(expected), "observed_minutes": len(bars),
             "missing_minutes": len(expected-bars.keys()), "duplicate_minutes": duplicate,
             "invalid_minutes": invalid, "excluded_off_grid": extended, "source_sha256": hashes}
    if audit["missing_minutes"] or duplicate or invalid:
        return (), audit
    events = tuple(EventEnvelope(f"{inst.symbol}:{at.isoformat()}", "market.bar", SOURCE,
                    inst, at+MINUTE, at+MINUTE, at+MINUTE, idx,
                    Bar(at, at+MINUTE, *bars[at], interval=MINUTE))
                   for idx, at in enumerate(sorted(bars)))
    return events, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", choices=SYMBOLS)
    parser.add_argument("month", type=int, choices=MONTHS)
    args = parser.parse_args()
    symbol, month = args.symbol, args.month
    key, secret = os.environ.get("ALPACA_DATA_KEY"), os.environ.get("ALPACA_DATA_SECRET")
    if not key or not secret:
        raise SystemExit("MISSING_DATA_CREDENTIALS")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    report = {"symbol": symbol, "month": month, "year": 2022, "planned_arms": 10,
              "study_schema": "alpaca-sip-raw-pilot-v1", "status": "SOURCE_ERROR",
              "holdout_accessed": False, "execution_certified": False}
    rows, errors = [], []
    try:
        inst, sessions, first, last = build_grid(symbol, month)
        ca, ca_hash = actions(symbol, first, last, headers)
        report.update({"first_session": str(first), "last_session": str(last),
                       "action_counts": ca, "action_sha256": ca_hash})
        events, coverage = fetch_tape(inst, sessions, headers)
        report.update(coverage)
        blockers = []
        if ca:
            blockers.append("PROVIDER_CORPORATE_ACTION_IN_BUFFER")
        if not events:
            blockers.append("INCOMPLETE_MINUTE_TAPE")
        report["blockers"] = blockers
        if blockers:
            report["status"] = "BLOCKED"
        else:
            calendar = StaticSessionCalendar(sessions)
            window = EvaluationWindow(sessions[20].start, sessions[-1].end)
            validate_window(events, calendar, window)
            for kind in ("no-trade", "hold-retry", *RULES):
                for cost in COSTS:
                    try:
                        strat = (NoTradeStrategy(DataRequirement("market.bar", MINUTE))
                            if kind == "no-trade" else
                            BuyHoldBaseline(MINUTE, TARGET, D("0.015"), retry_each_session=True)
                            if kind == "hold-retry" else ORBLongStrategy(ORBParameters(
                                opening_us=timedelta(minutes=RULES[kind][0]),
                                volume_multiplier=D(RULES[kind][1]))))
                        result = run(inst, events, calendar, strat, cost, SOURCE, window,
                                     first_entry_only=kind == "hold-retry",
                                     session_flat=kind in RULES, e514=True, fee_replay=True)
                        row = {"symbol": symbol, "month": month, "year": 2022,
                               "strategy": kind, "cost": cost, **result}
                        rows.append(row)
                        print("RAW_MINUTE_RUN "+json.dumps(row), flush=True)
                    except Exception as exc:
                        errors.append({"strategy": kind, "cost": cost, "error_type": type(exc).__name__})
            report["status"] = "PROVISIONAL_COMPLETE" if len(rows) == 10 else "PARTIAL"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        if str(exc) in {"HTTP_400", "HTTP_401", "HTTP_403", "HTTP_429"}:
            report["error_code"] = str(exc)
    report["errors"] = errors
    save(f"alpaca-raw-minute-{symbol}-{month}", rows, report)
    if report["status"] in ("SOURCE_ERROR", "PARTIAL"):
        raise SystemExit("RAW_MINUTE_STUDY_INCOMPLETE")


if __name__ == "__main__":
    main()
