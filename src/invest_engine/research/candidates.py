"""E6 offline experiment preregistration and candidate evaluation.

No strategy execution, model training, broker access, shadow/live promotion,
or claims of certified input provenance. A caller must persist the immutable
registry snapshots externally; this value-level gate is not a security boundary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from invest_engine.domain.primitives import _decimal, utc_datetime
from invest_engine.research.report import sha256

D = Decimal
_SHA = re.compile(r"[0-9a-f]{64}")
_CODE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
BASELINES = ("no-trade", "buy-hold")


def _hash(value: str) -> bool:
    return _SHA.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class ResearchWindow:
    window_id: str
    instrument_key: str
    currency: str
    split: str
    start: datetime
    end: datetime
    data_sha256: str
    context_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", utc_datetime(self.start))
        object.__setattr__(self, "end", utc_datetime(self.end))
        if (not self.window_id.strip() or not self.instrument_key.strip()
                or not re.fullmatch(r"[A-Z]{3}", self.currency)
                or self.split not in ("train", "validation", "test")
                or self.start >= self.end
                or not _hash(self.data_sha256) or not _hash(self.context_sha256)):
            raise ValueError("INVALID_RESEARCH_WINDOW")


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    strategy_version: str
    code_sha: str
    config_sha256: str
    training_cutoff: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "training_cutoff", utc_datetime(self.training_cutoff))
        if (not self.candidate_id.strip() or self.candidate_id in BASELINES
                or not self.strategy_version.strip() or not _CODE.fullmatch(self.code_sha)
                or not _hash(self.config_sha256)):
            raise ValueError("INVALID_CANDIDATE")


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    min_exit_fills: int
    max_drawdown: Decimal
    min_mean_excess: Decimal
    embargo: timedelta

    def __post_init__(self) -> None:
        if (type(self.min_exit_fills) is not int or self.min_exit_fills < 1
                or not D(0) <= _decimal(self.max_drawdown, field="max_drawdown") <= D(1)
                or _decimal(self.min_mean_excess, field="min_mean_excess") < 0
                or self.embargo < timedelta(0)):
            raise ValueError("INVALID_EVALUATION_POLICY")


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    plan_id: str
    registered_at: datetime
    windows: tuple[ResearchWindow, ...]
    candidates: tuple[Candidate, ...]
    costs: tuple[str, ...]
    policy: EvaluationPolicy
    label_horizon: timedelta
    baseline_config_sha256: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "registered_at", utc_datetime(self.registered_at))
        if (not self.plan_id.strip() or not self.candidates
                or not all(isinstance(v, tuple) for v in
                           (self.windows, self.candidates, self.costs))
                or self.label_horizon <= timedelta(0)
                or set(self.costs) != {"base", "stress"} or len(self.costs) != 2
                or not isinstance(self.baseline_config_sha256, tuple)
                or len(self.baseline_config_sha256) != 2
                or set(dict(self.baseline_config_sha256)) != set(BASELINES)
                or not all(_hash(h) for _, h in self.baseline_config_sha256)
                or len({w.window_id for w in self.windows}) != len(self.windows)
                or len({c.candidate_id for c in self.candidates}) != len(self.candidates)):
            raise ValueError("INVALID_RESEARCH_PLAN")
        buckets = {s: tuple(w for w in self.windows if w.split == s)
                   for s in ("train", "validation", "test")}
        if not all(buckets.values()):
            raise ValueError("RESEARCH_REQUIRES_ALL_SPLITS")
        for a, b in (("train", "validation"), ("validation", "test")):
            if (max(w.end for w in buckets[a]) + self.label_horizon + self.policy.embargo
                    > min(w.start for w in buckets[b])):
                raise ValueError("RESEARCH_SPLIT_OVERLAP_OR_PURGE")
        if any(c.training_cutoff > max(w.end for w in buckets["train"])
               for c in self.candidates):
            raise ValueError("CANDIDATE_TRAINING_USES_NONTRAIN_DATA")
        groups: dict[str, list[ResearchWindow]] = {}
        for w in self.windows:
            groups.setdefault(w.instrument_key, []).append(w)
        for group in groups.values():
            ordered = sorted(group, key=lambda w: w.start)
            if any(a.end > b.start for a, b in zip(ordered, ordered[1:])):
                raise ValueError("RESEARCH_DUPLICATE_EXPOSURE_WINDOW")

    @property
    def digest(self) -> str:
        return sha256(self)


@dataclass(frozen=True, slots=True)
class ArmEvidence:
    window_id: str
    candidate_id: str
    cost: str
    data_sha256: str
    context_sha256: str
    run_sha256: str
    candidate_config_sha256: str
    currency: str
    opening_cash: Decimal
    net_pnl: Decimal
    max_drawdown: Decimal
    exit_fills: int
    entry_fills: int
    provenance_verified: bool
    complete: bool
    cost_verified: bool
    execution_validated: bool

    def __post_init__(self) -> None:
        if (not all(_hash(x) for x in (self.data_sha256, self.context_sha256,
                                     self.run_sha256, self.candidate_config_sha256))
                or not self.window_id or not self.candidate_id
                or self.cost not in ("base", "stress")
                or _decimal(self.opening_cash, field="opening_cash") <= 0
                or not D(0) <= _decimal(self.max_drawdown, field="max_drawdown") <= D(1)
                or type(self.exit_fills) is not int or self.exit_fills < 0
                or type(self.entry_fills) is not int or self.entry_fills < 0
                or any(type(x) is not bool for x in (self.provenance_verified, self.complete,
                                                   self.cost_verified, self.execution_validated))):
            raise ValueError("INVALID_ARM_EVIDENCE")
        _decimal(self.net_pnl, field="net_pnl")
        if self.candidate_id == "no-trade" and (
                self.net_pnl or self.max_drawdown or self.exit_fills or self.entry_fills):
            raise ValueError("INVALID_NO_TRADE_BASELINE")

    @property
    def net_return(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 64
            return self.net_pnl / self.opening_cash


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    candidate_id: str
    status: str
    reasons: tuple[str, ...]
    mean_base_excess: Decimal | None
    mean_stress_excess: Decimal | None
    worst_drawdown: Decimal | None
    total_exit_fills: int


@dataclass(frozen=True, slots=True)
class ResearchRegistry:
    """Append-only value snapshots; final test evaluated once per snapshot lineage."""
    plan: ResearchPlan
    evidence: tuple[ArmEvidence, ...] = ()
    locked_candidate: str | None = None
    final_assessment: CandidateAssessment | None = None
    validation_locked: bool = False

    def record(self, arm: ArmEvidence) -> ResearchRegistry:
        windows = {w.window_id: w for w in self.plan.windows}
        if arm.window_id not in windows:
            raise ValueError("UNREGISTERED_WINDOW")
        w = windows[arm.window_id]
        if (arm.data_sha256 != w.data_sha256 or arm.context_sha256 != w.context_sha256
                or arm.currency != w.currency):
            raise ValueError("ARM_CONTEXT_MISMATCH")
        candidates = {c.candidate_id for c in self.plan.candidates}
        if arm.candidate_id not in candidates | set(BASELINES):
            raise ValueError("UNREGISTERED_CANDIDATE")
        hashes = {**dict(self.plan.baseline_config_sha256),
                  **{c.candidate_id: c.config_sha256 for c in self.plan.candidates}}
        if arm.candidate_config_sha256 != hashes[arm.candidate_id]:
            raise ValueError("ARM_CANDIDATE_CONFIG_MISMATCH")
        if self.final_assessment is not None:
            raise ValueError("HOLDOUT_ALREADY_FINALIZED")
        if w.split == "test":
            if (self.locked_candidate is None
                    or arm.candidate_id not in set(BASELINES) | {self.locked_candidate}):
                raise ValueError("TEST_REQUIRES_LOCKED_CANDIDATE")
        elif self.validation_locked:
            raise ValueError("DEVELOPMENT_EVIDENCE_LOCKED")
        for previous in self.evidence:
            if previous.run_sha256 == arm.run_sha256 and previous != arm:
                raise ValueError("RUN_IDENTITY_REUSED")
            if (previous.window_id, previous.candidate_id, previous.cost) == (
                    arm.window_id, arm.candidate_id, arm.cost):
                if previous == arm:
                    return self
                raise ValueError("ARM_ALREADY_RECORDED")
            if previous.window_id == arm.window_id and previous.opening_cash != arm.opening_cash:
                raise ValueError("ARM_CAPITAL_MISMATCH")
        return replace(self, evidence=(*self.evidence, arm))

    def assess(self, candidate_id: str, split: str = "validation") -> CandidateAssessment:
        if candidate_id not in {c.candidate_id for c in self.plan.candidates}:
            raise ValueError("UNREGISTERED_CANDIDATE")
        if split not in ("validation", "test"):
            raise ValueError("INVALID_ASSESSMENT_SPLIT")
        if split == "test" and self.locked_candidate != candidate_id:
            raise ValueError("TEST_REQUIRES_LOCKED_CANDIDATE")
        reasons: set[str] = set()
        scores: dict[str, list[Decimal]] = {c: [] for c in self.plan.costs}
        mdds: list[Decimal] = []
        exits = 0
        by_key = {(a.window_id, a.candidate_id, a.cost): a for a in self.evidence}
        for w in (w for w in self.plan.windows if w.split == split):
            for cost in self.plan.costs:
                keys = [(w.window_id, c, cost) for c in (candidate_id, *BASELINES)]
                if any(k not in by_key for k in keys):
                    reasons.add("MISSING_MATCHED_ARM")
                    continue
                candidate, cash, hold = (by_key[k] for k in keys)
                if not all(a.complete for a in (candidate, cash, hold)):
                    reasons.add("INCOMPLETE_EVIDENCE")
                if not all(a.provenance_verified and a.cost_verified and a.execution_validated
                           for a in (candidate, cash, hold)):
                    reasons.add("UNVERIFIED_EVIDENCE")
                if hold.entry_fills == 0:
                    reasons.add("HOLD_BASELINE_NO_ENTRY")
                if candidate.entry_fills == 0 or candidate.exit_fills < self.plan.policy.min_exit_fills:
                    reasons.add("INSUFFICIENT_EXIT_FILLS")
                if candidate.max_drawdown > self.plan.policy.max_drawdown:
                    reasons.add("DRAWDOWN_LIMIT")
                excess = candidate.net_return - max(cash.net_return, hold.net_return)
                scores[cost].append(excess)
                mdds.append(candidate.max_drawdown)
                exits += candidate.exit_fills
        means: dict[str, Decimal | None] = {
            c: sum(values, D(0))/len(values) if values else None
            for c, values in scores.items()}
        if any(x is None or x < self.plan.policy.min_mean_excess for x in means.values()):
            reasons.add("BASELINE_EXCESS_TOO_LOW")
        inconclusive = {"MISSING_MATCHED_ARM", "INCOMPLETE_EVIDENCE",
                        "UNVERIFIED_EVIDENCE", "HOLD_BASELINE_NO_ENTRY",
                        "INSUFFICIENT_EXIT_FILLS"}
        status = ("INCONCLUSIVE" if reasons & inconclusive else
                  "REJECTED" if reasons else "RESEARCH_PASS")
        return CandidateAssessment(candidate_id, status, tuple(sorted(reasons)),
                                   means["base"], means["stress"],
                                   max(mdds) if mdds else None, exits)

    def lock_validation(self) -> ResearchRegistry:
        """Select using validation only; no test outcomes have been observed here."""
        if self.validation_locked:
            raise ValueError("VALIDATION_ALREADY_LOCKED")
        assessments = tuple(self.assess(c.candidate_id) for c in self.plan.candidates)
        if any("MISSING_MATCHED_ARM" in a.reasons for a in assessments):
            raise ValueError("VALIDATION_MATRIX_INCOMPLETE")
        passed = [a for a in assessments if a.status == "RESEARCH_PASS"]
        if not passed:
            return replace(self, validation_locked=True)
        def rank(a: CandidateAssessment) -> tuple[Decimal, str]:
            assert a.mean_base_excess is not None and a.mean_stress_excess is not None
            return -min(a.mean_base_excess, a.mean_stress_excess), a.candidate_id
        selected = sorted(passed, key=rank)[0]
        return replace(self, locked_candidate=selected.candidate_id, validation_locked=True)

    def finalize_test(self) -> ResearchRegistry:
        if self.final_assessment is not None:
            raise ValueError("HOLDOUT_ALREADY_FINALIZED")
        if self.locked_candidate is None:
            raise ValueError("NO_LOCKED_CANDIDATE")
        assessment = self.assess(self.locked_candidate, "test")
        if "MISSING_MATCHED_ARM" in assessment.reasons:
            raise ValueError("TEST_MATRIX_INCOMPLETE")
        return replace(self, final_assessment=assessment)
