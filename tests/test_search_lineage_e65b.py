"""Local validation lineage and conservative descriptive robustness."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from invest_engine.research.candidates import (
    BASELINES, ResearchRegistry, SearchArmOutcome, SearchReservation, StabilityPolicy,
)
from invest_engine.research.report import sha256
from invest_engine.research.research_journal import ResearchJournal
from invest_engine.research.robustness import assess_stability
from test_research_candidates_e6 import DAY, NOW, arm, plan


def multi_plan():
    p = plan()
    template = p.windows[1]
    validation = tuple(replace(template, window_id=f"v{i}", start=NOW+day*DAY,
                               end=NOW+(day+1)*DAY, data_sha256=sha256(("v", i)))
                       for i, day in enumerate((10, 13, 16)))
    # Two different instruments sharing the first day: one temporal block.
    peer = replace(validation[0], window_id="peer", instrument_key="US:XNAS:OTHER",
                   data_sha256=sha256("peer"))
    return replace(p, windows=(p.windows[0], *validation, peer,
                               replace(p.windows[-1], start=NOW+25*DAY, end=NOW+30*DAY)))


def reservation(p, policy=StabilityPolicy()):
    n = sum(w.split == "validation" for w in p.windows)*(len(p.candidates)+2)*2
    return SearchReservation(sha256("manifest"), p.digest, n, policy)


def arms(p, *, concentrated=False, verified=True):
    for w in p.windows:
        if w.split != "validation":
            continue
        for name in (*BASELINES, "alpha", "beta"):
            for cost in p.costs:
                pnl = None
                if concentrated and name == "alpha":
                    pnl = "120" if w.window_id in ("v0", "peer") else "1"
                a = arm(p, w.window_id, name, cost, pnl=pnl, verified=verified)
                yield replace(a, report_sha256=sha256(("report", w.window_id, name, cost)))


def result_rows(evidence):
    return tuple(SearchArmOutcome(a.window_id, a.candidate_id, a.cost, "RECORDED",
                                  a.report_sha256) for a in evidence)


def test_temporal_blocks_do_not_count_correlated_same_day_symbols_twice():
    p = multi_plan()
    reg = ResearchRegistry(p)
    for a in arms(p):
        reg = reg.record(a)
    result = assess_stability(reg, "alpha", StabilityPolicy())
    assert result.status == "STABLE"
    assert len(result.blocks) == 3 and result.matched_windows == 4
    assert result.blocks[0].window_ids == ("peer", "v0")
    assert result.positive_block_fraction == 1
    assert result.worst_block_excess == D("0.007")
    assert result.worst_leave_one_out_mean == D("0.007")


def test_high_mean_but_one_winning_time_block_does_not_pass():
    p = multi_plan()
    state = ResearchRegistry(p).reserve_search(reservation(p))
    for a in arms(p, concentrated=True):
        state = state.record(a)
    assert state.assess("alpha").status == "RESEARCH_PASS"
    result = assess_stability(state, "alpha", StabilityPolicy())
    assert result.status == "UNSTABLE"
    assert "TOO_FEW_POSITIVE_BLOCKS" in result.reasons
    assert result.worst_leave_one_out_mean == D("-0.001")
    assert "LEAVE_ONE_OUT_EXCESS_TOO_LOW" in result.reasons
    with pytest.raises(ValueError, match="SEARCH_OUTCOME_MATRIX_INCOMPLETE"):
        state.lock_validation()
    state = state.record_search_outcomes(result_rows(state.evidence))
    assert state.lock_validation().locked_candidate == "beta"


def test_unverified_and_incomplete_blocks_never_qualified():
    p = multi_plan()
    state = ResearchRegistry(p)
    for a in arms(p, verified=False):
        state = state.record(a)
    assert assess_stability(state, "alpha", StabilityPolicy()).status == "INCONCLUSIVE"
    missing = replace(state, evidence=state.evidence[:-4])
    result = assess_stability(missing, "alpha", StabilityPolicy())
    assert result.status == "INCONCLUSIVE"
    assert "INCOMPLETE_PAIRED_BLOCKS" in result.reasons
    assert result.positive_block_fraction is None


def test_durable_reservation_cross_plan_and_policy_change(tmp_path):
    p = multi_plan()
    other = replace(p, plan_id="new-name", windows=(
        *p.windows[:-1], replace(p.windows[-1], start=NOW+40*DAY,
                                 end=NOW+45*DAY, data_sha256=sha256("new-final"))))
    path = tmp_path / "search.db"
    with ResearchJournal(path) as j:
        j.register(p)
        first = j.reserve_search(p.plan_id, reservation(p))
        assert j.reserve_search(p.plan_id, reservation(p)) == first
        with pytest.raises(ValueError, match="SEARCH_VALIDATION_ALREADY_RESERVED"):
            j.register(other)
        with pytest.raises(ValueError, match="SEARCH_RESERVATION_ALREADY_FIXED"):
            j.reserve_search(p.plan_id, reservation(p, StabilityPolicy(min_time_blocks=4)))
    with ResearchJournal(path) as j:
        assert j.get(p.plan_id) == first
    # Even if an overlapping plan was registered first, it can't become
    # a new search on the same validation period.
    with ResearchJournal(tmp_path / "prior.db") as j:
        j.register(other)
        j.register(p)
        with pytest.raises(ValueError, match="SEARCH_VALIDATION_ALREADY_RESERVED"):
            j.reserve_search(p.plan_id, reservation(p))
        assert j.get(p.plan_id).search_reservation is None


def test_recorded_and_failed_outcomes_preserved_no_fabricated_report(tmp_path):
    p = multi_plan()
    path = tmp_path / "outcomes.db"
    with ResearchJournal(path) as j:
        j.register(p)
        j.reserve_search(p.plan_id, reservation(p))
        for a in arms(p):
            j.record(p.plan_id, a)
        evidence = j.get(p.plan_id).evidence
        rows = result_rows(evidence)
        failed = (replace(rows[0], status="FAILED", error_type="ValueError",
                          report_sha256=None), *rows[1:])
        first = j.record_search_outcomes(p.plan_id, failed)
        assert len(first.search_history) == 1
        assert assess_stability(first, "alpha", StabilityPolicy()).status == "INCONCLUSIVE"
        assert "LATEST_SEARCH_OUTCOME_FAILED" in assess_stability(
            first, "alpha", StabilityPolicy()).reasons
        with pytest.raises(ValueError, match="SEARCH_OUTCOME_MATRIX_INCOMPLETE"):
            j.lock_validation(p.plan_id)
        with pytest.raises(ValueError, match="SEARCH_OUTCOME_REPORT_MISMATCH"):
            j.record_search_outcomes(p.plan_id, (replace(rows[0], report_sha256="f"*64), *rows[1:]))
        with pytest.raises(ValueError, match="SEARCH_OUTCOME_MATRIX_MISMATCH"):
            j.record_search_outcomes(p.plan_id, rows[:-1])
        final = j.record_search_outcomes(p.plan_id, rows)
        assert len(final.search_history) == 2
        assert j.record_search_outcomes(p.plan_id, tuple(reversed(rows))) == final
    with ResearchJournal(path) as j:
        assert j.get(p.plan_id) == final
        assert j.lock_validation(p.plan_id).locked_candidate == "alpha"


def test_reservation_not_allowed_after_results_seen(tmp_path):
    p = multi_plan()
    with ResearchJournal(tmp_path / "old.db") as j:
        j.register(p)
        j.record(p.plan_id, next(arms(p)))
        with pytest.raises(ValueError, match="SEARCH_RESERVATION_REQUIRES_UNSEEN_PLAN"):
            j.reserve_search(p.plan_id, reservation(p))
