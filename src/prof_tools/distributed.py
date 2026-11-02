"""Rank-local and explicitly clock-aligned collective diagnostics.

No absolute-time comparisons across ranks without documented alignment.
Collective matching requires stable user-instrumented sequence IDs.
"""
from collections import defaultdict
import json
from pathlib import Path
import re
import statistics

from .intervals import duration, intersection_duration, subtract
from .trace_diagnostics import database, _events
from .trace import identify, marker_windows


def analyze_ranks(manifest_path, top=20):
    root = Path(manifest_path).resolve()
    manifest = json.loads(root.read_text())
    ranks = manifest.get('ranks', [])
    if not ranks or any('rank' not in r or 'trace' not in r for r in ranks):
        raise ValueError('rank manifest requires ranks with unique rank and trace fields')
    rank_ids = [str(r['rank']) for r in ranks]
    if len(set(rank_ids)) != len(rank_ids):
        raise ValueError('duplicate rank in manifest')
    # Every clock offset must refer to the same named clock domain.
    all_aligned = all('clock_offset_ns' in r and 'alignment_error_ns' in r and
                      'clock_domain' in r for r in ranks)
    if all_aligned and len({r['clock_domain'] for r in ranks}) != 1:
        raise ValueError('clock_domain must be identical across aligned ranks')
    if all_aligned and any(not isinstance(r['alignment_error_ns'], (int, float)) or
                           not isinstance(r['clock_offset_ns'], (int, float)) for r in ranks):
        raise ValueError('clock offsets and error bounds must be numeric')
    if all_aligned and any(r['alignment_error_ns'] < 0 for r in ranks):
        raise ValueError('alignment_error_ns must not be negative')
    data = {}
    marker = manifest.get('step_marker')
    for row in ranks:
        rank = str(row['rank'])
        path = (root.parent / row['trace']).resolve()
        with database(path) as conn:
            events, missing = _events(conn, identify(conn))
            if marker:
                try:
                    windows = marker_windows(conn, identify(conn), marker)
                except ValueError:
                    windows = []
            else:
                windows = []
        by_dev = defaultdict(list)
        for evt in events:
            if evt.kind == 'kernel':
                by_dev[evt.device or 'unknown'].append(evt)
        device_stats = {}
        for dev, kernels in by_dev.items():
            comm = [(e.start, e.end) for e in kernels if re.search('nccl|rccl', e.name, re.I)]
            compute = [(e.start, e.end) for e in kernels if not re.search('nccl|rccl', e.name, re.I)]
            device_stats[dev] = {'compute_union_ns': duration(compute),
                                 'collective_named_union_ns': duration(comm),
                                 'observed_compute_collective_overlap_ns': intersection_duration(comm, compute),
                                 'collective_only_intervals_ns': duration(subtract(comm, compute))}
        data[rank] = {'trace': str(path), 'kernel_devices': device_stats,
                      'host_marker_durations_ns': [end - start for start, end in windows],
                      'missing_domains': missing}
    # Inputs must identify the collective. Positional matching can be wrong when ranks diverge.
    collective_records = manifest.get('collectives', [])
    grouped = defaultdict(list)
    seen = set()
    for row in collective_records:
        required = {'rank', 'sequence_id', 'kind', 'start_ns', 'end_ns'}
        if not required <= row.keys():
            raise ValueError(f'collective record missing: {sorted(required - row.keys())}')
        rank = str(row['rank'])
        if rank not in data:
            raise ValueError(f'unknown rank {rank} in collective record')
        key = (rank, str(row['sequence_id']))
        if key in seen:
            raise ValueError(f'duplicate collective rank/sequence_id: {key}')
        seen.add(key)
        if row['end_ns'] <= row['start_ns']:
            raise ValueError('collective end_ns must exceed start_ns')
        grouped[str(row['sequence_id'])].append(row)
    aligned = {str(r['rank']): r for r in ranks} if all_aligned else {}
    collectives = []
    for sequence_id, records in sorted(grouped.items()):
        if len({r['kind'] for r in records}) > 1:
            raise ValueError(f'collective {sequence_id}: operation differs across ranks')
        durations = {str(r['rank']): r['end_ns'] - r['start_ns'] for r in records}
        summary = {'sequence_id': sequence_id, 'kind': records[0]['kind'],
                   'participating_ranks': sorted(durations), 'missing_ranks': sorted(set(rank_ids) - set(durations)),
                   'per_rank_duration_ns': durations,
                   'duration_spread_ns': max(durations.values()) - min(durations.values()),
                   'slowest_observed_duration_rank': max(durations, key=durations.get),
                   'start_skew_ns': None, 'start_skew_error_bound_ns': None}
        if all_aligned:
            starts = {str(r['rank']): r['start_ns'] + aligned[str(r['rank'])]['clock_offset_ns'] for r in records}
            errors = [aligned[str(r['rank'])]['alignment_error_ns'] for r in records]
            summary['start_skew_ns'] = max(starts.values()) - min(starts.values())
            summary['start_skew_error_bound_ns'] = 2 * max(errors)
            summary['last_observed_start_rank'] = max(starts, key=starts.get)
        collectives.append(summary)
    step_lags = {}
    if marker:
        for rank, item in data.items():
            samples = item['host_marker_durations_ns']
            step_lags[rank] = {'count': len(samples), 'median_ns': statistics.median(samples) if samples else None}
    return {'source': str(root), 'ranks': data, 'step_marker': marker, 'step_duration_by_rank': step_lags,
            'collectives': collectives[:top], 'total_matched_sequence_ids': len(collectives),
            'cross_rank_clock_alignment': 'explicit' if all_aligned else 'unavailable',
            'warnings': ['Name-matched NCCL/RCCL kernel overlap is observational, not proven hidden latency.',
                         'Last start or longest observed duration does not establish a causal straggler.',
                         'Collective sequence IDs and spans must come from explicit framework instrumentation.',
                         'Clock offsets must be independently calibrated; alignment error bounds are reported.']}
