"""Preregistered daily research sensitivity over Alpaca adjusted SIP.

No raw price data artifacts, no order/account access, no holdout access.
Adjusted historical prices are NOT as-traded executable prices.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from decimal import Decimal as D

import exchange_calendars as xcals

from e513_market_study import DAY, RULES, DailyRule, run, save
from prepare_market_panel import FIELDS, alpaca_daily, coverage, load_plan
from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement

YEARS = (2021, 2022, 2023, 2024, 2025)
COST_LEVELS = ("base", "stress")
SOURCE = "Alpaca retrospective SIP adjustment=all; research proxy, not as-traded"


class DailyOneShotHold(DailyRule):
    """Exactly one initial signal, next-bar modeled fill or no-entry.

    The inherited DailyRule retries the first three bars; suppress those
    additional signals rather than accidentally benchmarking rebalancing.
    """
    def on_event(self, ev, ctx):
        if len(ctx.bars_for(self.inst, DAY)) != 1:
            return ()
        return super().on_event(ev, ctx)


def materialize(symbol, rows, cal):
    # Provisional composite US venue for calendar matching, not verified MIC.
    inst = InstrumentId(Market.US, "US-SIP", symbol, symbol, "USD")
    sessions = []
    events = []
    for i, values in enumerate(sorted(rows)):
        row = dict(zip(FIELDS, values, strict=True))
        day = row["date"]
        start = cal.session_open(day).to_pydatetime()
        end = cal.session_close(day).to_pydatetime()
        session = TradingSession(inst.market, inst.venue, start, end)
        sessions.append(session)
        bar = Bar(start, end, *(D(row[k]) for k in FIELDS[1:]), interval=DAY)
        events.append(EventEnvelope(f"{symbol}:{day}", "market.bar", SOURCE,
                                    inst, end, end, end, i, bar))
    return inst, tuple(events), StaticSessionCalendar(tuple(sessions))


def matched_summary(rows):
    """Paired arithmetic means over comparable independent accounts only."""
    by_key = {(row["symbol"], row["strategy"], row["cost"]): row for row in rows}
    summary = {}
    for strategy in RULES:
        if strategy in ("no-trade", "hold"):
            continue
        for cost in COST_LEVELS:
            comparable = []
            for row in rows:
                if row["strategy"] != strategy or row["cost"] != cost:
                    continue
                cash = by_key.get((row["symbol"], "no-trade", cost))
                hold = by_key.get((row["symbol"], "hold", cost))
                other_cost = "stress" if cost == "base" else "base"
                # Keep the same matched cohort across both cost arms; no failed
                # or unentered benchmark may masquerade as a zero-return hold.
                other = by_key.get((row["symbol"], strategy, other_cost))
                other_cash = by_key.get((row["symbol"], "no-trade", other_cost))
                other_hold = by_key.get((row["symbol"], "hold", other_cost))
                if (cash is None or hold is None or other is None or other_cash is None
                        or other_hold is None or not hold["buys"] or not other_hold["buys"]):
                    continue
                pnl = D(row["pnl"])
                excess = pnl-max(D(cash["pnl"]), D(hold["pnl"]))
                comparable.append((pnl, excess))
            n = len(comparable)
            summary[f"{strategy}:{cost}"] = {
                "matched_windows": n,
                "mean_account_return_pct": str(sum((p for p, _ in comparable), D(0))/n/1000) if n else None,
                "mean_excess_pct_points": str(sum((e for _, e in comparable), D(0))/n/1000) if n else None,
                "positive_windows": sum(p > 0 for p, _ in comparable),
                "beat_both_windows": sum(e > 0 for _, e in comparable),
            }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("year", type=int, choices=YEARS)
    args = parser.parse_args()
    year = args.year
    key, secret = os.environ.get("ALPACA_DATA_KEY"), os.environ.get("ALPACA_DATA_SECRET")
    if not key or not secret:
        raise SystemExit("MISSING_DATA_CREDENTIALS")
    plan, plan_hash = load_plan()
    universe = tuple(x["symbol"] for x in plan["instruments"] if x["market"] == "US")
    calendar = xcals.get_calendar("XNYS", start=f"{year}-01-01", end=f"{year}-12-31")
    expected = {x.date().isoformat() for x in calendar.sessions}
    rows, windows, errors = [], [], []
    for symbol in universe:
        record = {"symbol": symbol, "year": year, "status": "SOURCE_ERROR"}
        try:
            prices, hashes, invalid = alpaca_daily(symbol, year, key, secret, adjustment="all")
            audit = coverage(prices, expected, invalid)
            record.update({"source_sha256": hashes, **audit})
            if record["status"] == "STRUCTURAL_COMPLETE":
                inst, events, cal = materialize(symbol, prices, calendar)
                for strategy in RULES:
                    for cost in COST_LEVELS:
                        try:
                            implementation = (NoTradeStrategy(DataRequirement("market.bar", DAY))
                                              if strategy == "no-trade" else
                                              DailyOneShotHold("hold", inst) if strategy == "hold" else
                                              DailyRule(strategy, inst))
                            result = run(inst, events, cal, implementation, cost, SOURCE)
                            row = {"symbol": symbol, "year": year, "strategy": strategy, "cost": cost,
                                   **result}
                            rows.append(row)
                            print("ALPACA_DAILY_RUN "+json.dumps(row), flush=True)
                        except Exception as exc:
                            errors.append({"symbol": symbol, "strategy": strategy,
                                           "cost": cost, "error_type": type(exc).__name__})
                record["status"] = ("COMPLETE_RESEARCH_PROXY"
                    if sum(r["symbol"] == symbol for r in rows) == len(RULES)*len(COST_LEVELS)
                    else "PARTIAL")
        except Exception as exc:
            record["status"] = "SOURCE_OR_PREPARATION_ERROR"
            record["error_type"] = type(exc).__name__
        windows.append(record)
        print("ALPACA_DAILY_WINDOW "+json.dumps({k: record.get(k) for k in (
            "symbol", "year", "status", "observed_rows", "expected_sessions",
            "missing_sessions", "duplicates", "invalid_rows", "zero_volume_rows", "error_type")}),
            flush=True)
        time.sleep(.65)
    counts = {status: sum(w["status"] == status for w in windows) for status in (
        "COMPLETE_RESEARCH_PROXY", "BLOCKED_COVERAGE", "SOURCE_OR_PREPARATION_ERROR", "PARTIAL")}
    extra = {"study_schema": "alpaca-daily-adjusted-proxy-v1", "year": year,
             "split": "development" if year <= 2023 else "previously-observable-validation",
             "dataset_plan_sha256": plan_hash, "price_basis": "provider adjustment=all",
             "ticker_mapping": "disabled", "not_execution_certified": True, "holdout_accessed": False,
             "planned_arms": len(universe)*len(RULES)*len(COST_LEVELS),
             "window_status_counts": counts, "windows": windows, "errors": errors,
             "paired_summary": matched_summary(rows),
             "limitations": "cold-start independent years; adjusted prices; synthetic cost and fill model"}
    save(f"alpaca-adjusted-daily-{year}", rows, extra)
    if errors or counts["SOURCE_OR_PREPARATION_ERROR"] or not rows:
        raise SystemExit("RESEARCH_PANEL_INCOMPLETE")


if __name__ == "__main__":
    main()
