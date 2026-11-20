"""End-to-end E6 offline orchestration, using synthetic market bars only."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from invest_engine.research.candidates import StabilityPolicy
from invest_engine.research.pipeline import (
    PipelineSpec, close_validation, prepare_pipeline, review_pipeline, run_development,
)
from invest_engine.research.regime import RegimePolicy
from invest_engine.research.research_journal import ResearchJournal
from test_fold_execution_e63b import study
from test_parameter_search_e65a import grid


def inputs():
    wf, timing, cases, _, scenario, p = study()
    spec = PipelineSpec(p.plan_id, p.registered_at, wf.spec, grid(), p.policy,
                        p.label_horizon, (p.windows[0],), (p.windows[-1],),
                        regime_policy=RegimePolicy(lookback_returns=2), include_exposure=True)
    return spec, timing, cases, scenario


def test_full_pipeline_and_recover_review_without_market_data(tmp_path):
    spec, timing, cases, scenario = inputs()
    prepared = prepare_pipeline(spec, timing, cases, scenario)
    assert prepared == prepare_pipeline(spec, tuple(reversed(timing)), tuple(reversed(cases)), scenario)
    path = tmp_path / "integrated.db"
    with ResearchJournal(path) as journal:
        result = run_development(journal, prepared, timing, cases, scenario)
        assert result.search.study.complete
        assert result.review.planned_arms == result.review.recorded_arms == 16
        assert result.review.unverified_arms == 16
        assert result.review.phase == "NO_ELIGIBLE_CANDIDATE"
        assert result.review.locked_candidate is None
        assert not result.review.production_authorized
        assert all(c.economic.status == "INCONCLUSIVE" for c in result.review.candidates)
        assert all(a.exposure_study is not None for a in result.search.study.runs)
        assert result == run_development(journal, prepared, timing, cases, scenario)
    with ResearchJournal(path) as journal:
        restored = review_pipeline(journal, prepared)
        assert restored == result.review and restored.to_json() == result.review.to_json()
        closed = close_validation(journal, prepared)
        assert closed.phase == "VALIDATION_CLOSED_NO_CANDIDATE"
        assert closed.locked_candidate is None and not closed.production_authorized
        assert close_validation(journal, prepared) == closed
        with pytest.raises(ValueError, match="VALIDATION_ALREADY_CLOSED"):
            run_development(journal, prepared, timing, cases, scenario)


def test_incomplete_reservation_can_be_reviewed_but_not_closed(tmp_path):
    spec, timing, cases, scenario = inputs()
    prepared = prepare_pipeline(spec, timing, cases, scenario)
    with ResearchJournal(tmp_path / "partial.db") as journal:
        journal.register(prepared.plan)
        journal.reserve_search(prepared.plan.plan_id, prepared.reservation)
        snapshot = review_pipeline(journal, prepared)
        assert snapshot.phase == "RETRY_REQUIRED"
        assert snapshot.recorded_arms == 0
        with pytest.raises(ValueError, match="CANNOT_CLOSE_INCOMPLETE"):
            close_validation(journal, prepared)
        result = run_development(journal, prepared, timing, cases, scenario)
        assert result.review.recorded_arms == 16


def test_changed_spec_scenario_and_stability_rejected(tmp_path):
    spec, timing, cases, scenario = inputs()
    prepared = prepare_pipeline(spec, timing, cases, scenario)
    with ResearchJournal(tmp_path / "bound.db") as journal:
        with pytest.raises(ValueError, match="PREREGISTRATION_MISMATCH"):
            run_development(journal, prepared, timing, cases, replace(scenario, cash=D("200000")))
        journal.register(prepared.plan)
        journal.reserve_search(prepared.plan.plan_id, prepared.reservation)
        altered = prepare_pipeline(replace(spec, stability_policy=StabilityPolicy(min_time_blocks=4)),
                                   timing, cases, scenario)
        with pytest.raises(ValueError, match="RESERVATION_ALREADY_FIXED"):
            run_development(journal, altered, timing, cases, scenario)
        assert journal.get(prepared.plan.plan_id).evidence == ()


def test_final_metadata_must_match_universe_and_range():
    spec, timing, cases, scenario = inputs()
    with pytest.raises(ValueError, match="HOLDOUT_METADATA_RANGE"):
        replace(spec, final_windows=(replace(spec.final_windows[0],
                                             end=spec.walk_forward.holdout_end+spec.label_horizon),))
    with pytest.raises(ValueError, match="PARTITION_UNIVERSE_MISMATCH"):
        replace(spec, final_windows=())
    with pytest.raises(ValueError, match="INSTRUMENT_CURRENCY_MISMATCH"):
        replace(spec, final_windows=(replace(spec.final_windows[0], currency="KRW"),))
    with pytest.raises(ValueError, match="HOLDOUT_DATASET_REUSED"):
        prepared = prepare_pipeline(spec, timing, cases, scenario)
        replace(prepared.plan, windows=tuple(replace(w, data_sha256=spec.initial_windows[0].data_sha256)
                                              if w.split == "test" else w for w in prepared.plan.windows))
