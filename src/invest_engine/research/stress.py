"""Repeat the *same* offline historical experiment under explicit adverse costs.

Results are sensitivities to *assumptions*, not calibrated broker execution.
Generated run specifications and intermediate artifacts are temporary.
"""
from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from invest_engine.domain.primitives import _decimal
from invest_engine.research.experiment import run_experiment
from invest_engine.research.report import canonical_json, sha256


@dataclass(frozen=True, slots=True)
class CostScenario:
    name: str
    extra_fee_rate: Decimal = Decimal(0)
    extra_sell_tax_rate: Decimal = Decimal(0)
    extra_spread_bps: Decimal = Decimal(0)
    extra_impact_bps: Decimal = Decimal(0)
    participation_scale: Decimal = Decimal(1)
    extra_stop_adverse_bps: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not self.name.strip() or '/' in self.name or '\\' in self.name:
            raise ValueError('invalid scenario identifier')
        for field in ('extra_fee_rate', 'extra_sell_tax_rate', 'extra_spread_bps',
                      'extra_impact_bps', 'participation_scale', 'extra_stop_adverse_bps'):
            value = _decimal(getattr(self, field), field=field)
            if value < 0:
                raise ValueError('cost changes cannot improve the base assumptions')
        if not Decimal(0) < self.participation_scale <= Decimal(1):
            raise ValueError('participation scale must be in (0,1]')


