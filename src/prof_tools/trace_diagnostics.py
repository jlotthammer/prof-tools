"""Portable diagnostic queries over Nsight Systems and ROCm rocpd SQLite.

Profiler timings are diagnostic observations, never unprofiled benchmark results.
No source ownership/critical path is inferred from temporal containment.
"""
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import math
import re
import sqlite3
import statistics

from .trace import identify, marker_windows, tables, columns, union_duration


@dataclass(frozen=True)
class Event:
    kind: str
    name: str
    start: int
    end: int
    device: str | None = None
    stream: str | None = None
    correlation: str | None = None
    size: int | None = None
    category: str | None = None
    pid: str | None = None
    graph_node: str | None = None


@contextmanager
def database(path):
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    conn = sqlite3.connect(uri, uri=True)
    try:
        yield conn
    finally:
        conn.close()


def _column(available, *candidates):
    return next((name for name in candidates if name in available), None)


def _select(conn, table, spec):
    """Select only recognized identifiers; absent optional fields return NULL."""
    available = columns(conn, table)
    selected = [f'"{match}"' if (match := _column(available, *names)) else 'NULL'
                for names in spec]
    return conn.execute(f'SELECT {", ".join(selected)} FROM "{table}"')


def _number(value):
    return str(value) if value is not None else None


def _events(conn, vendor):
    names = tables(conn)
    result = []
    missing = []

    def consume(table, kind, spec):
        if table not in names:
            missing.append(table)
            return
        available = columns(conn, table)
        if not _column(available, 'start', 'start_time', 'start_timestamp') or not (
            _column(available, 'end', 'end_time', 'end_timestamp') or 'duration' in available
        ):
            missing.append(f'{table} (no absolute intervals)')
            return
        for row in _select(conn, table, spec):
            title, start, end, duration, dev, stream, correlation, size, category, pid = row
            if start is None:
                continue
            if end is None and duration is None:
                continue
            finish = int(end) if end is not None else int(start) + int(duration)
            begin = int(start)
            if finish <= begin:
                continue
            result.append(Event(kind, str(title or '<unnamed>'), begin, finish,
                                _number(dev), _number(stream), _number(correlation),
                                int(size) if size is not None else None,
                                str(category) if category is not None else None, _number(pid)))

    time_spec = [('start', 'start_time', 'start_timestamp'),
                 ('end', 'end_time', 'end_timestamp'), ('duration',)]
    if vendor == 'nvidia':
        string_names = {}
        if 'StringIds' in names:
            string_names = dict(conn.execute('SELECT id, value FROM StringIds'))
        if 'CUPTI_ACTIVITY_KIND_KERNEL' not in names:
            missing.append('CUPTI_ACTIVITY_KIND_KERNEL')
        else:
            rows = _select(conn, 'CUPTI_ACTIVITY_KIND_KERNEL', [
                ('shortName', 'demangledName'), *time_spec, ('deviceId',), ('streamId',),
                ('correlationId',), ('_absent_size',), ('_absent_category',),
                ('globalPid', 'pid'), ('graphNodeId',)])
            for n, start, end, duration, dev, stream, corr, _, _, pid, graph_node in rows:
                if start is None or end is None or int(end) <= int(start):
                    continue
                result.append(Event('kernel', str(string_names.get(n, n or '<unnamed>')),
                                    int(start), int(end), _number(dev), _number(stream), _number(corr),
                                    pid=_number(pid), graph_node=_number(graph_node)))
        for table, kind, id_column in (
            ('CUPTI_ACTIVITY_KIND_RUNTIME', 'api', 'nameId'),
            ('CUPTI_ACTIVITY_KIND_DRIVER', 'api', 'nameId'),
            ('CUPTI_ACTIVITY_KIND_MEMCPY', 'copy', 'copyKind'),
            ('CUPTI_ACTIVITY_KIND_MEMSET', 'memset', 'memKind'),
        ):
            if table not in names:
                missing.append(table)
                continue
            for n, start, end, duration, dev, stream, corr, size, cat, pid in _select(conn, table, [
                (id_column,), *time_spec, ('deviceId',), ('streamId',),
                ('correlationId',), ('bytes',), ('_absent_category',), ('globalPid', 'pid')]):
                if start is None or end is None or int(end) <= int(start):
                    continue
                title = str(string_names.get(n, n)) if kind == 'api' else f'{kind}:{n}'
                result.append(Event(kind, title, int(start), int(end), _number(dev),
                                    _number(stream), _number(corr), int(size) if size is not None else None, pid=_number(pid)))
    else:
        consume('kernels', 'kernel', [('name',), *time_spec,
                ('agent_abs_index', 'gpu_id', 'device_id', 'gpu_agent_id', 'agent_id'),
                ('stream_id', 'stream', 'queue_id'), ('correlation_id', 'correlationId'),
                ('_absent_size',), ('_absent_category',), ('process_id', 'pid')])
        consume('memory_copies', 'copy', [('name', 'direction'), *time_spec,
                ('dst_agent_abs_index', 'dst_agent_id', 'agent_abs_index'),
                ('stream_id', 'stream'), ('correlation_id', 'correlationId'),
                ('size', 'bytes'), ('_absent_category',), ('process_id', 'pid')])
        if 'regions_and_samples' in names:
            # Includes HIP/HSA/RCCL APIs and markers. Restrict to known API-like categories.
            for n, start, end, duration, dev, stream, corr, _, cat, pid in _select(conn, 'regions_and_samples', [
                    ('name',), *time_spec, ('_absent_device',), ('_absent_stream',),
                    ('correlation_id', 'correlationId'), ('_absent_size',), ('category',), ('process_id', 'pid')]):
                if cat is None or not str(cat).upper().startswith(('HIP_', 'HSA_', 'RCCL_', 'MPI_', 'UCX_')):
                    continue
                if start is None or (end is None and duration is None):
                    continue
                finish = int(end) if end is not None else int(start) + int(duration)
                if finish > int(start):
                    result.append(Event('api', str(n), int(start), finish,
                                        correlation=_number(corr), category=str(cat), pid=_number(pid)))
        else:
            missing.append('regions_and_samples')
    return result, missing


