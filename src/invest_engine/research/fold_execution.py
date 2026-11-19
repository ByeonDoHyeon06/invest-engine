"""E6.3b fixed-rule validation replay, not a training or promotion engine.

Every scored E5 event must have an eligible fold timing row; never silently
score purged labels, missing bars, or a partial instrument/fold matrix.
All inputs and complete run configurations are bound before execution.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from invest_engine.core.replay import canonical_bytes
from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Money, _decimal
from invest_engine.research.backtest import BacktestSettings, HistoricalBacktest
from invest_engine.research.candidates import BASELINES, Candidate, ResearchPlan, ResearchWindow, _hash
from invest_engine.research.evaluation import MINUTE, EvaluationWindow, validate_window
from invest_engine.research.fills import BarFillPolicy
from invest_engine.research.protection import ProtectionPolicy
from invest_engine.research.report import sha256
from invest_engine.research.report_evidence import ReportBinding, report_context_sha256
from invest_engine.research.research_journal import ResearchJournal
from invest_engine.research.walk_forward import SampleTiming, WalkForwardPlan, plan_walk_forward
from invest_engine.strategies.allocation import AllocationPolicy
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement, Strategy
from invest_engine.strategies.orb import ORBLongStrategy, ORBParameters
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.policy import RiskLimits


@dataclass(frozen=True, slots=True)
class FixedRule:
    candidate_id: str
    params: ORBParameters

    def __post_init__(self) -> None:
        if (not self.candidate_id.strip() or self.candidate_id in BASELINES
                or self.params.timeframe != MINUTE or self.params.prior_sessions > 20):
            raise ValueError("INVALID_FIXED_RULE")

    @property
    def config_sha256(self) -> str:
        return sha256(("e63b-protected-orb-v1", self.params))


@dataclass(frozen=True, slots=True)
class FoldScenario:
    settings: BacktestSettings
    cash: Decimal
    target: Decimal
    hold_stop: Decimal
    risk: RiskLimits
    base_fill: BarFillPolicy
    stress_fill: BarFillPolicy

    def __post_init__(self) -> None:
        if (not _hash(self.settings.code_sha) and
                not (len(self.settings.code_sha) == 40 and
                     all(c in "0123456789abcdef" for c in self.settings.code_sha))):
            raise ValueError("FOLD_CODE_REVISION_REQUIRED")
        if (_decimal(self.cash, field="cash") <= 0
                or not 0 < _decimal(self.target, field="target") <= 1
                or not 0 < _decimal(self.hold_stop, field="hold_stop") < 1
                or self.stress_fill.participation > self.base_fill.participation
                or self.stress_fill.spread_bps < self.base_fill.spread_bps
                or self.stress_fill.impact_bps < self.base_fill.impact_bps):
            raise ValueError("INVALID_FOLD_SCENARIO")

    @property
    def baseline_configs(self) -> tuple[tuple[str, str], ...]:
        return (("no-trade", sha256(("no-trade-v1", MINUTE))),
                ("buy-hold", sha256(("retry-first-fill-v2", MINUTE, self.target, self.hold_stop))))


@dataclass(frozen=True, slots=True)
class FoldInput:
    fold_id: str
    instrument_key: str
    calendar: StaticSessionCalendar
    window: EvaluationWindow
    events: tuple[EventEnvelope[MarketPayload], ...]
    base_config: TradingConfig
    stress_config: TradingConfig


@dataclass(frozen=True, slots=True)
class PreparedFold:
    fold_id: str
    window: ResearchWindow
    scenario_identity: str
    config_hashes: tuple[tuple[str, str, str], ...]


def _engine(case: FoldInput, scenario: FoldScenario, rule: FixedRule | None,
            candidate_id: str, cost: str) -> HistoricalBacktest:
    inst = case.events[0].instrument_id
    if inst is None:
        raise ValueError("FOLD_INSTRUMENT_REQUIRED")
    strategy: Strategy
    if candidate_id == "no-trade":
        strategy = NoTradeStrategy(DataRequirement("market.bar", MINUTE))
    elif candidate_id == "buy-hold":
        strategy = BuyHoldBaseline(MINUTE, scenario.target, scenario.hold_stop,
                                   retry_each_session=True)
    elif rule is not None and rule.candidate_id == candidate_id:
        strategy = ORBLongStrategy(rule.params)
    else:
        raise ValueError("FOLD_RULE_NOT_REGISTERED")
    fill = scenario.base_fill if cost == "base" else scenario.stress_fill
    config = case.base_config if cost == "base" else case.stress_config
    protected = rule is not None
    return HistoricalBacktest(
        calendar=case.calendar, strategies=(strategy,), config=config,
        opening_cash=(Money(scenario.cash, inst.currency),), risk=scenario.risk,
        fill_policy=fill, allocation_policy=AllocationPolicy(scenario.target, scenario.target),
        protection_policy=ProtectionPolicy(enabled=True, adverse_bps=fill.spread_bps+fill.impact_bps)
        if protected else None, settings=scenario.settings, evaluation_window=case.window,
        first_entry_only=candidate_id == "buy-hold", session_flat=protected,
    )


def prepare_validation(
    plan: WalkForwardPlan, timing: tuple[SampleTiming, ...], cases: tuple[FoldInput, ...],
    rules: tuple[FixedRule, ...], scenario: FoldScenario,
) -> tuple[PreparedFold, ...]:
    """Recompute fold membership, bind complete E5 configs before any replay."""
    if plan != plan_walk_forward(plan.spec, timing) or not plan.eligible:
        raise ValueError("FOLD_PLAN_INELIGIBLE_OR_MODIFIED")
    if (not isinstance(cases, tuple) or not isinstance(rules, tuple) or not rules
            or len({r.candidate_id for r in rules}) != len(rules)
            or any(r.params.target_fraction != scenario.target for r in rules)):
        raise ValueError("INVALID_FIXED_RULE_SET")
    expected = {(f.fold_id, i) for f in plan.folds for i in plan.spec.instruments}
    keys = [(c.fold_id, c.instrument_key) for c in cases]
    if len(set(keys)) != len(keys) or set(keys) != expected:
        raise ValueError("FOLD_MATRIX_INCOMPLETE_OR_DUPLICATE")
    fold_by_id = {f.fold_id: f for f in plan.folds}
    by_id = {s.sample_id: s for s in timing}
    prepared: list[PreparedFold] = []
    for case in sorted(cases, key=lambda c: (c.fold_id, c.instrument_key)):
        fold = fold_by_id[case.fold_id]
        coverage = validate_window(case.events, case.calendar, case.window)
        inst = case.events[0].instrument_id
        if (inst is None or inst.key != case.instrument_key
                or not fold.validation_start <= case.window.start < case.window.end <= fold.validation_end
                or case.calendar.sessions[0].start < fold.train_start
                or case.window.warmup_sessions != 20):
            raise ValueError("FOLD_E5_WINDOW_MISMATCH")
        # The rule runner is not a supervised learner. Timing rows identify
        # every scored E5 observation; if a row is purged, that full window
        # cannot be replayed/scored with the strict E5 contract.
        expected_samples = tuple(by_id[i] for i in fold.validation_ids
                                 if by_id[i].instrument_key == case.instrument_key)
        event_pairs = tuple((e.event_id, max(e.available_at, e.received_at))
                            for e in case.events[coverage.warmup_bars:])
        if (event_pairs != tuple((s.sample_id, s.decision_at) for s in expected_samples)
                or any(by_id[i].instrument_key == case.instrument_key
                       for i in fold.purged_validation_ids)):
            raise ValueError("FOLD_VALIDATION_SAMPLE_COVERAGE_MISMATCH")
        # Same instrument rules, settlement and all other trading settings.
        if (case.stress_config.fee_rate < case.base_config.fee_rate
                or case.stress_config.sell_tax_rate < case.base_config.sell_tax_rate
                or replace(case.base_config, fee_rate=case.stress_config.fee_rate,
                           sell_tax_rate=case.stress_config.sell_tax_rate) != case.stress_config):
            raise ValueError("FOLD_UNMATCHED_COST_POLICIES")
        lookup = {r.candidate_id: r for r in rules}
        configs = tuple((candidate, cost, _engine(case, scenario, lookup.get(candidate),
                                                  candidate, cost).config_digest())
                        for candidate in (*BASELINES, *sorted(lookup))
                        for cost in ("base", "stress"))
        # Bind costs, capital, rule parameters and initial full configs in the
        # common research context; register it before running any market arm.
        scenario_identity = sha256(("e63b-fixed-rule-matrix-v1", plan.digest, fold,
                                    scenario, tuple(sorted(rules, key=lambda r: r.candidate_id)),
                                    configs))
        context = report_context_sha256(case.calendar, case.window, scenario_identity)
        data = sha256(tuple(canonical_bytes(e).hex() for e in case.events))
        window = ResearchWindow(f"{case.fold_id}:{case.instrument_key}", case.instrument_key,
                                inst.currency, "validation", case.window.start, case.window.end,
                                data, context)
        prepared.append(PreparedFold(case.fold_id, window, scenario_identity, configs))
    return tuple(prepared)


def fixed_candidates(rules: tuple[FixedRule, ...], scenario: FoldScenario,
                     plan: WalkForwardPlan) -> tuple[Candidate, ...]:
    # Rules are frozen before validation, no fitted parameters or training labels.
    return tuple(Candidate(r.candidate_id, "orb-long:1.0.0", scenario.settings.code_sha,
                           r.config_sha256, plan.folds[0].train_end)
                 for r in sorted(rules, key=lambda r: r.candidate_id))


@dataclass(frozen=True, slots=True)
class FoldExecution:
    window_id: str
    candidate_id: str
    cost: str
    status: str
    report_sha256: str | None = None
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class FoldStudyResult:
    walk_forward_sha256: str
    research_plan_sha256: str
    runs: tuple[FoldExecution, ...]

    @property
    def complete(self) -> bool:
        return bool(self.runs) and all(r.status == "RECORDED" for r in self.runs)


def execute_validation(
    journal: ResearchJournal, research_plan_id: str, walk_forward: WalkForwardPlan,
    timing: tuple[SampleTiming, ...], cases: tuple[FoldInput, ...],
    rules: tuple[FixedRule, ...], scenario: FoldScenario,
) -> FoldStudyResult:
    """Run every registered developmental arm and persist provisional E5 evidence.

    Caller registers the ResearchPlan using prepared window/context digests first.
    No holdout events accepted. No strategy selection or journal lock performed.
    Per-arm failures are reported, never substituted with zero PnL.
    """
    prepared = prepare_validation(walk_forward, timing, cases, rules, scenario)
    registry = journal.get(research_plan_id)
    plan: ResearchPlan = registry.plan
    if registry.validation_locked or registry.final_assessment is not None:
        raise ValueError("FOLD_VALIDATION_ALREADY_LOCKED")
    if (tuple(sorted((w for w in plan.windows if w.split == "validation"),
                      key=lambda w: w.window_id)) !=
            tuple(sorted((p.window for p in prepared), key=lambda w: w.window_id))
            or tuple(sorted(plan.candidates, key=lambda c: c.candidate_id)) !=
            fixed_candidates(rules, scenario, walk_forward)
            or plan.baseline_config_sha256 != scenario.baseline_configs
            or plan.policy.embargo != walk_forward.spec.embargo
            or {(w.instrument_key, w.start, w.end) for w in plan.windows if w.split == "test"} !=
            {(key, walk_forward.spec.holdout_start, walk_forward.spec.holdout_end)
             for key in walk_forward.spec.instruments}
            or any(w.end > walk_forward.spec.development_end for w in plan.windows
                   if w.split != "test")):
        raise ValueError("FOLD_RESEARCH_PLAN_BINDING_MISMATCH")
    inputs = {(c.fold_id, c.instrument_key): c for c in cases}
    lookup = {r.candidate_id: r for r in rules}
    results: list[FoldExecution] = []
    for p in prepared:
        case = inputs[(p.fold_id, p.window.instrument_key)]
        for candidate, cost, config_hash in p.config_hashes:
            try:
                engine = _engine(case, scenario, lookup.get(candidate), candidate, cost)
                if engine.config_digest() != config_hash:
                    raise ValueError("FOLD_INITIAL_CONFIG_CHANGED")
                report = engine.run(case.events)
                binding = ReportBinding(plan.digest, p.window.window_id, candidate, cost, config_hash)
                journal.record_report(plan.plan_id, binding, report, case.events, case.calendar,
                                      case.window, scenario_identity=p.scenario_identity)
                results.append(FoldExecution(p.window.window_id, candidate, cost, "RECORDED",
                                             sha256(report)))
            except (ValueError, RuntimeError, ArithmeticError) as exc:
                results.append(FoldExecution(p.window.window_id, candidate, cost, "FAILED",
                                             error_type=type(exc).__name__))
    return FoldStudyResult(walk_forward.digest, plan.digest, tuple(results))
