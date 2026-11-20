"""Prespecified exploratory turnover study on previously observed v4 windows."""
from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal as D

from alpaca_raw_minute_pilot import MONTHS, SYMBOLS, actions, build_grid, fetch_tape
from e513_market_study import MINUTE, TARGET, run, save
from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.research.evaluation import EvaluationWindow, validate_window
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.strategies.orb import ORBLongStrategy, ORBParameters
from invest_engine.strategies.orb_screen import ORBScreen, ScreenedORB

COSTS = ("base", "stress")
SOURCE = "Alpaca raw SIP v4 screen; reduced-turnover reused 2022 study"
SCREENS = {
    "orb-volume-control": None,
    "orb-weekly": ORBScreen(once_per_week=True),
    "orb-range200": ORBScreen(minimum_range_bps=D("200")),
    "orb-combined": ORBScreen(True, D("200")),
}


def make_strategy(kind):
    params = ORBParameters(volume_multiplier=D("2"))
    screen = SCREENS[kind]
    return ORBLongStrategy(params) if screen is None else ScreenedORB(params, screen)


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
    report = {"symbol": symbol, "month": month, "year": 2022, "planned_arms": 12,
              "study_schema": "alpaca-sip-reduced-turnover-v1", "status": "SOURCE_ERROR",
              "holdout_accessed": False, "execution_certified": False}
    rows, errors = [], []
    try:
        inst, sessions, first, last = build_grid(symbol, month)
        ca, ca_hash = actions(symbol, first, last, headers)
        action_counts = {kind: sum(x["kind"] == kind for x in ca) for kind in sorted({x["kind"] for x in ca})}
        report.update({"first_session": str(first), "last_session": str(last),
                       "action_counts": action_counts, "action_classifications": ca,
                       "action_sha256": ca_hash, "action_search_margin_days": 90})
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
            for kind in ("no-trade", "hold-retry", *SCREENS):
                for cost in COSTS:
                    try:
                        strat = (NoTradeStrategy(DataRequirement("market.bar", MINUTE))
                            if kind == "no-trade" else
                            BuyHoldBaseline(MINUTE, TARGET, D("0.015"), retry_each_session=True)
                            if kind == "hold-retry" else make_strategy(kind))
                        result = run(inst, events, calendar, strat, cost, SOURCE, window,
                                     first_entry_only=kind == "hold-retry",
                                     session_flat=kind in SCREENS, e514=True, fee_replay=True)
                        row = {"symbol": symbol, "month": month, "year": 2022,
                               "strategy": kind, "cost": cost, **result}
                        rows.append(row)
                        print("TURNOVER_RUN "+json.dumps(row), flush=True)
                    except Exception as exc:
                        errors.append({"strategy": kind, "cost": cost, "error_type": type(exc).__name__})
                        print("TURNOVER_ARM_FAILED "+json.dumps(errors[-1]), flush=True)
            report["status"] = "PROVISIONAL_COMPLETE" if len(rows) == 12 else "PARTIAL"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        if str(exc) in {"HTTP_400", "HTTP_401", "HTTP_403", "HTTP_429"}:
            report["error_code"] = str(exc)
    report["errors"] = errors
    save(f"alpaca-reduced-turnover-{symbol}-{month}", rows, report)
    if report["status"] in ("SOURCE_ERROR", "PARTIAL"):
        raise SystemExit("TURNOVER_STUDY_INCOMPLETE")


if __name__ == "__main__":
    main()
