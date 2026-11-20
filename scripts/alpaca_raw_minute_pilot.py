"""Fixed raw SIP minute pilot: 2022 Oct/Nov, six prespecified US equities.

No raw artifacts or order access; conservative provider corporate-action
screen, strict warmup/evaluation grid, matched E5 fee-aware arms.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

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
SOURCE = "Alpaca SIP raw 2022 retrospective minute pilot v4"
UTC = ZoneInfo("UTC")


# These three ordinary events have documented ex/record/payment dates.
# Every other action type remains fail-closed, including symbol changes.
DATE_KINDS = frozenset(("cash_dividends", "forward_splits", "reverse_splits"))
DATE_FIELDS = ("ex_date", "record_date", "payable_date")


def classify_actions(grouped, symbol, first, last):
    """Conservative classification of provider-returned actions only.

    No declaration of complete PIT coverage. For supported events, allow
    exclusion only if the *entire* entitlement/effective/payment interval
    lies outside warmup plus evaluation. Unknown schema/identity blocks.
    """
    if not isinstance(grouped, dict) or first > last:
        raise ValueError("UNVERIFIABLE_ACTION_RESPONSE")
    results = []
    for kind, records in sorted(grouped.items()):
        if not isinstance(records, list):
            raise ValueError("UNVERIFIABLE_ACTION_RESPONSE")
        for record in records:
            detail = {"kind": kind, "classification": "UNRESOLVED", "dates": {},
                      "reason": "UNSUPPORTED_ACTION_TYPE"}
            if kind not in DATE_KINDS or not isinstance(record, dict):
                results.append(detail)
                continue
            detail["schema"] = {field: ("missing" if field not in record else
                "null" if record[field] is None else "empty" if record[field] == ""
                else type(record[field]).__name__) for field in (
                "symbol", "currency", "cusip", "foreign", "ex_date", "record_date",
                "payable_date", "effective_date", "due_bill_on_date", "due_bill_off_date")}
            detail["symbol_matches"] = record.get("symbol") == symbol
            detail["usd_explicit"] = record.get("currency") == "USD"
            detail["foreign_false"] = record.get("foreign") is False
            # Currency is optional in provider schema; this screen does not
            # credit cash or infer USD. Accept omission for date-only analysis
            # on a symbol-matched record, never for accounting.
            currency = record.get("currency")
            cusip = record.get("cusip")
            # Split records omit the dividend-specific foreign field. Absence
            # is not a domestic certification: only dates are screened, and
            # a stated foreign or malformed value still fails closed.
            split = kind in ("forward_splits", "reverse_splits")
            foreign_ok = record.get("foreign") is False or (split and "foreign" not in record)
            detail["foreign_basis"] = ("EXPLICIT_DOMESTIC" if record.get("foreign") is False
                                       else "UNSPECIFIED_SPLIT_DATE_ONLY")
            if (record.get("symbol") != symbol or not foreign_ok
                    or not isinstance(cusip, str) or not cusip.strip()
                    or currency not in (None, "", "USD")):
                detail["reason"] = "IDENTITY_OR_CURRENCY_UNVERIFIED"
                results.append(detail)
                continue
            detail["currency_basis"] = "EXPLICIT_USD" if currency == "USD" else "UNSPECIFIED_DATE_ONLY"
            try:
                dates = {field: date.fromisoformat(record[field]) for field in DATE_FIELDS}
                # A non-null optional effective date can only widen the bounds.
                for field in ("effective_date", "due_bill_on_date", "due_bill_off_date"):
                    if record.get(field) is not None:
                        dates[field] = date.fromisoformat(record[field])
                # An open due-bill interval is ambiguous and cannot be excluded.
                if ("due_bill_on_date" in dates) != ("due_bill_off_date" in dates):
                    raise ValueError("INCOMPLETE_DUE_BILL_INTERVAL")
                if ("due_bill_on_date" in dates
                        and dates["due_bill_on_date"] > dates["due_bill_off_date"]):
                    raise ValueError("INVALID_DUE_BILL_INTERVAL")
            except (KeyError, TypeError, ValueError):
                detail["reason"] = "REQUIRED_DATE_UNVERIFIED"
                results.append(detail)
                continue
            detail["dates"] = {k: v.isoformat() for k, v in dates.items()}
            # Do not assume the ex-date precedes payment: split conventions vary.
            if max(dates.values()) < first or min(dates.values()) > last:
                detail["classification"] = "OUTSIDE_WINDOW"
            else:
                detail["classification"] = "INTERSECTS_WINDOW"
            detail["reason"] = "ECONOMIC_DATE_INTERVAL_CLASSIFIED"
            results.append(detail)
    return results


def actions(symbol, first, last, headers):
    # Provider query bounds are processing dates, not economic event dates.
    # Use a wider 90-day search margin to detect delayed processing; this
    # remains bounded retrospective metadata rather than a PIT attestation.
    params = {"symbols": symbol, "start": str(first-timedelta(days=90)),
              "end": str(last+timedelta(days=90)), "limit": 1000,
              "data_quality": "all"}
    raw = request("https://data.alpaca.markets/v1/corporate-actions?"+urlencode(params), headers)
    data = json.loads(raw)
    if data.get("next_page_token"):
        raise ValueError("UNVERIFIABLE_ACTION_RESPONSE")
    details = classify_actions(data["corporate_actions"], symbol, first, last)
    return details, digest(raw)


def build_grid(symbol, month):
    import exchange_calendars as xcals

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
    parser.add_argument("--action-diagnostics-only", action="store_true")
    args = parser.parse_args()
    symbol, month = args.symbol, args.month
    key, secret = os.environ.get("ALPACA_DATA_KEY"), os.environ.get("ALPACA_DATA_SECRET")
    if not key or not secret:
        raise SystemExit("MISSING_DATA_CREDENTIALS")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    report = {"symbol": symbol, "month": month, "year": 2022, "planned_arms": 10,
              "study_schema": "alpaca-sip-raw-pilot-v4", "status": "SOURCE_ERROR",
              "holdout_accessed": False, "execution_certified": False}
    rows, errors = [], []
    try:
        inst, sessions, first, last = build_grid(symbol, month)
        ca, ca_hash = actions(symbol, first, last, headers)
        action_counts = {kind: sum(x["kind"] == kind for x in ca) for kind in sorted({x["kind"] for x in ca})}
        report.update({"first_session": str(first), "last_session": str(last),
                       "action_counts": action_counts, "action_classifications": ca,
                       "action_sha256": ca_hash, "action_search_margin_days": 90})
        if args.action_diagnostics_only:
            report["status"] = "ACTION_SCHEMA_DIAGNOSTIC"
            report["errors"] = []
            save(f"alpaca-action-schema-{symbol}-{month}", [], report)
            return
        events, coverage = fetch_tape(inst, sessions, headers)
        report.update(coverage)
        blockers = []
        if any(x["classification"] == "UNRESOLVED" for x in ca):
            blockers.append("UNRESOLVED_PROVIDER_CORPORATE_ACTION")
        if any(x["classification"] == "INTERSECTS_WINDOW" for x in ca):
            blockers.append("PROVIDER_CORPORATE_ACTION_INTERSECTS_WINDOW")
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
                        print("RAW_MINUTE_ARM_FAILED "+json.dumps(errors[-1]), flush=True)
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
