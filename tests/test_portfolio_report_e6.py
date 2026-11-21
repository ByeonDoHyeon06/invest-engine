from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.portfolio_report import (
    PortfolioBacktestReport,
    PortfolioExecutionRecord,
    PortfolioSessionWindow,
    summarize_portfolio_executions,
)
from invest_engine.research.report import BacktestReport, EquityPoint
from invest_engine.trading.models import Side


SESSION_START = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
SESSION_END = SESSION_START + timedelta(minutes=390)
SESSION_ID = "US:2026-11-20"
A = InstrumentId(Market.US, "XNAS", "US-A", "AAA", "USD")
B = InstrumentId(Market.US, "XNYS", "US-B", "BBB", "USD")


def execution(
    execution_id: str,
    side: Side,
    quantity: str,
    price: str,
    at_minutes: int,
    before: str,
    after: str,
    *,
    fee: str,
    tax: str = "0",
    realized: str = "0",
    instrument: InstrumentId = A,
    session_id: str = SESSION_ID,
) -> PortfolioExecutionRecord:
    return PortfolioExecutionRecord(
        execution_id=execution_id,
        intent_id="intent:" + execution_id,
        source_frame_id="frame:1",
        market_event_id="bar:" + execution_id,
        instrument=instrument,
        side=side,
        quantity=D(quantity),
        price=D(price),
        fee=D(fee),
        tax=D(tax),
        realized_pnl=D(realized),
        occurred_at=SESSION_START + timedelta(minutes=at_minutes),
        position_before=D(before),
        position_after=D(after),
        session_id=session_id,
    )


def partial_cycle() -> tuple[PortfolioExecutionRecord, ...]:
    return (
        execution("buy-1", Side.BUY, "4", "100", 30, "0", "4", fee="0.40"),
        execution("buy-2", Side.BUY, "6", "101", 31, "4", "10", fee="0.60"),
        execution(
            "sell-1",
            Side.SELL,
            "3",
            "105",
            60,
            "10",
            "7",
            fee="0.30",
            tax="0.03",
            realized="11.67",
        ),
        execution(
            "sell-2",
            Side.SELL,
            "7",
            "104",
            61,
            "7",
            "0",
            fee="0.70",
            tax="0.07",
            realized="19.26",
        ),
    )


def session_window() -> PortfolioSessionWindow:
    return PortfolioSessionWindow(SESSION_ID, SESSION_START, SESSION_END)


def test_partial_entry_and_exit_fills_form_one_completed_cycle():
    summary = summarize_portfolio_executions(partial_cycle(), (session_window(),))

    assert len(summary.cycles) == 1
    cycle = summary.cycles[0]
    assert cycle.entry_fill_ids == ("buy-1", "buy-2")
    assert cycle.exit_fill_ids == ("sell-1", "sell-2")
    assert cycle.entry_quantity == cycle.exit_quantity == D("10")
    assert cycle.turnover == D("2049")
    assert cycle.fees == D("2.00")
    assert cycle.taxes == D("0.10")
    assert cycle.net_pnl == D("30.93")
    assert cycle.gross_pnl == D("33.03")


def test_execution_transition_mismatch_or_cross_session_cycle_is_rejected():
    inconsistent = replace(
        partial_cycle()[1],
        position_before=D("3"),
        position_after=D("9"),
    )
    with pytest.raises(ValueError, match="position transition"):
        summarize_portfolio_executions(
            (partial_cycle()[0], inconsistent),
            (session_window(),),
        )

    next_session = PortfolioSessionWindow(
        "US:2026-11-21",
        SESSION_START + timedelta(days=1),
        SESSION_END + timedelta(days=1),
    )
    cross_session_close = replace(
        partial_cycle()[-1],
        session_id=next_session.session_id,
        occurred_at=next_session.start + timedelta(minutes=31),
    )
    with pytest.raises(ValueError, match="cross session"):
        summarize_portfolio_executions(
            (partial_cycle()[0], cross_session_close),
            (session_window(), next_session),
        )


def test_fill_counts_remain_distinct_from_completed_cycles():
    executions = partial_cycle()
    summary = summarize_portfolio_executions(executions, (session_window(),))

    assert len(executions) == 4
    assert summary.sessions[0].entry_fill_count == 2
    assert summary.sessions[0].exit_fill_count == 2
    assert summary.sessions[0].completed_cycle_count == 1


