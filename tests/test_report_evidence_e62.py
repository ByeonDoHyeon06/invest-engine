"""E5 report -> E6 structurally reconciled, explicitly unverified arm."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar
from invest_engine.domain.primitives import Market
from invest_engine.research.candidates import Candidate, EvaluationPolicy, ResearchPlan, ResearchWindow
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.report import sha256
from invest_engine.research.report_evidence import ReportBinding, evidence_from_report, report_context_sha256
from invest_engine.research.research_journal import ResearchJournal
from test_us_fee_audit_e514b import INST, fixture

DAY = timedelta(days=1)


def make():
    report, events = fixture(dated=True)
    sessions = []
    for e in events[::4]:
        bar = e.payload
        assert isinstance(bar, Bar)
        sessions.append(TradingSession(Market.US, "XNAS", bar.start, bar.start+timedelta(minutes=4)))
    calendar = StaticSessionCalendar(tuple(sessions))
    window = EvaluationWindow(sessions[-1].start, sessions[-1].end)
    scenario = sha256("fixture-base-and-stress")
    ctx = report_context_sha256(calendar, window, scenario)
    w = ResearchWindow("val", INST.key, "USD", "validation", window.start, window.end,
                       report.dataset_sha256, ctx)
    train = replace(w, window_id="train", split="train", start=w.start-50*DAY,
                    end=w.end-50*DAY, data_sha256=sha256("train"))
    test = replace(w, window_id="test", split="test", start=w.start+50*DAY,
                   end=w.end+50*DAY, data_sha256=sha256("test"))
    c = Candidate("alpha", "v1", "a"*40, sha256("alpha"), train.end)
    p = ResearchPlan("demo", train.end, (train, w, test), (c,), ("base", "stress"),
                     EvaluationPolicy(1, D("0.1"), D("0"), DAY), DAY,
                     (("no-trade", sha256("cash")), ("buy-hold", sha256("hold"))))
    bind = ReportBinding(p.digest, w.window_id, c.candidate_id, "base", report.config_sha256)
    return report, events, calendar, window, scenario, p, bind


def test_actual_report_reconciles_and_persists_as_unverified(tmp_path):
    report, events, calendar, window, scenario, p, bind = make()
    a = evidence_from_report(p, bind, report, events, calendar, window, scenario_identity=scenario)
    assert a.report_sha256 == sha256(report) and a.run_sha256 == report.run_sha256
    assert a.complete and a.entry_fills == report.entry_fill_count
    assert a.net_pnl == dict(report.net_pnl)["USD"]
    assert not a.provenance_verified and not a.cost_verified and not a.execution_validated
    path = tmp_path / "evidence.db"
    with ResearchJournal(path) as journal:
        journal.register(p)
        state = journal.record(p.plan_id, a)
    with ResearchJournal(path) as journal:
        assert journal.get(p.plan_id) == state


def test_mismatched_config_dataset_and_scenario_fail():
    report, events, calendar, window, scenario, p, bind = make()

    def convert(r=report, b=bind, es=events, sc=scenario):
        return evidence_from_report(p, b, r, es, calendar, window, scenario_identity=sc)

    with pytest.raises(ValueError, match="PLAN_OR_CONFIG"):
        convert(b=replace(bind, expected_report_config_sha256="f"*64))
    with pytest.raises(ValueError, match="DATASET_MISMATCH"):
        convert(r=replace(report, dataset_sha256="f"*64))
    with pytest.raises(ValueError, match="CONTEXT_MISMATCH"):
        convert(sc="f"*64)
    with pytest.raises(ValueError, match="MINUTE"):
        convert(es=events[1:])


def test_trace_and_metrics_reconciliation_reject_tampering():
    report, events, calendar, window, scenario, p, bind = make()

    def convert(r):
        return evidence_from_report(p, bind, r, events, calendar, window, scenario_identity=scenario)

    with pytest.raises(ValueError, match="METRIC_RECONCILIATION"):
        convert(replace(report, net_pnl=(("USD", D("12345")),)))
    with pytest.raises(ValueError, match="TRACE_COVERAGE_MISMATCH"):
        convert(replace(report, decisions=report.decisions[:-1]))
    with pytest.raises(ValueError, match="FILL_COST_RECONCILIATION"):
        convert(replace(report, total_fees=(("USD", D("123")),)))