def _clip(events, start, end):
    if start is None and end is None:
        return events
    low = start if start is not None else -math.inf
    high = end if end is not None else math.inf
    return [Event(e.kind, e.name, max(e.start, low), min(e.end, high), e.device,
                  e.stream, e.correlation, e.size, e.category, e.pid, e.graph_node)
            for e in events if min(e.end, high) > max(e.start, low)]


def _percentile(values, q):
    seq = sorted(values)
    if not seq:
        return None
    pos = (len(seq) - 1) * q
    low = int(pos)
    high = min(low + 1, len(seq) - 1)
    return seq[low] + (seq[high] - seq[low]) * (pos - low)


def _intervals(events):
    return [(e.start, e.end) for e in events]


from .intervals import intersection_duration as _overlap_duration


def _groups(events, top):
    groups = defaultdict(list)
    for e in events:
        groups[e.name].append(e.end - e.start)
    result = []
    for name, values in groups.items():
        result.append({'name': name, 'calls': len(values), 'sum_ns': sum(values),
                       'mean_ns': statistics.mean(values), 'median_ns': statistics.median(values),
                       'p95_ns': _percentile(values, .95), 'max_ns': max(values)})
    return sorted(result, key=lambda d: (-d['sum_ns'], d['name']))[:top]


def _queue_delays(events, top):
    """Correlate unique CUDA API launches to GPU activities, not source ranges."""
    runtimes = defaultdict(list)
    kernels = defaultdict(list)
    for e in events:
        if e.correlation is None:
            continue
        if e.kind == 'api':
            runtimes[(e.pid, e.correlation)].append(e)
        elif e.kind == 'kernel':
            kernels[(e.pid, e.correlation)].append(e)
    delays = []
    ambiguous = 0
    for corr, launches in kernels.items():
        apis = runtimes.get(corr, [])
        if len(launches) != 1 or len(apis) != 1 or launches[0].graph_node not in (None, '0'):
            ambiguous += len(launches)
            continue
        if launches[0].start >= apis[0].end:
            delays.append(launches[0].start - apis[0].end)
    return {'matched_unique_launches': len(delays), 'ambiguous_or_unmatched_launches': ambiguous,
            'kernels_without_correlation_id': sum(e.kind == 'kernel' and e.correlation is None for e in events),
            'median_launch_to_start_ns': statistics.median(delays) if delays else None,
            'p95_launch_to_start_ns': _percentile(delays, .95),
            'caveat': 'time from CUDA/HIP API return to kernel start is not all host launch overhead; CUDA graphs may lack one-to-one API correlation; correlation IDs may be reused across processes'}


