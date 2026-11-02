"""Single deterministic evidence report for automatic performance triage."""
from __future__ import annotations

from pathlib import Path
import json

from .counters import load_counters, summarize_counter_records
from .counter_hypotheses import nvidia_saturation_hypotheses
from .dependencies import analyze_dependency_graph
from .gpu_dependencies import analyze_gpu_dependencies
from .distributed import analyze_ranks
from .torch_trace import analyze_torch_trace
from .trace_diagnostics import diagnose, step_diagnostics


def finding(code, severity, observation, followup, evidence, confidence='medium'):
    return {'code': code, 'severity': severity, 'confidence': confidence,
            'observation': observation, 'evidence': evidence, 'next_experiment': followup}


def auto_diagnose(trace=None, counter_file=None, counter_manifest=None,
                  counter_table=None, counter_columns=None, torch_trace=None,
                  ranks_manifest=None, dependency_graph=None, marker=None, top=20):
    if not any((trace, counter_file, torch_trace, ranks_manifest, dependency_graph)):
        raise ValueError('provide at least one evidence source')
    if bool(counter_file) != bool(counter_manifest):
        raise ValueError('counter-file and counter-manifest must be supplied together')
    result = {'schema_version': 1, 'sources': {}, 'findings': [], 'limitations': []}
    findings = result['findings']
    if marker and not trace:
        raise ValueError('step marker requires a GPU trace')
    if trace:
        diag = diagnose(trace, top=top)
        result['sources']['gpu_trace'] = diag
        result['sources']['gpu_dependency_evidence'] = analyze_gpu_dependencies(trace)
        for device, stats in diag['per_device'].items():
            span = stats['observed_window_ns']
            idle = stats['observed_no_activity_ns']
            if span and idle is not None and idle / span >= .25:
                findings.append(finding('OBSERVED_GPU_GAPS', 'investigate',
                    f'{device}: {idle/span:.1%} of observed GPU activity window has no recorded kernels/copies/memsets',
                    'Test input preparation, host scheduling and launch queues with CPU and runtime markers; rule out trace gaps.',
                    {'device': device, 'idle_ns': idle, 'window_ns': span}, 'low'))
            collective = stats['collective_named_kernel_union_ns']
            if collective:
                findings.append(finding('COLLECTIVE_ACTIVITY', 'investigate',
                    f'{device}: collective-named kernel union {collective} ns; observed compute overlap {stats["compute_collective_overlap_ns"]} ns',
                    'Capture rank-stable collective sequence IDs and explicitly aligned clocks; test overlap on unprofiled step time.',
                    {'device': device, 'collective_ns': collective,
                     'overlap_ns': stats['compute_collective_overlap_ns']}, 'low'))
        launches = diag['launch_queue_diagnostics']
        if launches['matched_unique_launches']:
            findings.append(finding('LAUNCH_TO_START_DELAY', 'observe',
                f'{launches["matched_unique_launches"]} unambiguous launch correlations; median API-return-to-GPU-start {launches["median_launch_to_start_ns"]} ns',
                'Investigate stream dependencies and CPU submission cadence before changing launch strategy.',
                launches, 'medium'))
        sync = diag['synchronization_api_observations']
        if sync['calls']:
            findings.append(finding('HOST_SYNCHRONIZATION', 'investigate',
                f'{sync["calls"]} observed host synchronization calls (summed {sync["duration_sum_ns"]} ns)',
                'Attribute waits to source call sites and thread; test avoiding unnecessary barriers with correctness checks.',
                {'calls': sync['calls'], 'sum_ns': sync['duration_sum_ns']}, 'medium'))
        result['limitations'].extend(diag['warnings'])
        if marker:
            steps = step_diagnostics(trace, marker, top)
            result['sources']['steps'] = steps
            median, p95 = steps['host_marker_duration_ns']['median'], steps['host_marker_duration_ns']['p95']
            if median and p95 > 1.2 * median:
                findings.append(finding('STEP_VARIABILITY', 'investigate',
                    f'Host marker p95/median = {p95/median:.2f} across {steps["marker_count"]} recorded steps',
                    'Compare straggling iterations with dataloader, compilation, allocation, synchronization and collective activity; collect more steps.',
                    {'median_ns': median, 'p95_ns': p95, 'count': steps['marker_count']}, 'medium'))
    if counter_file:
        capture, raw_counters, errors = load_counters(counter_file, counter_manifest, counter_table, counter_columns)
        if trace and capture.vendor != diag['vendor']:
            raise ValueError(f'counter vendor {capture.vendor!r} does not match trace vendor {diag["vendor"]!r}')
        counters = summarize_counter_records(capture, raw_counters, counter_file, errors, top=top)
        result['sources']['counters'] = counters
        for observation in nvidia_saturation_hypotheses(capture, raw_counters):
            findings.append(finding(observation['code'], 'investigate', observation['interpretation'],
                                    observation['next_check'], observation, 'medium'))
        result['limitations'].append('Counter samples may reflect replay/serialization and must not be used as acceptance timing.')
        # Names and units remain vendor-specific: no inferred utilization without known mapping.
        findings.append(finding('COUNTER_EVIDENCE', 'observe',
            f'{counters["records"]} typed counter records, {counters["distinct_metrics"]} distinct metric/unit pairs',
            'Select a bottleneck hypothesis from documented architecture-specific counters, validate it with a matched experiment.',
            {'metrics': counters['metrics'][:top], 'architecture': counters['capture']['architecture']}, 'high'))
    if torch_trace:
        pytorch = analyze_torch_trace(torch_trace, top)
        result['sources']['pytorch_trace'] = pytorch
        flows = pytorch['flow_attribution']
        if flows['matched']:
            findings.append(finding('PYTORCH_EXPLICIT_FLOWS', 'observe',
                f'{flows["matched"]} explicit CPU→GPU flow matches',
                'Investigate the corresponding CPU operators and preserve shape/stride when constructing a kernel reproducer.',
                {'flow_samples': flows['samples']}, 'medium'))
        result['limitations'].extend(pytorch['warnings'])
    if ranks_manifest:
        distributed = analyze_ranks(ranks_manifest, top)
        result['sources']['distributed'] = distributed
        for col in distributed['collectives']:
            if col['missing_ranks']:
                findings.append(finding('INCOMPLETE_COLLECTIVE', 'investigate',
                    f'{col["sequence_id"]} not observed on ranks {col["missing_ranks"]}',
                    'Verify instrumented rank set and tracing completeness before diagnosing a missing collective.',
                    {'sequence_id': col['sequence_id'], 'missing_ranks': col['missing_ranks']}, 'medium'))
            if col['start_skew_ns'] is not None and col['start_skew_ns'] > 2 * col['start_skew_error_bound_ns']:
                findings.append(finding('COLLECTIVE_START_SKEW', 'investigate',
                    f'{col["sequence_id"]}: start skew {col["start_skew_ns"]} ns ± {col["start_skew_error_bound_ns"]} ns',
                    'Inspect rank-specific input/compute work preceding this sequence ID; do not assume late launch caused collective time.',
                    {'sequence_id': col['sequence_id'], 'start_skew_ns': col['start_skew_ns']}, 'medium'))
        result['limitations'].extend(distributed['warnings'])
    if dependency_graph:
        result['sources']['dependency_graph'] = analyze_dependency_graph(dependency_graph)
        result['limitations'].append('A weighted dependency path is causal only if input graph edges and node coverage are complete and verified.')
    if not findings:
        findings.append(finding('INSUFFICIENT_EVIDENCE', 'observe',
            'Available records do not identify a specific bottleneck',
            'Capture a representative steady-state GPU/CPU trace and architecture-specific counters.', {}, 'high'))
    result['findings'] = sorted(findings, key=lambda item: (
        {'investigate': 0, 'observe': 1}[item['severity']], item['code']))
    result['limitations'].append('Only unprofiled paired benchmarks establish a performance improvement.')
    return result
