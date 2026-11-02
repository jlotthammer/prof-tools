"""Typed, provenance-preserving hardware-counter ingestion.

Counter names are vendor-defined. The only generic arithmetic is on numeric
values with exactly matching metric identity, unit, architecture and conditions.
"""
from __future__ import annotations

import csv
from contextlib import closing
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class Capture:
    vendor: str
    architecture: str
    profiler: str
    profiler_version: str
    command: str
    replay_mode: str
    workload_id: str
    device_id: str
    conditions: dict


@dataclass(frozen=True)
class Counter:
    metric: str
    value: float
    unit: str
    kernel: str | None
    dispatch: str | None
    device: str | None
    process: str | None
    context: str | None
    stream: str | None
    source: str


FIELD_NAMES = {
    'metric': ('Metric Name', 'Metric', 'MetricName', 'Metric_Name', 'name'),
    'value': ('Metric Value', 'Value', 'MetricValue', 'Metric_Value', 'value'),
    'unit': ('Metric Unit', 'Unit', 'MetricUnit', 'units', 'unit'),
    'kernel': ('Kernel Name', 'Kernel', 'KernelName', 'kernel_name'),
    'dispatch': ('ID', 'Dispatch ID', 'Dispatch', 'dispatch_id'),
    'device': ('Device', 'GPU ID', 'Device ID', 'gpu_id'),
    'process': ('Process ID', 'PID', 'process_id'),
    'context': ('Context', 'Context ID', 'context_id'),
    'stream': ('Stream', 'Stream ID', 'stream_id'),
}


def _header_map(fields, override=None):
    field_map = {}
    for dest, aliases in FIELD_NAMES.items():
        choice = (override or {}).get(dest)
        if choice and choice not in fields:
            raise ValueError(f'mapped {dest} column {choice!r} absent')
        field_map[dest] = choice or next((x for x in aliases if x in fields), None)
    if not field_map['metric'] or not field_map['value'] or not field_map['unit']:
        raise ValueError('counter table needs explicit metric, value, and unit columns; provide a schema map')
    return field_map


def _number(raw):
    text = str(raw).strip().replace(',', '')
    if not text or text in {'N/A', 'nan', 'NaN', '--', 'None'}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _row(row, fields, source):
    metric = str(row.get(fields['metric']) or '').strip()
    unit = str(row.get(fields['unit']) or '').strip()
    value = _number(row.get(fields['value']))
    if not metric or not unit or value is None:
        return None

    def optional(key):
        value = row.get(fields[key]) if fields[key] else None
        return str(value).strip() if value is not None and str(value).strip() else None

    return Counter(metric, value, unit, optional('kernel'), optional('dispatch'),
                   optional('device'), optional('process'), optional('context'),
                   optional('stream'), source)


