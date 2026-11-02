"""PyTorch/Kineto Chrome trace statistics with explicit flow evidence.

Chrome timestamps are microseconds, converted to integer nanoseconds.
This parser does not infer source ownership from timestamp containment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path

from .intervals import duration


def read_chrome(path):
    path = Path(path)
    with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as fh:
        raw = json.load(fh)
    if isinstance(raw, dict):
        raw = raw.get('traceEvents', [])
    if not isinstance(raw, list):
        raise ValueError('Chrome trace expects traceEvents list')
    return raw


def _kind(evt):
    cat = str(evt.get('cat', '')).lower()
    args = evt.get('args') or {}
    device_type = str(args.get('Device Type', args.get('device_type', ''))).lower()
    if 'kernel' in cat or device_type in {'1', 'cuda', 'hip', 'gpu'}:
        return 'gpu'
    if 'cpu_op' in cat or 'python' in cat or 'operator' in cat or device_type in {'0', 'cpu'}:
        return 'cpu'
    if 'cuda_runtime' in cat or 'hip_runtime' in cat:
        return 'runtime'
    return 'other'


def analyze_torch_trace(path, top=25):
    events = read_chrome(path)
    spans = []
    endpoints = defaultdict(lambda: {'s': [], 'f': []})
    skipped = 0
    for evt in events:
        phase = evt.get('ph')
        if phase in ('s', 'f') and 'id' in evt:
            # Chrome flow IDs may be reused across PIDs; scope them.
            endpoints[(str(evt.get('pid')), str(evt['id']))][phase].append(evt)
        if phase != 'X':
            continue
        try:
            start, elapsed = round(float(evt['ts']) * 1000), round(float(evt['dur']) * 1000)
        except (ValueError, TypeError, KeyError):
            skipped += 1
            continue
        if elapsed <= 0:
            continue
        spans.append({'name': str(evt.get('name', '<unnamed>')), 'start_ns': start,
                      'end_ns': start + elapsed, 'pid': str(evt.get('pid')),
                      'tid': str(evt.get('tid')), 'kind': _kind(evt)})
    per_kind = {}
    for kind in ('cpu', 'gpu', 'runtime'):
        subset = [s for s in spans if s['kind'] == kind]
        counts = Counter(s['name'] for s in subset)
        summed = Counter()
        for s in subset:
            summed[s['name']] += s['end_ns'] - s['start_ns']
        per_kind[kind] = {'count': len(subset), 'sum_ns': sum(summed.values()),
                          'top': [{'name': n, 'calls': counts[n], 'duration_sum_ns': v}
                                  for n, v in summed.most_common(top)]}
    gpu = [s for s in spans if s['kind'] == 'gpu']
    cpu = [s for s in spans if s['kind'] == 'cpu']
    flows = []
    ambiguous = 0
    for key, points in endpoints.items():
        if len(points['s']) != 1 or len(points['f']) != 1:
            ambiguous += 1
            continue
        src, dst = points['s'][0], points['f'][0]
        try:
            start = round(float(src['ts']) * 1000)
            finish = round(float(dst['ts']) * 1000)
        except (KeyError, ValueError, TypeError):
            continue
        origins = [s for s in cpu if s['start_ns'] <= start <= s['end_ns'] and s['pid'] == str(src.get('pid')) and s['tid'] == str(src.get('tid'))]
        targets = [s for s in gpu if s['start_ns'] <= finish <= s['end_ns'] and s['pid'] == str(dst.get('pid')) and s['tid'] == str(dst.get('tid'))]
        if not origins or len(targets) != 1:
            continue
        nearest = min(origins, key=lambda s: (s['end_ns'] - s['start_ns'], s['name']))
        flows.append({'cpu_op': nearest['name'], 'gpu_kernel': targets[0]['name'],
                      'flow_id': key[1], 'source_pid': key[0],
                      'evidence': 'explicit Chrome flow endpoints plus CPU interval containment'})
    return {'source': str(Path(path).resolve()), 'spans': len(spans), 'skipped_spans': skipped,
            'domains': per_kind, 'gpu_union_ns': duration((e['start_ns'], e['end_ns']) for e in gpu),
            'flow_attribution': {'matched': len(flows), 'ambiguous_flow_ids': ambiguous,
                                 'samples': flows[:top]},
            'warnings': ['Trace event categories and GPU device type labels vary by PyTorch version.',
                         'Flow edges are profiler evidence, not a reconstructed complete execution DAG.',
                         'Inclusive operator time can double-count nested CPU operations.']}
