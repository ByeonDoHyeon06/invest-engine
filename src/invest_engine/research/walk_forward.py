"""E6.3 deterministic temporal walk-forward planning (offline only).

This module consumes timing metadata, never labels/features/market prices.
It does not train, fit, rank or deploy strategies, and cannot isolate files
that callers can access outside the API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from invest_engine.domain.primitives import utc_datetime
from invest_engine.research.candidates import ResearchRegistry
from invest_engine.research.report import sha256


@dataclass(frozen=True, slots=True)
class SampleTiming:
    sample_id: str
    instrument_key: str
    decision_at: datetime
    feature_available_at: datetime
    label_start: datetime
    label_end: datetime
    label_available_at: datetime

    def __post_init__(self) -> None:
        for field in ("decision_at", "feature_available_at", "label_start",
                      "label_end", "label_available_at"):
            object.__setattr__(self, field, utc_datetime(getattr(self, field)))
        if (not self.sample_id.strip() or not self.instrument_key.strip()
                or self.feature_available_at > self.decision_at
                or self.label_start < self.decision_at
                or self.label_end <= self.label_start
                or self.label_available_at < self.label_end):
            raise ValueError("INVALID_SAMPLE_TIMING_OR_LOOKAHEAD")


@dataclass(frozen=True, slots=True)
class WalkForwardSpec:
    development_start: datetime
    development_end: datetime
    holdout_start: datetime
    holdout_end: datetime
    train_span: timedelta
    validation_span: timedelta
    step: timedelta
    embargo: timedelta
    instruments: tuple[str, ...]
    min_train_per_instrument: int
    min_validation_per_instrument: int
    expanding: bool = True

    def __post_init__(self) -> None:
        for field in ("development_start", "development_end", "holdout_start", "holdout_end"):
            object.__setattr__(self, field, utc_datetime(getattr(self, field)))
        if (not self.development_start < self.development_end <= self.holdout_start < self.holdout_end
                or not all(isinstance(v, timedelta) for v in
                           (self.train_span, self.validation_span, self.step, self.embargo))
                or self.train_span <= timedelta(0) or self.validation_span <= timedelta(0)
                or self.step < self.validation_span or self.embargo < timedelta(0)
                or self.development_end + self.embargo > self.holdout_start
                or self.development_start + self.train_span + self.embargo
                + self.validation_span > self.development_end
                or not isinstance(self.instruments, tuple) or not self.instruments
                or len(set(self.instruments)) != len(self.instruments)
                or not all(isinstance(i, str) and i.strip() for i in self.instruments)
                or type(self.min_train_per_instrument) is not int
                or type(self.min_validation_per_instrument) is not int
                or min(self.min_train_per_instrument, self.min_validation_per_instrument) < 1
                or type(self.expanding) is not bool):
            raise ValueError("INVALID_WALK_FORWARD_SPEC")

    @property
    def digest(self) -> str:
        return sha256(self)


@dataclass(frozen=True, slots=True)
class Fold:
    fold_id: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    train_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    purged_train_ids: tuple[str, ...]
    purged_validation_ids: tuple[str, ...]
    embargo_ids: tuple[str, ...]
    train_counts: tuple[tuple[str, int], ...]
    validation_counts: tuple[tuple[str, int], ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    spec: WalkForwardSpec
    timing_sha256: str
    development_ids: tuple[str, ...]
    folds: tuple[Fold, ...]

    @property
    def digest(self) -> str:
        return sha256(self)

    @property
    def eligible(self) -> bool:
        return bool(self.folds) and all(not fold.blockers for fold in self.folds)


def _ordered(samples: tuple[SampleTiming, ...], instruments: tuple[str, ...],
             start: datetime, end: datetime) -> tuple[SampleTiming, ...]:
    if not isinstance(samples, tuple):
        raise ValueError("SAMPLES_MUST_BE_IMMUTABLE")
    seen: set[str] = set()
    keys: set[tuple[str, datetime]] = set()
    for sample in samples:
        key = (sample.instrument_key, sample.decision_at)
        if sample.sample_id in seen or key in keys:
            raise ValueError("DUPLICATE_SAMPLE_ID_OR_DECISION")
        if sample.instrument_key not in instruments:
            raise ValueError("UNREGISTERED_SAMPLE_INSTRUMENT")
        if not start <= sample.decision_at < end:
            raise ValueError("SAMPLE_OUTSIDE_DECLARED_PARTITION")
        seen.add(sample.sample_id)
        keys.add(key)
    return tuple(sorted(samples, key=lambda x: (x.decision_at, x.instrument_key, x.sample_id)))


def _counts(samples: tuple[SampleTiming, ...], instruments: tuple[str, ...]
            ) -> tuple[tuple[str, int], ...]:
    return tuple((key, sum(s.instrument_key == key for s in samples)) for key in instruments)


def _ids(samples: tuple[SampleTiming, ...]) -> tuple[str, ...]:
    return tuple(s.sample_id for s in samples)


def plan_walk_forward(spec: WalkForwardSpec, development: tuple[SampleTiming, ...]
                      ) -> WalkForwardPlan:
    """Fixed-duration folds based only on timestamps and preregistered bounds.

    All train decisions precede the embargo and validation. Purge examples
    whose outcome is not known strictly before the fitting cutoff. Validation
    labels must also be available by that validation window's end. A previous
    validation observation may enter a later fold's training once known.
    Block sparse folds rather than choose dates from outcomes.
    """
    ordered = _ordered(development, spec.instruments,
                       spec.development_start, spec.development_end)
    folds: list[Fold] = []
    val_start = spec.development_start + spec.train_span + spec.embargo
    while val_start + spec.validation_span <= spec.development_end:
        train_end = val_start - spec.embargo
        train_start = (spec.development_start if spec.expanding else train_end-spec.train_span)
        val_end = val_start + spec.validation_span
        train_pool = tuple(s for s in ordered if train_start <= s.decision_at < train_end)
        val_pool = tuple(s for s in ordered if val_start <= s.decision_at < val_end)
        train = tuple(s for s in train_pool if s.label_end < train_end
                      and s.label_available_at < train_end)
        validation = tuple(s for s in val_pool if s.label_end <= val_end
                           and s.label_available_at <= val_end)
        train_ids, val_ids = _ids(train), _ids(validation)
        train_set, val_set = set(train_ids), set(val_ids)
        train_counts = _counts(train, spec.instruments)
        val_counts = _counts(validation, spec.instruments)
        blockers = tuple(
            f"INSUFFICIENT_{phase.upper()}:{key}"
            for phase, counts, minimum in (
                ("train", train_counts, spec.min_train_per_instrument),
                ("validation", val_counts, spec.min_validation_per_instrument))
            for key, count in counts if count < minimum)
        embargo_ids = _ids(tuple(s for s in ordered if train_end <= s.decision_at < val_start))
        folds.append(Fold(
            f"fold-{len(folds)+1:04d}", train_start, train_end, val_start, val_end,
            train_ids, val_ids,
            tuple(s.sample_id for s in train_pool if s.sample_id not in train_set),
            tuple(s.sample_id for s in val_pool if s.sample_id not in val_set),
            embargo_ids, train_counts, val_counts, blockers,
        ))
        val_start += spec.step
    return WalkForwardPlan(spec, sha256(ordered), _ids(ordered), tuple(folds))


@dataclass(frozen=True, slots=True)
class HoldoutPartition:
    plan_sha256: str
    research_plan_sha256: str
    candidate_id: str
    candidate_config_sha256: str
    timing_sha256: str
    sample_ids: tuple[str, ...]
    purged_ids: tuple[str, ...]
    counts: tuple[tuple[str, int], ...]
    blockers: tuple[str, ...]


def prepare_holdout(plan: WalkForwardPlan, registry: ResearchRegistry,
                    samples: tuple[SampleTiming, ...]) -> HoldoutPartition:
    """Logical final partition gate, not a credential or data-access boundary.

    Requires all development folds eligible and a registry-selected candidate;
    the caller must obtain the registry from its durable authoritative journal.
    The registry must declare exactly the same final spans for all instruments.
    This never finalizes the economic test or changes registry state.
    """
    spec = plan.spec
    if (not plan.eligible or not registry.validation_locked or registry.locked_candidate is None
            or registry.final_assessment is not None):
        raise ValueError("HOLDOUT_REQUIRES_ELIGIBLE_PLAN_AND_LOCKED_CANDIDATE")
    final_windows = tuple(w for w in registry.plan.windows if w.split == "test")
    if (len(final_windows) != len(spec.instruments)
            or {w.instrument_key for w in final_windows} != set(spec.instruments)
            or any((w.start, w.end) != (spec.holdout_start, spec.holdout_end)
                   for w in final_windows)
            or any(w.end > spec.development_end for w in registry.plan.windows if w.split != "test")
            or registry.plan.policy.embargo != spec.embargo):
        raise ValueError("HOLDOUT_REGISTRY_WINDOW_MISMATCH")
    selected = next(c for c in registry.plan.candidates if c.candidate_id == registry.locked_candidate)
    ordered = _ordered(samples, spec.instruments, spec.holdout_start, spec.holdout_end)
    eligible = tuple(s for s in ordered if s.label_available_at <= spec.holdout_end
                     and s.label_end <= spec.holdout_end)
    accepted = set(_ids(eligible))
    if set(plan.development_ids) & set(_ids(ordered)):
        raise ValueError("HOLDOUT_REUSES_DEVELOPMENT_SAMPLE_ID")
    counts = _counts(eligible, spec.instruments)
    blockers = tuple(f"INSUFFICIENT_HOLDOUT:{key}" for key, count in counts
                     if count < spec.min_validation_per_instrument)
    return HoldoutPartition(
        plan.digest, registry.plan.digest, selected.candidate_id, selected.config_sha256,
        sha256(ordered), _ids(eligible), tuple(s.sample_id for s in ordered
                                             if s.sample_id not in accepted), counts, blockers,
    )