def _diagnose(conn, vendor, top, start_ns, end_ns, range_name, range_index):
    raw_events, missing = _events(conn, vendor)
    selected = None
    if range_name is not None:
        if start_ns is not None or end_ns is not None:
            raise ValueError('choose range-name or explicit timestamp bounds')
        windows = marker_windows(conn, vendor, range_name)
        if not 0 <= range_index < len(windows):
            raise ValueError(f'range-index {range_index} outside {len(windows)} matching ranges')
        start_ns, end_ns = windows[range_index]
        selected = {'name': range_name, 'index': range_index, 'matching_ranges': len(windows),
                    'start_ns': start_ns, 'end_ns': end_ns,
                    'scope': 'host timestamp window, not GPU causal ownership'}
    if start_ns is not None and end_ns is not None and start_ns >= end_ns:
        raise ValueError('end-ns must exceed start-ns')
    events = _clip(raw_events, start_ns, end_ns)
    selected_launches = [e for e in raw_events if e.kind == "kernel" and (start_ns is None or e.start >= start_ns) and (end_ns is None or e.start < end_ns)]
    selected_ids = {e.correlation for e in selected_launches if e.correlation is not None}
    correlation_events = selected_launches + [e for e in raw_events if e.kind == "api" and e.correlation in selected_ids]
    by_kind = defaultdict(list)
    for event in events:
        by_kind[event.kind].append(event)
    ranges = {}
    for kind, subset in by_kind.items():
        ranges[kind] = {'events': len(subset), 'duration_sum_ns': sum(e.end - e.start for e in subset),
                        'reported_bytes': sum(e.size for e in subset if e.size is not None),
                        'events_with_known_bytes': sum(e.size is not None for e in subset),
                        'top': _groups(subset, top)}
    per_device = {}
    for dev in sorted({e.device or 'unknown' for e in by_kind['kernel'] + by_kind['copy'] + by_kind['memset']}):
        k = [e for e in by_kind['kernel'] if (e.device or 'unknown') == dev]
        copies = [e for e in by_kind['copy'] if (e.device or 'unknown') == dev]
        memsets = [e for e in by_kind['memset'] if (e.device or 'unknown') == dev]
        compute = [e for e in k if not re.search(r'(?i)(nccl|rccl)', e.name)]
        comm = [e for e in k if re.search(r'(?i)(nccl|rccl)', e.name)]
        kints, cints = _intervals(k), _intervals(copies)
        mints = _intervals(memsets)
        all_intervals = kints + cints + mints
        extent = None
        if all_intervals:
            begin = start_ns if start_ns is not None else min(s for s, _ in all_intervals)
            finish = end_ns if end_ns is not None else max(e for _, e in all_intervals)
            extent = max(0, finish - begin)
        per_device[dev] = {
            'kernel_busy_union_ns': union_duration(kints),
            'copy_busy_union_ns': union_duration(cints),
            'memset_busy_union_ns': union_duration(mints),
            'kernel_copy_overlap_ns': _overlap_duration(kints, cints),
            'any_gpu_activity_union_ns': union_duration(all_intervals),
            'observed_window_ns': extent,
            'observed_no_activity_ns': (extent - union_duration(all_intervals)) if extent is not None else None,
            'compute_kernel_union_ns': union_duration(_intervals(compute)),
            'collective_named_kernel_union_ns': union_duration(_intervals(comm)),
            'compute_collective_overlap_ns': _overlap_duration(_intervals(compute), _intervals(comm)),
            'collective_classification': 'heuristic: kernel name contains NCCL or RCCL; validate for the workload',
        }
    sync = [e for e in by_kind['api'] if re.search(r'(?i)(synchronize|wait|streamquery|eventquery|hipdevicesynchronize|cudadevicesynchronize)', e.name)]
    return {
        'vendor': vendor, 'selected_window': selected,
        'window_limits_ns': {'start': start_ns, 'end': end_ns},
        'domains': ranges, 'per_device': per_device,
        'launch_queue_diagnostics': _queue_delays(correlation_events, top),
        'synchronization_api_observations': {'calls': len(sync),
            'duration_sum_ns': sum(e.end - e.start for e in sync),
            'top': _groups(sync, top),
            'scope': 'host API duration; overlaps other host threads; not proved device idle or avoidable stall'},
        'missing_domains': sorted(set(missing)),
        'warnings': [
            'Profiler intervals and their sums are diagnostic, NOT an unprofiled performance comparison.',
            'CPU marker time clipping is not causal GPU attribution: kernels may launch asynchronously.',
            'Per-device interval union is not SM utilization, bandwidth utilization or critical path.',
            'Device IDs and host timestamp epochs may differ across processes: no cross-rank overlap inference.',
            'Capture coverage and hardware counters vary by profiler version/configuration.',
        ],
    }


