"""E6.6a: unified, deterministic offline development research workflow.

The caller supplies development-only timings and strict E5 replay windows,
plus immutable metadata claims for initial training and reserved final
holdout. No holdout prices/labels, external data access, model fit, broker
calls, approval, automated deployment or strategy mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from invest_engine.domain.primitives import utc_datetime
from invest_engine.research.candidates import (
    CandidateAssessment, EvaluationPolicy, ResearchPlan, ResearchWindow,
    SearchArmOutcome, SearchReservation, StabilityPolicy,
)
from invest_engine.research.fold_execution import FoldInput, FoldScenario, fixed_candidates
from invest_engine.research.parameter_search import (
    DEFAULT_STABILITY, CandidateSearchResult, PreparedSearch, SearchGrid, execute_search, prepare_search,
)
from invest_engine.research.regime import RegimePolicy
from invest_engine.research.report import canonical_json, sha256
from invest_engine.research.research_journal import ResearchJournal
from invest_engine.research.robustness import StabilityAssessment, assess_stability
from invest_engine.research.walk_forward import SampleTiming, WalkForwardPlan, WalkForwardSpec, plan_walk_forward


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    plan_id: str
    registered_at: datetime
    walk_forward: WalkForwardSpec
    grid: SearchGrid
    evaluation_policy: EvaluationPolicy
    label_horizon: timedelta
    initial_windows: tuple[ResearchWindow, ...]
    final_windows: tuple[ResearchWindow, ...]
    stability_policy: StabilityPolicy = DEFAULT_STABILITY
    regime_policy: RegimePolicy | None = None
    include_exposure: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "registered_at", utc_datetime(self.registered_at))
        wf = self.walk_forward
        if (not self.plan_id.strip() or self.evaluation_policy.embargo != wf.embargo
                or self.label_horizon <= timedelta(0)
                or type(self.include_exposure) is not bool
                or (self.include_exposure and self.regime_policy is None)):
            raise ValueError("PIPELINE_INVALID_POLICY")
        for windows, split in ((self.initial_windows, "train"), (self.final_windows, "test")):
            if (not isinstance(windows, tuple) or len(windows) != len(wf.instruments)
                    or {w.instrument_key for w in windows} != set(wf.instruments)
                    or any(w.split != split for w in windows)):
                raise ValueError("PIPELINE_PARTITION_UNIVERSE_MISMATCH")
        first_fit_end = wf.development_start+wf.train_span
        if any(not wf.development_start <= w.start < w.end <= first_fit_end
               for w in self.initial_windows):
            raise ValueError("PIPELINE_INITIAL_TRAIN_RANGE")
        if any((w.start, w.end) != (wf.holdout_start, wf.holdout_end) for w in self.final_windows):
            raise ValueError("PIPELINE_HOLDOUT_METADATA_RANGE")
        initial = {w.instrument_key: w.currency for w in self.initial_windows}
        if any(initial[w.instrument_key] != w.currency for w in self.final_windows):
            raise ValueError("PIPELINE_INSTRUMENT_CURRENCY_MISMATCH")


@dataclass(frozen=True, slots=True)
class PreparedPipeline:
    spec: PipelineSpec
    walk_forward: WalkForwardPlan
    search: PreparedSearch
    plan: ResearchPlan

    @property
    def reservation(self) -> SearchReservation:
        return SearchReservation(self.search.manifest.digest, self.plan.digest,
                                 self.search.manifest.planned_arms, self.spec.stability_policy)

    @property
    def digest(self) -> str:
        return sha256(("offline-pipeline-v1", self.spec, self.walk_forward.digest,
                       self.search, self.plan.digest, self.reservation))


def prepare_pipeline(spec: PipelineSpec, timing: tuple[SampleTiming, ...],
                     cases: tuple[FoldInput, ...], scenario: FoldScenario) -> PreparedPipeline:
    """Deterministically compile a full plan; never execute market arms."""
    walk_forward = plan_walk_forward(spec.walk_forward, timing)
    search = prepare_search(spec.grid, walk_forward, timing, cases, scenario,
                            regime_policy=spec.regime_policy, include_exposure=spec.include_exposure)
    initial = {w.instrument_key: w.currency for w in spec.initial_windows}
    if any(initial[f.window.instrument_key] != f.window.currency for f in search.folds):
        raise ValueError("PIPELINE_INSTRUMENT_CURRENCY_MISMATCH")
    plan = ResearchPlan(
        spec.plan_id, spec.registered_at,
        tuple(sorted((*spec.initial_windows, *(f.window for f in search.folds), *spec.final_windows),
                     key=lambda w: w.window_id)),
        fixed_candidates(search.manifest.rules, scenario, walk_forward),
        ("base", "stress"), spec.evaluation_policy, spec.label_horizon, scenario.baseline_configs,
    )
    return PreparedPipeline(spec, walk_forward, search, plan)


@dataclass(frozen=True, slots=True)
class CandidateReview:
    economic: CandidateAssessment
    stability: StabilityAssessment


@dataclass(frozen=True, slots=True)
class PipelineReview:
    pipeline_sha256: str
    plan_sha256: str
    search_sha256: str
    phase: str
    planned_arms: int
    recorded_arms: int
    failed_latest_arms: int
    unverified_arms: int
    incomplete_arms: int
    distinct_outcome_matrices: int
    outcome_history_sha256: str
    latest_outcomes: tuple[SearchArmOutcome, ...]
    candidates: tuple[CandidateReview, ...]
    locked_candidate: str | None
    blockers: tuple[str, ...]
    # This development workflow never authorizes release or broker operations.
    production_authorized: bool = False

    @property
    def digest(self) -> str:
        return sha256(self)

    def to_json(self) -> bytes:
        return canonical_json(self)


def review_pipeline(journal: ResearchJournal, prepared: PreparedPipeline) -> PipelineReview:
    """Rebuild a development-only report from the authoritative local journal.

    No report or market event data is required to review or recover this state.
    Detailed regime studies are caller-retained; the journal stores arm metrics
    and report hashes, not the full original report artifacts.
    """
    registry = journal.get(prepared.plan.plan_id)
    if registry.plan != prepared.plan:
        raise ValueError("PIPELINE_JOURNAL_PLAN_MISMATCH")
    reserved = registry.search_reservation
    if reserved != prepared.reservation:
        raise ValueError("PIPELINE_JOURNAL_RESERVATION_MISMATCH")
    ids = {w.window_id for w in registry.plan.windows if w.split == "validation"}
    evidence = tuple(a for a in registry.evidence if a.window_id in ids)
    latest = registry.search_history[-1] if registry.search_history else ()
    failures = sum(a.status == "FAILED" for a in latest)
    unverified = sum(not (a.provenance_verified and a.cost_verified and a.execution_validated)
                     for a in evidence)
    incomplete = sum(not a.complete for a in evidence)
    planned = reserved.planned_arms
    candidates = tuple(CandidateReview(registry.assess(c.candidate_id),
                                       assess_stability(registry, c.candidate_id, reserved.stability))
                       for c in registry.plan.candidates)
    eligible = tuple(c for c in candidates if c.economic.status == "RESEARCH_PASS"
                     and c.stability.status == "STABLE")
    blockers = tuple(code for condition, code in (
        (len(evidence) != planned or len(latest) != planned, "INCOMPLETE_VALIDATION_MATRIX"),
        (failures > 0, "LATEST_SEARCH_FAILED_ARMS"),
        (unverified > 0, "UNVERIFIED_VALIDATION_EVIDENCE"),
        (incomplete > 0, "INCOMPLETE_VALIDATION_EVIDENCE"),
        (not eligible, "NO_ELIGIBLE_RESEARCH_CANDIDATE"),
    ) if condition)
    if registry.validation_locked:
        phase = "CANDIDATE_LOCKED_OFFLINE" if registry.locked_candidate else "VALIDATION_CLOSED_NO_CANDIDATE"
    elif len(evidence) != planned or len(latest) != planned or failures:
        phase = "RETRY_REQUIRED"
    elif not eligible:
        phase = "NO_ELIGIBLE_CANDIDATE"
    else:
        phase = "READY_FOR_EXPLICIT_VALIDATION_LOCK"
    return PipelineReview(prepared.digest, registry.plan.digest, reserved.manifest_sha256,
                          phase, planned, len(evidence), failures, unverified, incomplete,
                          len(registry.search_history), sha256(registry.search_history), latest,
                          candidates, registry.locked_candidate, blockers)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    search: CandidateSearchResult
    review: PipelineReview


def run_development(journal: ResearchJournal, prepared: PreparedPipeline,
                    timing: tuple[SampleTiming, ...], cases: tuple[FoldInput, ...],
                    scenario: FoldScenario) -> PipelineResult:
    """Compile/check, register, reserve, replay, persist, then summarize.

    There is no implicit lock: the caller must explicitly close validation
    when satisfied with the research review. Exact retries are idempotent.
    """
    current = prepare_pipeline(prepared.spec, timing, cases, scenario)
    if current != prepared:
        raise ValueError("PIPELINE_PREREGISTRATION_MISMATCH")
    registry = journal.register(current.plan)
    if registry.validation_locked:
        raise ValueError("PIPELINE_VALIDATION_ALREADY_CLOSED")
    spec = current.spec
    search = execute_search(journal, current.plan.plan_id, current.search,
                            current.walk_forward, timing, cases, scenario,
                            regime_policy=spec.regime_policy, include_exposure=spec.include_exposure,
                            stability_policy=spec.stability_policy)
    return PipelineResult(search, review_pipeline(journal, current))


def close_validation(journal: ResearchJournal, prepared: PreparedPipeline) -> PipelineReview:
    """Irreversible local close of a complete matrix; never run holdout.

    Closing a provisional or unsuccessful experiment selects nobody. This
    is explicit so a caller can retain an open failed experiment for retry.
    Independent attestations and separately authorized release are absent.
    """
    prior = review_pipeline(journal, prepared)
    if prior.phase in ("VALIDATION_CLOSED_NO_CANDIDATE", "CANDIDATE_LOCKED_OFFLINE"):
        return prior
    if prior.phase == "RETRY_REQUIRED":
        raise ValueError("PIPELINE_CANNOT_CLOSE_INCOMPLETE_MATRIX")
    journal.lock_validation(prepared.plan.plan_id)
    return review_pipeline(journal, prepared)
