"""E5.15b preregistered independent-provider diagnostic; aggregates only.

No purchase, credential, raw storage or data redistribution. Rolling sample
bytes can change; pin the exact retrieved digest, never shift evaluation dates.
"""
from __future__ import annotations

import sys
import json
from datetime import date, timedelta

from e513_market_study import D, MINUTE, TARGET, download, run, save, session
from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.kibot_sample import inspect_kibot_unadjusted
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.strategies.orb import ORBLongStrategy

SAMPLES = {
    "IBM": ("https://api.kibot.com/?get=e4Vuqcxk", "XNYS", AssetClass.EQUITY),
    "OIH": ("https://api.kibot.com/?get=NaatWNJD", "ARCX", AssetClass.ETF),
}
# Both free sample instruments and both most recent completed calendar months
# as of 2026-11-19, selected before inspecting any strategy results.
MONTHS = (9, 10)
ARMS = (("no-trade", "base"), ("hold-retry", "base"), ("hold-retry", "stress"),
        ("orb-entry", "base"), ("orb-entry", "stress"),
        ("orb-session-flat", "base"), ("orb-session-flat", "stress"))
# NYSE/Arca regular sessions; no early closes in Aug-Oct 2026.
HOLIDAYS = {date(2026, 9, 7)}
# Conservative known issuer-action exclusions; no certificate of completeness.
KNOWN_ACTIONS = {"IBM": (date(2026, 8, 10),), "OIH": ()}
ACTION_SOURCES = {
    "IBM": ("https://newsroom.ibm.com/2026-07-22-IBM-RELEASES-SECOND-QUARTER-RESULTS",
            "https://newsroom.ibm.com/2026-10-21-IBM-RELEASES-THIRD-QUARTER-RESULTS",
            "https://www.ibm.com/investor/help/ibm-stock-splits-and-ibm-stock-dividends"),
    "OIH": ("https://www.vaneck.com/us/en/investments/oil-services-etf-oih/performance/",
            "https://www.vaneck.com/us/en/vaneck-etfs-distributions-schedule-2026.pdf"),
}
SOURCE = "Kibot public unadjusted 1-minute sample; provider-declared consolidated"


def days_for(month):
    if month not in MONTHS:
        raise ValueError("UNREGISTERED_MONTH")
    first = date(2026, month, 1)
    end = date(2026, month+1, 1)
    days = []
    day = date(2026, 8, 1)
    while day < end:
        if day.weekday() < 5 and day not in HOLIDAYS:
            days.append(day)
        day += timedelta(days=1)
    warm = tuple(d for d in days if d < first)[-20:]
    evaluation = tuple(d for d in days if d >= first)
    if len(warm) != 20 or not evaluation:
        raise ValueError("CALENDAR_INCOMPLETE")
    return warm, evaluation