def test_session_time_in_market_is_union_of_overlapping_symbol_cycles():
    executions = (
        execution("a-buy", Side.BUY, "1", "100", 30, "0", "1", fee="0"),
        execution(
            "b-buy", Side.BUY, "1", "100", 60, "0", "1", fee="0", instrument=B
        ),
        execution(
            "a-sell", Side.SELL, "1", "105", 90, "1", "0", fee="0", realized="5"
        ),
        execution(
            "b-sell",
            Side.SELL,
            "1",
            "102",
            120,
            "1",
            "0",
            fee="0",
            realized="2",
            instrument=B,
        ),
    )

    summary = summarize_portfolio_executions(executions, (session_window(),))

    assert summary.sessions[0].time_in_market == timedelta(minutes=90)


def test_zero_fill_session_is_reported_and_positive_symbol_share_is_exact():
    next_window = PortfolioSessionWindow(
        "US:2026-11-21",
        SESSION_START + timedelta(days=1),
        SESSION_END + timedelta(days=1),
    )
    executions = (
        execution("a-buy", Side.BUY, "1", "100", 30, "0", "1", fee="0"),
        execution(
            "b-buy", Side.BUY, "1", "100", 31, "0", "1", fee="0", instrument=B
        ),
        execution(
            "a-sell", Side.SELL, "1", "130", 60, "1", "0", fee="0", realized="30"
        ),
        execution(
            "b-sell",
            Side.SELL,
            "1",
            "110",
            61,
            "1",
            "0",
            fee="0",
            realized="10",
            instrument=B,
        ),
    )

    summary = summarize_portfolio_executions(
        executions,
        (session_window(), next_window),
    )

    assert summary.sessions[1].completed_cycle_count == 0
    assert summary.sessions[1].entry_fill_count == 0
    assert summary.sessions[1].exit_fill_count == 0
    assert summary.sessions[1].time_in_market == timedelta(0)
    assert tuple(row.instrument for row in summary.symbols) == (A, B)
    assert summary.largest_positive_symbol_pnl_share == D("0.75")


def test_no_positive_symbol_pnl_produces_null_concentration():
    executions = (
        execution("a-buy", Side.BUY, "1", "100", 30, "0", "1", fee="0"),
        execution(
            "b-buy", Side.BUY, "1", "100", 31, "0", "1", fee="0", instrument=B
        ),
        execution(
            "a-sell", Side.SELL, "1", "99", 60, "1", "0", fee="0", realized="-1"
        ),
        execution(
            "b-sell",
            Side.SELL,
            "1",
            "100",
            61,
            "1",
            "0",
            fee="0",
            realized="0",
            instrument=B,
        ),
    )

    summary = summarize_portfolio_executions(executions, (session_window(),))

    assert summary.largest_positive_symbol_pnl_share is None


def account_report() -> BacktestReport:
    point = EquityPoint(SESSION_END, (("USD", D("100030.93")),), True)
    return BacktestReport(
        dataset_sha256="d" * 64,
        config_sha256="c" * 64,
        state_digest="s" * 64,
        run_sha256="a" * 64,
        event_count=4,
        by_currency_start=(("USD", D("100000")),),
        by_currency_end=point.by_currency,
        max_drawdown=(("USD", D("0")),),
        entry_fill_count=2,
        exit_fill_count=2,
        total_fees=(("USD", D("2.00")),),
        total_taxes=(("USD", D("0.10")),),
        realized_exit_pnl=(("USD", D("30.93")),),
        equity=(point,),
        decisions=(),
        fills=(),
        net_pnl=(("USD", D("30.93")),),
        turnover=(("USD", D("2049")),),
        profit_factor=(("USD", None),),
        exit_fill_expectancy=(("USD", D("15.465")),),
        notes=("fixture account report",),
    )


def test_portfolio_report_export_is_canonical_and_repeatable(tmp_path):
    executions = partial_cycle()
    summary = summarize_portfolio_executions(executions, (session_window(),))
    report = PortfolioBacktestReport(
        account_report=account_report(),
        universe_decisions=(),
        executions=executions,
        cycles=summary.cycles,
        sessions=summary.sessions,
        symbols=summary.symbols,
        largest_positive_symbol_pnl_share=summary.largest_positive_symbol_pnl_share,
        blocked_checkpoint_count=0,
        run_sha256="e" * 64,
        notes=("offline fixture",),
    )
    first = tmp_path / "first"
    second = tmp_path / "second"

    report.export(first)
    report.export(second)

    expected = {
        "account/decisions.jsonl",
        "account/equity.jsonl",
        "account/fills.jsonl",
        "account/report.json",
        "cycles.jsonl",
        "executions.jsonl",
        "report.json",
        "sessions.jsonl",
        "symbols.jsonl",
        "universe_decisions.jsonl",
    }
    first_files = {str(path.relative_to(first)) for path in first.rglob("*") if path.is_file()}
    assert first_files == expected
    assert {
        str(path.relative_to(first)): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    } == {
        str(path.relative_to(second)): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert b'"run_sha256":"' + b"e" * 64 + b'"' in (first / "report.json").read_bytes()