DEFAULT_SCENARIOS = (
    CostScenario('baseline'),
    CostScenario('higher_costs', extra_fee_rate=Decimal('0.0005'),
                 extra_spread_bps=Decimal('10'), extra_impact_bps=Decimal('10')),
    CostScenario('lower_liquidity', participation_scale=Decimal('0.5')),
    CostScenario('joint_adverse', extra_fee_rate=Decimal('0.001'),
                 extra_sell_tax_rate=Decimal('0.001'),
                 extra_spread_bps=Decimal('20'), extra_impact_bps=Decimal('20'),
                 participation_scale=Decimal('0.25'),
                 extra_stop_adverse_bps=Decimal('20')),
)


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    name: str
    assumptions: tuple[tuple[str, str], ...]
    run_sha256: str
    net_pnl: tuple[tuple[str, Decimal], ...]
    max_drawdown: tuple[tuple[str, Decimal], ...]
    entry_fills: int
    exit_fills: int
    total_fees: tuple[tuple[str, Decimal], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StressReport:
    schema_version: str
    dataset_file_sha256: str
    source_spec_sha256: str
    outcomes: tuple[ScenarioOutcome, ...]
    result_sha256: str
    warnings: tuple[str, ...]


def _alter_costs(spec: dict[str, object], scenario: CostScenario) -> dict[str, object]:
    amended = copy.deepcopy(spec)
    account = amended['account']
    fill = amended['fill_model']
    if not isinstance(account, dict) or not isinstance(fill, dict):
        raise ValueError('invalid research account/fill configuration')
    additions = (
        (account, 'fee_rate', scenario.extra_fee_rate),
        (account, 'sell_tax_rate', scenario.extra_sell_tax_rate),
        (fill, 'spread_bps', scenario.extra_spread_bps),
        (fill, 'impact_bps', scenario.extra_impact_bps),
    )
    for target, field, increment in additions:
        value = target[field]
        if not isinstance(value, str):
            raise ValueError('costs must be explicit decimal strings')
        target[field] = str(Decimal(value) + increment)
    raw_participation = fill['participation']
    if not isinstance(raw_participation, str):
        raise ValueError('participation must be a decimal string')
    fill['participation'] = str(Decimal(raw_participation) * scenario.participation_scale)
    protection = fill.get('protective_exit')
    if isinstance(protection, dict) and protection.get('enabled') is True:
        raw_adverse = protection['adverse_bps']
        if not isinstance(raw_adverse, str):
            raise ValueError('protection cost must be a decimal string')
        protection['adverse_bps'] = str(Decimal(raw_adverse) + scenario.extra_stop_adverse_bps)
    amended['run_id'] = str(amended['run_id']) + ':' + scenario.name
    amended['output_dir'] = 'scenario-artifacts'
    return amended


def run_cost_stress(
    config_file: Path | str,
    scenarios: tuple[CostScenario, ...] = DEFAULT_SCENARIOS,
) -> StressReport:
    path = Path(config_file).resolve()
    if not scenarios or scenarios[0].name != 'baseline':
        raise ValueError('first scenario must be the base assumptions')
    if len({s.name for s in scenarios}) != len(scenarios):
        raise ValueError('duplicate scenario identifier')
    if scenarios[0] != CostScenario('baseline'):
        raise ValueError('baseline must not change any assumption')
    source_data = path.read_bytes()
    spec: dict[str, object] = json.loads(source_data)
    dataset = spec['dataset']
    if not isinstance(dataset, dict) or not isinstance(dataset.get('events_jsonl'), str):
        raise ValueError('invalid dataset reference')
    source_path = (path.parent / dataset['events_jsonl']).resolve()
    # Generated specifications live in a disposable location. Absolute dataset
    # reference keeps the same exact data file in every scenario without copying.
    source_spec = sha256(spec)
    results: list[ScenarioOutcome] = []
    pinned_hash: str | None = None
    with tempfile.TemporaryDirectory(prefix='invest-e5-stress-') as scratch:
        temp_root = Path(scratch)
        for scenario in scenarios:
            trial = _alter_costs(spec, scenario)
            trial_dataset = trial['dataset']
            assert isinstance(trial_dataset, dict)
            trial_dataset['events_jsonl'] = str(source_path)
            trial_path = temp_root / 'run.json'
            trial_path.write_bytes(canonical_json(trial))
            outcome = run_experiment(trial_path)
            manifest = json.loads((outcome.output_dir / 'manifest.json').read_text())
            data_hash = manifest['dataset_file_sha256']
            if pinned_hash is None:
                pinned_hash = data_hash
            elif pinned_hash != data_hash:
                raise ValueError('dataset changed between stress scenarios')
            fill = trial['fill_model']
            account = trial['account']
            assert isinstance(fill, dict) and isinstance(account, dict)
            assumptions = tuple(sorted((key, str(value)) for key, value in {
                'fee_rate': account['fee_rate'], 'sell_tax_rate': account['sell_tax_rate'],
                'spread_bps': fill['spread_bps'], 'impact_bps': fill['impact_bps'],
                'participation': fill['participation'],
                'stop_adverse_bps': (
                    fill.get('protective_exit', {}).get('adverse_bps', 'disabled')
                    if isinstance(fill.get('protective_exit', {}), dict) else 'disabled'
                ),
            }.items()))
            report = outcome.report
            results.append(ScenarioOutcome(
                scenario.name, assumptions, report.run_sha256, report.net_pnl,
                report.max_drawdown, report.entry_fill_count, report.exit_fill_count,
                report.total_fees, report.notes,
            ))
    assert pinned_hash is not None
    warnings = [
        'HYPOTHETICAL_COSTS_NOT_BROKER_CALIBRATED',
        'RESULTS_NOT_EVIDENCE_OF_FUTURE_PROFIT',
        'NO_CROSS_CURRENCY_PNL_AGGREGATION',
    ]
    if all(case.entry_fills + case.exit_fills == 0 for case in results):
        warnings.append('INCONCLUSIVE_NO_TRADES')
    evidence = (source_spec, pinned_hash, tuple(results), tuple(warnings))
    return StressReport('e5-stress-v1', pinned_hash, source_spec, tuple(results),
                        sha256(evidence), tuple(warnings))


def export_stress(
    report: StressReport, path: Path | str, *, config_file: Path | str,
) -> None:
    """Export without overwriting the original configuration or market dataset."""
    dest = Path(path).resolve()
    spec_path = Path(config_file).resolve()
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    dataset = raw.get("dataset")
    if not isinstance(dataset, dict) or not isinstance(dataset.get("events_jsonl"), str):
        raise ValueError("invalid dataset path")
    data_path = (spec_path.parent / dataset["events_jsonl"]).resolve()
    original_out = raw.get('output_dir')
    if not isinstance(original_out, str) or not original_out.strip():
        raise ValueError('invalid original experiment output directory')
    baseline_directory = (spec_path.parent / original_out).resolve()
    if dest in (spec_path, data_path) or dest.is_relative_to(baseline_directory):
        raise ValueError("refusing to overwrite source config, dataset or baseline report")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(canonical_json(report))
