"""E6.3 synthetic timestamp-only tests; not financial evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from invest_engine.research.candidates import ResearchRegistry
from invest_engine.research.walk_forward import (
    SampleTiming, WalkForwardSpec, plan_walk_forward, prepare_holdout,
)
from test_research_candidates_e6 import matrix, plan

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
HOUR = timedelta(hours=1)
INST = "US:XNAS:FIX"


def sample(day, key=INST, *, hours=0, label_hours=1, delay_hours=0, identity=None):
    decision = NOW+day*DAY+hours*HOUR
    return SampleTiming(identity or f"{key}:{day}:{hours}", key, decision,
                        decision-HOUR, decision, decision+label_hours*HOUR,
                        decision+(label_hours+delay_hours)*HOUR)


def spec(**kwargs):
    base = WalkForwardSpec(NOW, NOW+15*DAY, NOW+20*DAY, NOW+25*DAY,
                           4*DAY, 3*DAY, 3*DAY, DAY, (INST,), 2, 2)
    return replace(base, **kwargs)


def test_expanding_folds_have_disjoint_validation_and_historical_training():
    s = spec()
    data = tuple(sample(i) for i in range(15))
    p = plan_walk_forward(s, data)
    assert p.eligible and len(p.folds) == 3
    first, second, third = p.folds
    assert first.train_start == second.train_start == NOW
    assert first.validation_start == NOW+5*DAY
    assert len(first.train_ids) == 4 and len(first.validation_ids) == 3
    assert first.embargo_ids == (sample(4).sample_id,)
    assert first.validation_end == second.validation_start
    assert set(first.validation_ids).isdisjoint(second.validation_ids)
    assert sample(5).sample_id in second.train_ids
    assert third.validation_end == NOW+14*DAY
    assert sample(14).sample_id in p.development_ids
    assert p.digest == plan_walk_forward(s, tuple(reversed(data))).digest


def test_rolling_fit_purges_overlap_and_delayed_labels_without_shifting_boundaries():
    original = tuple(sample(i) for i in range(15))
    data = tuple(sample(3, label_hours=24) if i==3 else
                 sample(7, delay_hours=48) if i==7 else original[i]
                 for i in range(15))
    p = plan_walk_forward(spec(expanding=False), data)
    first, second, _ = p.folds
    assert sample(3).sample_id in first.purged_train_ids
    assert sample(7).sample_id in first.purged_validation_ids
    assert first.validation_start == NOW+5*DAY
    assert second.train_start == NOW+3*DAY
    assert sample(0).sample_id not in second.train_ids
    assert p.eligible


def test_per_symbol_minima_block_sparse_fold_not_move_it():
    s = spec(instruments=(INST, "OTHER"))
    p = plan_walk_forward(s, tuple(sample(i) for i in range(15)))
    assert not p.eligible
    assert "INSUFFICIENT_TRAIN:OTHER" in p.folds[0].blockers
    assert "INSUFFICIENT_VALIDATION:OTHER" in p.folds[0].blockers
    assert len(p.folds) == 3


def test_reject_lookahead_duplicates_foreign_samples_and_overlap():
    a = sample(0)
    with pytest.raises(ValueError, match="LOOKAHEAD"):
        replace(a, feature_available_at=a.decision_at+HOUR)
    with pytest.raises(ValueError, match="LOOKAHEAD"):
        replace(a, label_available_at=a.label_start)
    with pytest.raises(ValueError, match="DUPLICATE"):
        plan_walk_forward(spec(), (a, replace(a, sample_id="duplicate")))
    with pytest.raises(ValueError, match="UNREGISTERED"):
        plan_walk_forward(spec(), (sample(1, "OTHER"),))
    with pytest.raises(ValueError, match="OUTSIDE"):
        plan_walk_forward(spec(), (sample(20),))
    with pytest.raises(ValueError, match="INVALID_WALK_FORWARD"):
        spec(step=DAY)
    with pytest.raises(ValueError, match="INVALID_WALK_FORWARD"):
        spec(holdout_start=NOW+15*DAY, embargo=DAY)


def test_holdout_requires_registry_selection_and_exact_declared_final_span():
    data = tuple(sample(i) for i in range(15))
    wf = plan_walk_forward(spec(), data)
    reg = ResearchRegistry(plan())
    with pytest.raises(ValueError, match="LOCKED_CANDIDATE"):
        prepare_holdout(wf, reg, ())
    locked = matrix(reg, "validation", ("no-trade", "buy-hold", "alpha", "beta")).lock_validation()
    # Fixture registry final bounds are Jan 21--26, matching spec.
    held = tuple(sample(i) for i in range(20, 25))
    partition = prepare_holdout(wf, locked, held)
    assert partition.candidate_id == "alpha"
    assert partition.sample_ids == tuple(s.sample_id for s in held)
    assert not partition.blockers
    assert partition.plan_sha256 == wf.digest
    with pytest.raises(ValueError, match="WINDOW_MISMATCH"):
        prepare_holdout(plan_walk_forward(spec(holdout_end=NOW+26*DAY), data), locked, held)
    with pytest.raises(ValueError, match="REUSES_DEVELOPMENT"):
        prepare_holdout(wf, locked, (replace(held[0], sample_id=sample(14).sample_id), *held[1:]))
    with pytest.raises(ValueError, match="LOCKED_CANDIDATE"):
        prepare_holdout(wf, matrix(locked, "test", ("no-trade", "buy-hold", "alpha")).finalize_test(), held)


def test_final_late_label_purge_and_minimum_support():
    wf = plan_walk_forward(spec(), tuple(sample(i) for i in range(15)))
    reg = matrix(ResearchRegistry(plan()), "validation",
                 ("no-trade", "buy-hold", "alpha", "beta")).lock_validation()
    late = sample(24, label_hours=25)
    held = prepare_holdout(wf, reg, (sample(20), late))
    assert held.purged_ids == (late.sample_id,)
    assert held.blockers == (f"INSUFFICIENT_HOLDOUT:{INST}",)
