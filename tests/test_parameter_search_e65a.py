"""Bounded grid evaluation over actual synthetic E5 fold replays."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from invest_engine.research.fold_execution import fixed_candidates
from invest_engine.research.parameter_search import (
    SearchGrid, build_search_manifest, execute_search, prepare_search,
)
from invest_engine.research.research_journal import ResearchJournal
from test_fold_execution_e63b import study


def grid():
    return SearchGrid("demo-grid", (1,), (5,), (20,), (2,),
                      (D("1.0"), D("2")), 2, 16)


def test_deterministic_grid_ids_and_canonical_axis_values():
    wf, _, _, _, scenario, _ = study()
    one = build_search_manifest(grid(), wf, scenario)
    two = build_search_manifest(replace(grid(), volume_multipliers=(D("2.00"), D("1"))),
                                wf, scenario)
    assert one == two and one.digest == two.digest
    assert one.planned_arms == 16
    assert len({r.candidate_id for r in one.rules}) == 2
    assert all(r.params.target_fraction == scenario.target for r in one.rules)


def test_budget_and_inactive_dimensions_fail_closed():
    wf, _, _, _, scenario, _ = study()
    with pytest.raises(ValueError, match="CANDIDATE_BUDGET_EXCEEDED"):
        replace(grid(), candidate_budget=1)
    with pytest.raises(ValueError, match="REPLAY_BUDGET_EXCEEDED"):
        build_search_manifest(replace(grid(), replay_arm_budget=15), wf, scenario)
    with pytest.raises(ValueError, match="INACTIVE_MARKET_AXIS"):
        build_search_manifest(replace(grid(), opening_kr_minutes=(5, 10),
                                      candidate_budget=4), wf, scenario)
    with pytest.raises(ValueError, match="INVALID_SEARCH_VOLUME_AXIS"):
        replace(grid(), volume_multipliers=(D("1"), D("1.00")))
    with pytest.raises(ValueError, match="INVALID_SEARCH_AXIS"):
        replace(grid(), prior_sessions=(21,))


def test_two_candidate_full_search_and_no_automatic_promotion(tmp_path):
    wf, timing, cases, _, scenario, p = study()
    prepared = prepare_search(grid(), wf, timing, cases, scenario)
    p = replace(p, windows=(p.windows[0], *(a.window for a in prepared.folds), p.windows[-1]),
                candidates=fixed_candidates(prepared.manifest.rules, scenario, wf))
    path = tmp_path / "grid.sqlite"
    with ResearchJournal(path) as journal:
        journal.register(p)
        result = execute_search(journal, p.plan_id, prepared, wf, timing, cases, scenario)
        assert result.study.complete, result.study.runs
        assert result.planned_arms == len(result.study.runs) == 16
        assert len(result.assessments) == 2
        assert all(a.status == "INCONCLUSIVE" for a in result.assessments)
        assert not result.selection_performed
        state = journal.get(p.plan_id)
        assert len(state.evidence) == 16 and not state.validation_locked
        assert execute_search(journal, p.plan_id, prepared, wf, timing, cases, scenario) == result
        assert len(journal.get(p.plan_id).evidence) == 16
    with ResearchJournal(path) as journal:
        assert journal.get(p.plan_id) == state


def test_manifest_or_registered_budget_changes_rejected_before_execution(tmp_path):
    wf, timing, cases, _, scenario, p = study()
    prepared = prepare_search(grid(), wf, timing, cases, scenario)
    p = replace(p, windows=(p.windows[0], *(a.window for a in prepared.folds), p.windows[-1]),
                candidates=fixed_candidates(prepared.manifest.rules, scenario, wf))
    with ResearchJournal(tmp_path / "grid.sqlite") as journal:
        journal.register(p)
        bad = replace(prepared, manifest=replace(prepared.manifest, planned_arms=999))
        with pytest.raises(ValueError, match="SEARCH_PREREGISTRATION_MISMATCH"):
            execute_search(journal, p.plan_id, bad, wf, timing, cases, scenario)
        other = prepare_search(replace(grid(), replay_arm_budget=17), wf, timing, cases, scenario)
        with pytest.raises(ValueError, match="FOLD_RESEARCH_PLAN_BINDING_MISMATCH"):
            execute_search(journal, p.plan_id, other, wf, timing, cases, scenario)
        assert journal.get(p.plan_id).evidence == ()
