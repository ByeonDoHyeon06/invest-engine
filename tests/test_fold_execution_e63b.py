"""Real E5 replay over synthetic strict minute tapes; no market claims."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.backtest import BacktestSettings
from invest_engine.research.candidates import EvaluationPolicy, ResearchPlan, ResearchWindow
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.fills import BarFillPolicy
from invest_engine.research.fold_execution import (
    FixedRule, FoldInput, FoldScenario, execute_validation, fixed_candidates, prepare_validation,
)
from invest_engine.research.report import sha256
from invest_engine.research.research_journal import ResearchJournal
from invest_engine.research.walk_forward import SampleTiming, WalkForwardSpec, plan_walk_forward
from invest_engine.strategies.orb import ORBParameters
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits

NOW = datetime(2022, 9, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
MIN = timedelta(minutes=1)
INST = InstrumentId(Market.US, "XNAS", "fixture", "FIX", "USD")


def study():
    spec = WalkForwardSpec(NOW, NOW+26*DAY, NOW+30*DAY, NOW+32*DAY,
                           21*DAY, 2*DAY, 2*DAY, DAY, (INST.key,), 2, 2)
    sessions = tuple(TradingSession(Market.US, INST.venue,
                    NOW+day*DAY+timedelta(hours=14), NOW+day*DAY+timedelta(hours=14)+4*MIN)
                    for day in range(26))
    events = []
    timing = []
    for day, session in enumerate(sessions):
        for j, values in enumerate((
            ("100", "101", "99", "100", "4000"),
            ("100", "103", "99", "102", "8000" if day >= 22 else "4000"),
            ("102", "103", "100", "102", "4000"),
            ("103", "104", "102", "103", "4000"),
        )):
            start = session.start+j*MIN
            end = start+MIN
            bar = Bar(start, end, *(D(v) for v in values), interval=MIN)
            identity = f"day{day}-bar{j}"
            events.append(EventEnvelope(identity, "market.bar", "synthetic", INST,
                                        end, end, end, len(events), bar))
            timing.append(SampleTiming(identity, INST.key, end, end, end, end+MIN, end+MIN))
    wf = plan_walk_forward(spec, tuple(timing))
    assert wf.eligible and len(wf.folds) == 2
    cfg = TradingConfig("sim", (MonetaryRules("USD", D("0.01")),),
                        ((INST.key, InstrumentRules(D("0.01"), D("1"))),))
    scenario = FoldScenario(BacktestSettings(code_sha="a"*40), D("100000"), D("0.05"),
                            D("0.015"), RiskLimits(), BarFillPolicy(),
                            BarFillPolicy(spread_bps=D("20"), impact_bps=D("20")))
    rules = (FixedRule("orb", ORBParameters(opening_us=MIN, atr_period=2)),)
    cases = tuple(FoldInput(
        fold.fold_id, INST.key, StaticSessionCalendar(sessions[d-20:d+2]),
        EvaluationWindow(sessions[d].start, sessions[d+1].end),
        tuple(replace(event, ingest_ordinal=i) for i, event in
              enumerate(events[(d-20)*4:(d+2)*4])), cfg, replace(cfg, fee_rate=D("0.0025")))
        for fold, d in zip(wf.folds, (22, 24), strict=True))
    prepared = prepare_validation(wf, tuple(timing), cases, rules, scenario)
    train = ResearchWindow("initial", INST.key, "USD", "train", NOW, NOW+20*DAY,
                           sha256("train-metadata"), sha256("train-context"))
    test = ResearchWindow("final", INST.key, "USD", "test", spec.holdout_start, spec.holdout_end,
                          sha256("reserved-test"), sha256("test-context"))
    p = ResearchPlan("folds", NOW, (train, *(c.window for c in prepared), test),
                     fixed_candidates(rules, scenario, wf), ("base", "stress"),
                     EvaluationPolicy(1, D("0.1"), D("0"), DAY), MIN,
                     scenario.baseline_configs)
    return wf, tuple(timing), cases, rules, scenario, p


def test_complete_matrix_replays_and_reconciles_into_durable_journal(tmp_path):
    wf, timing, cases, rules, scenario, p = study()
    path = tmp_path / "research.sqlite"
    with ResearchJournal(path) as journal:
        journal.register(p)
        result = execute_validation(journal, p.plan_id, wf, timing, cases, rules, scenario)
        assert result.complete, result.runs
        assert len(result.runs) == 12
        state = journal.get(p.plan_id)
        assert len(state.evidence) == 12
        assert all(a.report_sha256 and a.complete and not a.provenance_verified
                   and not a.cost_verified and not a.execution_validated for a in state.evidence)
        assert all(a.entry_fills > 0 for a in state.evidence if a.candidate_id == "buy-hold")
        assert state.assess("orb").status == "INCONCLUSIVE"
        assert execute_validation(journal, p.plan_id, wf, timing, cases, rules, scenario) == result
    with ResearchJournal(path) as journal:
        assert journal.get(p.plan_id) == state
        locked = journal.lock_validation(p.plan_id)
        assert locked.locked_candidate is None
        with pytest.raises(ValueError, match="ALREADY_LOCKED"):
            execute_validation(journal, p.plan_id, wf, timing, cases, rules, scenario)


def test_all_folds_required_and_no_substituted_costs():
    wf, timing, cases, rules, scenario, _ = study()
    with pytest.raises(ValueError, match="MATRIX_INCOMPLETE"):
        prepare_validation(wf, timing, cases[:1], rules, scenario)
    with pytest.raises(ValueError, match="UNMATCHED_COST_POLICIES"):
        prepare_validation(wf, timing, (replace(cases[0], stress_config=replace(
            cases[0].stress_config, account_id="other")), cases[1]), rules, scenario)
    with pytest.raises(ValueError, match="PLAN_INELIGIBLE_OR_MODIFIED"):
        prepare_validation(replace(wf, timing_sha256="b"*64), timing, cases, rules, scenario)
    bad = replace(cases[0], events=(replace(cases[0].events[0], ingest_ordinal=1),
                                         *cases[0].events[1:]))
    with pytest.raises(ValueError, match="LOCAL_CONTIGUOUS_ORDINALS"):
        prepare_validation(wf, timing, (bad, cases[1]), rules, scenario)


def test_purged_validation_sample_must_not_be_scored():
    wf, timing, cases, rules, scenario, _ = study()
    sid = wf.folds[0].validation_ids[0]
    altered = tuple(replace(t, label_available_at=wf.folds[0].validation_end+DAY)
                    if t.sample_id == sid else t for t in timing)
    new = plan_walk_forward(wf.spec, altered)
    assert new.eligible
    with pytest.raises(ValueError, match="VALIDATION_SAMPLE_COVERAGE"):
        prepare_validation(new, altered, cases, rules, scenario)


def test_research_plan_pins_rule_and_scenario_before_execution(tmp_path):
    wf, timing, cases, rules, scenario, p = study()
    with ResearchJournal(tmp_path / "research.sqlite") as journal:
        journal.register(p)
        with pytest.raises(ValueError, match="PLAN_BINDING_MISMATCH"):
            execute_validation(journal, p.plan_id, wf, timing, cases, rules,
                               replace(scenario, cash=D("200000")))
        assert journal.get(p.plan_id).evidence == ()
