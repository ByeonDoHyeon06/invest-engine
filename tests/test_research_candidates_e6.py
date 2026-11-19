"""Pure offline E6 candidate lifecycle; synthetic evidence, not strategy results."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.research.candidates import (
    ArmEvidence, Candidate, EvaluationPolicy, ResearchPlan, ResearchRegistry, ResearchWindow,
)
from invest_engine.research.report import sha256

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
H = "a"*64
CTX = "b"*64
BASE = (("no-trade", "c"*64), ("buy-hold", "d"*64))


def plan():
    windows = tuple(ResearchWindow(split, "US:XNAS:FIX", "USD", split,
                    NOW + i*10*DAY, NOW + (i*10+5)*DAY, H, CTX)
                    for i, split in enumerate(("train", "validation", "test")))
    candidates = tuple(Candidate(c, "v1", "e"*40, sha256(c), NOW+5*DAY)
                       for c in ("alpha", "beta"))
    return ResearchPlan("fixture", NOW-DAY, windows, candidates, ("base", "stress"),
                        EvaluationPolicy(2, D("0.05"), D("0.001"), DAY), DAY, BASE)


def arm(p, split, name, cost, *, pnl=None, verified=True, entries=None, exits=None):
    config = {**dict(p.baseline_config_sha256),
              **{c.candidate_id: c.config_sha256 for c in p.candidates}}[name]
    amount = {"no-trade": "0", "buy-hold": "2", "alpha": "9", "beta": "5"}[name]
    return ArmEvidence(split, name, cost, H, CTX, sha256((split, name, cost)),
                       config, "USD", D("1000"), D(amount if pnl is None else pnl),
                       D("0") if name == "no-trade" else D("0.01"),
                       0 if name in ("no-trade", "buy-hold") else (2 if exits is None else exits),
                       (0 if name == "no-trade" else 2) if entries is None else entries,
                       verified, True, verified, verified)


def matrix(reg, split, names, **kwargs):
    for name in names:
        for cost in reg.plan.costs:
            reg = reg.record(arm(reg.plan, split, name, cost, **kwargs))
    return reg


def test_temporal_gap_and_training_cutoff_are_enforced():
    p = plan()
    w = replace(p.windows[1], start=NOW+6*DAY)
    with pytest.raises(ValueError, match="SPLIT_OVERLAP_OR_PURGE"):
        replace(p, windows=(p.windows[0], w, p.windows[2]))
    with pytest.raises(ValueError, match="TRAINING_USES_NONTRAIN"):
        replace(p, candidates=(replace(p.candidates[0], training_cutoff=NOW+11*DAY),))
    assert p.digest == plan().digest
    assert p.digest != replace(p, label_horizon=2*DAY).digest


def test_validation_selection_and_one_selected_holdout():
    p = plan()
    reg = ResearchRegistry(p)
    with pytest.raises(ValueError, match="TEST_REQUIRES_LOCKED"):
        reg.record(arm(p, "test", "alpha", "base"))
    with pytest.raises(ValueError, match="VALIDATION_MATRIX_INCOMPLETE"):
        reg.lock_validation()
    ready = matrix(reg, "validation", ("no-trade", "buy-hold", "alpha", "beta"))
    assert reg.evidence == ()
    assert ready.assess("alpha").status == "RESEARCH_PASS"
    locked = ready.lock_validation()
    assert locked.locked_candidate == "alpha" and locked.validation_locked
    with pytest.raises(ValueError, match="TEST_REQUIRES_LOCKED"):
        locked.record(arm(p, "test", "beta", "base"))
    with pytest.raises(ValueError, match="DEVELOPMENT_EVIDENCE_LOCKED"):
        locked.record(arm(p, "train", "alpha", "base"))
    with pytest.raises(ValueError, match="TEST_MATRIX_INCOMPLETE"):
        locked.finalize_test()
    final = matrix(locked, "test", ("no-trade", "buy-hold", "alpha")).finalize_test()
    assert final.final_assessment.status == "RESEARCH_PASS"
    with pytest.raises(ValueError, match="HOLDOUT_ALREADY_FINALIZED"):
        final.finalize_test()


def test_provisional_source_cannot_pass_even_with_positive_pnl():
    p = plan()
    reg = matrix(ResearchRegistry(p), "validation", ("no-trade", "buy-hold",
                                                    "alpha", "beta"), verified=False)
    result = reg.assess("alpha")
    assert result.status == "INCONCLUSIVE"
    assert "UNVERIFIED_EVIDENCE" in result.reasons
    assert reg.lock_validation().locked_candidate is None


def test_non_executable_hold_and_insufficient_trades_are_inconclusive():
    p = plan()
    reg = matrix(ResearchRegistry(p), "validation", ("no-trade",))
    reg = matrix(reg, "validation", ("buy-hold",), entries=0)
    reg = matrix(reg, "validation", ("alpha",), exits=1)
    a = reg.assess("alpha")
    assert a.status == "INCONCLUSIVE"
    assert {"HOLD_BASELINE_NO_ENTRY", "INSUFFICIENT_EXIT_FILLS"} <= set(a.reasons)


def test_negative_stress_is_rejected_despite_positive_base():
    p = plan()
    reg = matrix(ResearchRegistry(p), "validation", ("no-trade", "buy-hold"))
    reg = reg.record(arm(p, "validation", "alpha", "base"))
    reg = reg.record(arm(p, "validation", "alpha", "stress", pnl="-1"))
    a = reg.assess("alpha")
    assert a.status == "REJECTED"
    assert "BASELINE_EXCESS_TOO_LOW" in a.reasons


def test_evidence_identity_duplicate_and_capital_are_fail_closed():
    p = plan()
    a = arm(p, "validation", "alpha", "base")
    reg = ResearchRegistry(p)
    with pytest.raises(ValueError, match="ARM_CONTEXT_MISMATCH"):
        reg.record(replace(a, data_sha256="f"*64))
    with pytest.raises(ValueError, match="ARM_CANDIDATE_CONFIG_MISMATCH"):
        reg.record(replace(a, candidate_config_sha256="f"*64))
    reg = reg.record(a)
    assert reg.record(a) is reg
    with pytest.raises(ValueError, match="RUN_IDENTITY_REUSED"):
        reg.record(replace(a, net_pnl=D("100")))
    with pytest.raises(ValueError, match="ARM_ALREADY_RECORDED"):
        reg.record(replace(a, run_sha256="f"*64))
    with pytest.raises(ValueError, match="ARM_CAPITAL_MISMATCH"):
        reg.record(replace(arm(p, "validation", "buy-hold", "base"),
                           opening_cash=D("100")))
