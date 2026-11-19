"""E6.5a bounded, exhaustive rule-parameter search, offline only.

The grid and budget are fixed before validation. No holdout observations,
adaptive retries, fitted models, parameter feedback, or deployment rights.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import product
from math import prod

from invest_engine.domain.primitives import _decimal
from invest_engine.research.candidates import BASELINES, CandidateAssessment
from invest_engine.research.fold_execution import (
    FixedRule, FoldInput, FoldScenario, FoldStudyResult, PreparedFold,
    execute_validation, prepare_validation,
)
from invest_engine.research.regime import RegimePolicy
from invest_engine.research.report import sha256
from invest_engine.research.research_journal import ResearchJournal
from invest_engine.research.walk_forward import SampleTiming, WalkForwardPlan
from invest_engine.strategies.orb import ORBParameters

D = Decimal


@dataclass(frozen=True, slots=True)
class SearchGrid:
    search_id: str
    opening_us_minutes: tuple[int, ...]
    opening_kr_minutes: tuple[int, ...]
    prior_sessions: tuple[int, ...]
    atr_periods: tuple[int, ...]
    volume_multipliers: tuple[Decimal, ...]
    candidate_budget: int
    replay_arm_budget: int

    def __post_init__(self) -> None:
        if (not self.search_id.strip() or type(self.candidate_budget) is not int
                or not 1 <= self.candidate_budget <= 64
                or type(self.replay_arm_budget) is not int
                or not 1 <= self.replay_arm_budget <= 4096):
            raise ValueError("INVALID_SEARCH_BUDGET_OR_ID")
        for name, low, high in (
            ("opening_us_minutes", 1, 60), ("opening_kr_minutes", 1, 60),
            ("prior_sessions", 1, 20), ("atr_periods", 2, 100),
        ):
            values = getattr(self, name)
            if (not isinstance(values, tuple) or not values
                    or any(type(v) is not int or not low <= v <= high for v in values)
                    or len(set(values)) != len(values)):
                raise ValueError("INVALID_SEARCH_AXIS")
            object.__setattr__(self, name, tuple(sorted(values)))
        values = self.volume_multipliers
        if (not isinstance(values, tuple) or not values
                or any(not D("0.25") <= _decimal(v, field="volume_multiplier") <= D("10")
                       or v != v.quantize(D("0.0001")) for v in values)
                or len(set(values)) != len(values)):
            raise ValueError("INVALID_SEARCH_VOLUME_AXIS")
        object.__setattr__(self, "volume_multipliers",
                           tuple(sorted(v.quantize(D("0.0001")) for v in values)))
        if self.candidate_count > self.candidate_budget:
            raise ValueError("SEARCH_CANDIDATE_BUDGET_EXCEEDED")

    @property
    def candidate_count(self) -> int:
        return prod(len(axis) for axis in (
            self.opening_us_minutes, self.opening_kr_minutes, self.prior_sessions,
            self.atr_periods, self.volume_multipliers))

    @property
    def digest(self) -> str:
        return sha256(self)


@dataclass(frozen=True, slots=True)
class SearchManifest:
    grid: SearchGrid
    walk_forward_sha256: str
    scenario_sha256: str
    regime_policy_sha256: str | None
    include_exposure: bool
    rules: tuple[FixedRule, ...]
    planned_arms: int

    @property
    def digest(self) -> str:
        return sha256(self)


@dataclass(frozen=True, slots=True)
class PreparedSearch:
    manifest: SearchManifest
    folds: tuple[PreparedFold, ...]


def build_search_manifest(
    grid: SearchGrid, walk_forward: WalkForwardPlan, scenario: FoldScenario, *,
    regime_policy: RegimePolicy | None = None, include_exposure: bool = False,
) -> SearchManifest:
    if not walk_forward.eligible:
        raise ValueError("SEARCH_REQUIRES_ELIGIBLE_WALK_FORWARD")
    markets = {key.split(":", 1)[0] for key in walk_forward.spec.instruments}
    if not markets <= {"US", "KR"}:
        raise ValueError("SEARCH_UNSUPPORTED_MARKET")
    if (("KR" not in markets and len(grid.opening_kr_minutes) != 1)
            or ("US" not in markets and len(grid.opening_us_minutes) != 1)):
        raise ValueError("SEARCH_INACTIVE_MARKET_AXIS")
    if type(include_exposure) is not bool or include_exposure and regime_policy is None:
        raise ValueError("SEARCH_EXPOSURE_REQUIRES_REGIME")
    planned = (grid.candidate_count+len(BASELINES))*2*len(walk_forward.folds)*len(
        walk_forward.spec.instruments)
    if planned > grid.replay_arm_budget:
        raise ValueError("SEARCH_REPLAY_BUDGET_EXCEEDED")
    rules: list[FixedRule] = []
    for us, kr, prior, atr, volume in product(
            grid.opening_us_minutes, grid.opening_kr_minutes, grid.prior_sessions,
            grid.atr_periods, grid.volume_multipliers):
        params = ORBParameters(opening_us=timedelta(minutes=us),
                               opening_kr=timedelta(minutes=kr),
                               prior_sessions=prior, atr_period=atr,
                               volume_multiplier=volume, target_fraction=scenario.target)
        rules.append(FixedRule("orb-"+sha256(params), params))
    return SearchManifest(grid, walk_forward.digest, sha256(scenario),
                          regime_policy.digest if regime_policy else None,
                          include_exposure, tuple(sorted(rules, key=lambda r: r.candidate_id)),
                          planned)


def prepare_search(
    grid: SearchGrid, walk_forward: WalkForwardPlan, timing: tuple[SampleTiming, ...],
    cases: tuple[FoldInput, ...], scenario: FoldScenario, *,
    regime_policy: RegimePolicy | None = None, include_exposure: bool = False,
) -> PreparedSearch:
    manifest = build_search_manifest(grid, walk_forward, scenario,
                                     regime_policy=regime_policy, include_exposure=include_exposure)
    folds = prepare_validation(walk_forward, timing, cases, manifest.rules, scenario,
                               regime_policy=regime_policy, include_exposure=include_exposure,
                               search_identity=manifest.digest)
    return PreparedSearch(manifest, folds)


@dataclass(frozen=True, slots=True)
class CandidateSearchResult:
    manifest_sha256: str
    planned_arms: int
    study: FoldStudyResult
    assessments: tuple[CandidateAssessment, ...]
    # The research registry, not this function, may later lock a verified candidate.
    selection_performed: bool = False


def execute_search(
    journal: ResearchJournal, research_plan_id: str, prepared: PreparedSearch,
    walk_forward: WalkForwardPlan, timing: tuple[SampleTiming, ...], cases: tuple[FoldInput, ...],
    scenario: FoldScenario, *, regime_policy: RegimePolicy | None = None,
    include_exposure: bool = False,
) -> CandidateSearchResult:
    """Run the entire frozen validation grid; retain failures and all assessments.

    The caller must have registered the matching ResearchPlan before execution.
    There is no automatic best candidate, holdout access or iterative tuning.
    The budgets count distinct planned arms, not retries or CPU seconds.
    """
    current = prepare_search(prepared.manifest.grid, walk_forward, timing, cases, scenario,
                             regime_policy=regime_policy, include_exposure=include_exposure)
    if current != prepared:
        raise ValueError("SEARCH_PREREGISTRATION_MISMATCH")
    study = execute_validation(journal, research_plan_id, walk_forward, timing, cases,
                               current.manifest.rules, scenario, regime_policy=regime_policy,
                               include_exposure=include_exposure, search_identity=current.manifest.digest)
    if len(study.runs) != current.manifest.planned_arms:
        raise ValueError("SEARCH_ARM_COUNT_MISMATCH")
    registry = journal.get(research_plan_id)
    assessments = tuple(registry.assess(rule.candidate_id) for rule in current.manifest.rules)
    return CandidateSearchResult(current.manifest.digest, current.manifest.planned_arms,
                                 study, assessments)