def inspect_schema(path):
    with database(path) as conn:
        names = tables(conn)
        try:
            vendor = identify(conn)
        except ValueError:
            vendor = 'unknown'
        return {'file': str(Path(path).resolve()), 'vendor': vendor,
                'tables': {table: sorted(columns(conn, table)) for table in sorted(names)}}


def diagnose(path, top=20, start_ns=None, end_ns=None, range_name=None, range_index=0):
    if top < 1:
        raise ValueError('top must be positive')
    with database(path) as conn:
        vendor = identify(conn)
        result = _diagnose(conn, vendor, top, start_ns, end_ns, range_name, range_index)
        result['source'] = str(Path(path).resolve())
        return result



def step_diagnostics(path, range_name, top=10):
    """Compare host marker durations and per-step GPU activity without asserting ownership."""
    if top < 1:
        raise ValueError('top must be positive')
    with database(path) as conn:
        vendor = identify(conn)
        windows = marker_windows(conn, vendor, range_name)
        events, missing = _events(conn, vendor)
        durations = [end - start for start, end in windows]
        steps = []
        for index, (start, end) in enumerate(windows):
            selected = _clip(events, start, end)
            kernels = [x for x in selected if x.kind == 'kernel']
            copies = [x for x in selected if x.kind == 'copy']
            steps.append({'index': index, 'start_ns': start, 'end_ns': end,
                          'host_marker_duration_ns': end - start,
                          'kernel_count_overlapping_window': len(kernels),
                          'copy_count_overlapping_window': len(copies),
                          'kernel_busy_union_ns': union_duration(_intervals(kernels)),
                          'copy_busy_union_ns': union_duration(_intervals(copies))})
    slowest = sorted(steps, key=lambda x: (-x['host_marker_duration_ns'], x['index']))[:top]
    return {'source': str(Path(path).resolve()), 'vendor': vendor, 'marker': range_name,
            'marker_count': len(windows),
            'host_marker_duration_ns': {'median': statistics.median(durations),
                'p95': _percentile(durations, .95), 'min': min(durations), 'max': max(durations)},
            'slowest_host_markers': slowest, 'missing_domains': sorted(set(missing)),
            'warnings': ['Host marker duration need not equal a synchronized GPU step.',
                         'GPU activity is selected by temporal intersection, not launch ownership.',
                         'Do not infer GPU speedup from profiler-marker durations.']}