def csv_counters(path, mapping=None):
    """Read NVIDIA ncu --csv --page raw or explicitly mapped AMD metric tables.

    Ignores pre-header profiler notices; rejects ambiguous or unsupported schemas.
    """
    results = []
    with Path(path).open(newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        header = None
        fields = None
        for cells in reader:
            if not cells:
                continue
            if header is None or all(x in cells for x in (fields['metric'], fields['value'], fields['unit'])):
                try:
                    candidate = _header_map(cells, mapping)
                except ValueError:
                    if header is None:
                        continue
                else:
                    header, fields = cells, candidate
                    continue
            if header is None:
                continue
            if len(cells) != len(header):
                continue
            item = _row(dict(zip(header, cells)), fields, str(Path(path)))
            if item is not None:
                results.append(item)
    if header is None:
        raise ValueError(f'{path}: no recognized metric/value/unit header; inspect export schema')
    return results


def sqlite_counters(path, table, mapping):
    """Strict read-only schema-mapped ROCm analysis DB ingestion.

    Report database view layouts evolve: require an explicit table/column map
    rather than silently guessing a plausible but wrong metric column.
    """
    if not mapping:
        raise ValueError('SQLite counter report requires explicit schema column map')
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        tables = {x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if table not in tables:
            raise ValueError(f'{table!r} absent; available views: {sorted(tables)}')
        escaped = table.replace('\"', '\"\"')
        cols = {x[1] for x in conn.execute(f'PRAGMA table_info("{escaped}")')}
        fields = _header_map(cols, mapping)
        results = []
        cursor = conn.execute(f'SELECT * FROM "{escaped}"')
        names = [x[0] for x in cursor.description]
        for values in cursor:
            item = _row(dict(zip(names, values)), fields, f'{path}:{table}')
            if item is not None:
                results.append(item)
    return results


def read_capture(path):
    document = json.loads(Path(path).read_text())
    expected = set(Capture.__dataclass_fields__)
    if set(document) != expected:
        raise ValueError(f'capture manifest fields: missing={sorted(expected - set(document))}, unexpected={sorted(set(document) - expected)}')
    cap = Capture(**document)
    if cap.vendor not in ('nvidia', 'amd') or not cap.architecture or not cap.profiler_version or not cap.command or not cap.workload_id or not cap.replay_mode or not cap.device_id or not cap.profiler:
        raise ValueError('capture manifest requires vendor, architecture, profiler version, command, workload')
    valid = {'nvidia': {'ncu', 'nsight-compute'},
             'amd': {'rocprof-compute', 'rocprofiler-compute'}}
    if cap.profiler not in valid[cap.vendor]:
        raise ValueError(f'unsupported counter profiler {cap.profiler!r} for vendor {cap.vendor!r}')
    if not isinstance(cap.conditions, dict):
        raise ValueError('capture conditions must be a JSON object')
    return cap


def load_counters(source, manifest, table=None, columns=None):
    cap = read_capture(manifest)
    if Path(source).suffix.lower() in ('.db', '.sqlite', '.sqlite3'):
        if not table:
            raise ValueError('SQLite counter DB needs --table and --column-map; run trace-schema to inspect it')
        data = sqlite_counters(source, table, columns)
    else:
        if Path(source).is_dir():
            csv_files = sorted(Path(source).glob('*.csv'))
            if not csv_files:
                raise ValueError('counter directory contains no CSV tables')
            data = []
            errors = []
            for path in csv_files:
                try:
                    data.extend(csv_counters(path, columns))
                except ValueError as exc:
                    errors.append(str(exc))
        else:
            data = csv_counters(source, columns)
            errors = []
    if not data:
        raise ValueError('no numeric counter values with explicit units found')
    return cap, data, (errors if 'errors' in locals() else [])


def counter_summary(source, manifest, table=None, columns=None, top=100):
    capture, counters, errors = load_counters(source, manifest, table, columns)
    return summarize_counter_records(capture, counters, source, errors, top)


def summarize_counter_records(capture, counters, source, errors=(), top=100):
    values = [asdict(c) for c in counters[:top]]
    metrics = sorted({(c.metric, c.unit) for c in counters})
    return {'capture': asdict(capture), 'source': str(source), 'records': len(counters),
            'distinct_metrics': len(metrics), 'metrics': [{'name': n, 'unit': u} for n, u in metrics],
            'samples': values, 'truncated': len(counters) > top,
            'unreadable_tables': errors,
            'interpretation': 'hardware-counter observations under replay/instrumentation; not full-step throughput'}


def compare_counter_reports(baseline, candidate, baseline_manifest, candidate_manifest,
                            table=None, columns=None):
    a, original, _ = load_counters(baseline, baseline_manifest, table, columns)
    b, changed, _ = load_counters(candidate, candidate_manifest, table, columns)
    invariants = ('vendor', 'architecture', 'profiler', 'profiler_version', 'replay_mode',
                  'workload_id', 'device_id', 'conditions')
    conflicts = [field for field in invariants if getattr(a, field) != getattr(b, field)]
    if conflicts:
        raise ValueError(f'counter captures not comparable; differing fields: {conflicts}')
    def index(rows):
        indexed = {}
        ambiguous = set()
        for record in rows:
            # Process/stream/context IDs are capture-local and often differ
            # between independent invocations; preserve but do not match on them.
            key = (record.metric, record.unit, record.kernel, record.dispatch, record.device)
            if key in indexed:
                ambiguous.add(key)
            indexed[key] = record
        return indexed, ambiguous
    old, dup_a = index(original)
    new, dup_b = index(changed)
    keys = (old.keys() & new.keys()) - dup_a - dup_b
    diffs = [{'metric': k[0], 'unit': k[1], 'kernel': k[2], 'dispatch': k[3],
              'device': k[4], 'baseline_identity': {
                  'process': old[k].process, 'context': old[k].context, 'stream': old[k].stream},
              'candidate_identity': {
                  'process': new[k].process, 'context': new[k].context, 'stream': new[k].stream},
              'baseline': old[k].value, 'candidate': new[k].value,
              'delta': new[k].value - old[k].value} for k in sorted(keys, key=str)]
    return {'capture': asdict(a), 'matched': len(diffs), 'changes': diffs,
            'baseline_only': len(old.keys() - new.keys()), 'candidate_only': len(new.keys() - old.keys()),
            'ambiguous_keys': len(dup_a | dup_b),
            'warnings': ['Counter deltas do not prove end-to-end speedup.',
                         'Dispatch index and kernel name must refer to the same workload; process/context/stream IDs are capture-local metadata.']}