def study(symbol, month, raw):
    url, venue, asset = SAMPLES[symbol]
    inst = InstrumentId(Market.US, venue, symbol, symbol, "USD", asset)
    warm, actual = days_for(month)
    sessions = tuple(session(inst, d) for d in warm+actual)
    calendar = StaticSessionCalendar(sessions)
    window = EvaluationWindow(sessions[20].start, sessions[-1].end)
    actions = [d.isoformat() for d in KNOWN_ACTIONS[symbol] if d in warm+actual]
    extra = {
        "symbol": symbol, "month": month, "year": 2026,
        "study_schema": "e5.15b-kibot-independent-v1", "source": url,
        "source_page": "https://www.kibot.com/free-historical-intraday-data.html",
        "license": "https://www.kibot.com/license.html",
        "calendar_source": "https://www.nyse.com/trade/hours-calendars",
        "action_sources": ACTION_SOURCES[symbol], "known_action_dates": actions,
        "action_completeness_verified": False,
        "price_basis": "provider-declared unadjusted; original decimal prices retained",
        "market_coverage": "provider-declared consolidated; odd-lot completeness unverified",
        "time_assumption": "retrospective bars assumed received at bar end; PIT not certified",
        "fee_scope": "synthetic base/stress rates only; 2022 fee schedule NOT reused",
        "order_tick_assumption": "USD 0.01 synthetic order grid; subcent observations unchanged",
        "planned_arms": len(ARMS), "warmup_sessions": len(warm),
        "eval_sessions": len(actual), "first_day": warm[0].isoformat(),
        "evaluation_start": actual[0].isoformat(), "evaluation_end": actual[-1].isoformat(),
        "status": "BLOCKED",
    }
    rows = []
    try:
        audit = inspect_kibot_unadjusted(raw, inst, calendar, window, source=SOURCE)
    except Exception as exc:
        # No raw prices, rows or user data in logs or artifacts.
        extra["status"] = "SOURCE_ERROR"
        extra["error"] = type(exc).__name__
        save(f"e515b-kibot-{symbol}-{month}", rows, extra)
        return False
    extra.update({
        "file_sha256": audit.file_sha256, "actual_bars": audit.observed_minutes,
        "expected_bars": audit.expected_minutes, "missing_bars": audit.missing_minutes,
        "extra_bars": audit.extra_minutes, "missing_by_session": audit.missing_by_session,
        "complete_sessions": audit.complete_sessions, "expected_sessions": audit.expected_sessions,
    })
    if actions or not audit.events:
        extra["blockers"] = (["KNOWN_ISSUER_ACTION"] if actions else []) + (
            ["MISSING_OR_EXTRA_MINUTE"] if not audit.events else [])
        save(f"e515b-kibot-{symbol}-{month}", rows, extra)
        return True
    errors = []
    for kind, cost in ARMS:
        try:
            strategy = (NoTradeStrategy(DataRequirement("market.bar", MINUTE))
                        if kind == "no-trade" else
                        BuyHoldBaseline(MINUTE, TARGET, D("0.015"), retry_each_session=True)
                        if kind == "hold-retry" else ORBLongStrategy())
            result = run(inst, audit.events, calendar, strategy, cost, SOURCE, window,
                         first_entry_only=kind == "hold-retry",
                         session_flat=kind == "orb-session-flat", e514=True,
                         independent_diagnostics=True)
            rows.append({"symbol": symbol, "month": month, "strategy": kind,
                         "cost": cost, **result})
            print("INDEPENDENT_RUN "+json.dumps(rows[-1]), flush=True)
        except Exception as exc:
            errors.append({"strategy": kind, "cost": cost, "error_type": type(exc).__name__})
    extra["status"] = "PROVISIONAL_COMPLETE" if len(rows) == len(ARMS) else "PARTIAL"
    extra["errors"] = errors
    extra["comparator_complete"] = all(r["entry_coverage"] == "ENTRY_FILLED"
                                      for r in rows if r["strategy"] == "hold-retry"
                                      ) and sum(r["strategy"] == "hold-retry" for r in rows) == 2
    save(f"e515b-kibot-{symbol}-{month}", rows, extra)
    return not errors


def main():
    symbol = sys.argv[1]
    if symbol not in SAMPLES:
        raise SystemExit("UNREGISTERED_SYMBOL")
    try:
        raw = download(SAMPLES[symbol][0], 12_000_000)
    except Exception as exc:
        for month in MONTHS:
            save(f"e515b-kibot-{symbol}-{month}", [], {
                "symbol": symbol, "month": month, "year": 2026,
                "study_schema": "e5.15b-kibot-independent-v1",
                "status": "SOURCE_ERROR", "error": type(exc).__name__,
                "source": SAMPLES[symbol][0], "planned_arms": len(ARMS)})
        raise SystemExit("Independent provider download unavailable") from None
    results = [study(symbol, month, raw) for month in MONTHS]
    if not all(results):
        raise SystemExit("Independent provider study source or execution error")


if __name__ == "__main__":
    main()