def compare_traces(baseline, candidate, top=30, range_name=None, range_index=0):
    """Compare diagnostic kernel distributions, not profiler-derived speedups."""
    base = diagnose(baseline, top=10**9, range_name=range_name, range_index=range_index)
    new = diagnose(candidate, top=10**9, range_name=range_name, range_index=range_index)
    before = {x['name']: x for x in base['domains'].get('kernel', {}).get('top', [])}
    after = {x['name']: x for x in new['domains'].get('kernel', {}).get('top', [])}
    differences = []
    for name in before.keys() | after.keys():
        b, c = before.get(name), after.get(name)
        differences.append({'name': name,
                            'baseline_calls': b['calls'] if b else 0,
                            'candidate_calls': c['calls'] if c else 0,
                            'baseline_total_ns': b['sum_ns'] if b else 0,
                            'candidate_total_ns': c['sum_ns'] if c else 0,
                            'delta_total_ns': (c['sum_ns'] if c else 0) - (b['sum_ns'] if b else 0),
                            'baseline_median_ns': b['median_ns'] if b else None,
                            'candidate_median_ns': c['median_ns'] if c else None,
                            'baseline_p95_ns': b['p95_ns'] if b else None,
                            'candidate_p95_ns': c['p95_ns'] if c else None})
    differences.sort(key=lambda r: (-abs(r['delta_total_ns']), r['name']))
    return {'baseline': str(Path(baseline).resolve()), 'candidate': str(Path(candidate).resolve()),
            'baseline_vendor': base['vendor'], 'candidate_vendor': new['vendor'],
            'kernel_changes': differences[:top], 'total_distinct_kernels': len(differences),
            'domain_totals': {'baseline': {k: v['duration_sum_ns'] for k, v in base['domains'].items()},
                              'candidate': {k: v['duration_sum_ns'] for k, v in new['domains'].items()}},
            'warnings': ['Diagnostic profile comparison only. Require matched workload, capture ranges, profiler settings and unprofiled paired benchmark for speedup claims.',
                         'Kernel names, devices, streams, and profiler versions may not be comparable across vendors or builds.',
                         'A negative change in summed kernel durations is not necessarily a decrease in end-to-end latency.']}


def export_events(path, out, kind='all', start_ns=None, end_ns=None):
    """Export normalized activities as JSON Lines for agent-authored analysis.

    The exported times are original profiler timestamps except at explicitly
    requested window boundaries, where intersecting intervals are clipped.
    """
    import json
    from dataclasses import asdict

    if kind not in {'all', 'kernel', 'api', 'copy', 'memset'}:
        raise ValueError('unknown event kind')
    if start_ns is not None and end_ns is not None and start_ns >= end_ns:
        raise ValueError('end-ns must exceed start-ns')
    source = Path(path).resolve()
    target = Path(out).resolve()
    if source == target or target.exists():
        raise FileExistsError('export destination exists or equals input; choose a new output path')
    with database(path) as conn:
        vendor = identify(conn)
        events, missing = _events(conn, vendor)
    selected = _clip(events, start_ns, end_ns)
    if kind != 'all':
        selected = [e for e in selected if e.kind == kind]
    selected.sort(key=lambda x: (x.start, x.end, x.kind, x.name))
    with target.open('x', encoding='utf-8') as file:
        for event in selected:
            file.write(json.dumps(asdict(event), sort_keys=True) + '\n')
    return {'source': str(source), 'vendor': vendor, 'output_jsonl': str(target),
            'exported_events': len(selected), 'kind': kind, 'missing_domains': sorted(set(missing)),
            'warning': 'Names and timestamps normalized, but GPU clocks are not aligned across independent processes; timestamps are clipped at requested window boundaries.'}
