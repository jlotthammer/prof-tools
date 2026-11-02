"""Conservative dependency evidence extracted from Nsight Systems / ROCm traces.

Inter-stream GPU execution edges cannot generally be inferred from order or
correlation IDs alone. Report precisely which relationships are observed.
"""
from collections import defaultdict

from .trace import columns, tables, identify
from .trace_diagnostics import database, _events


def _sync_evidence(conn):
    names = tables(conn)
    required = {'CUPTI_ACTIVITY_KIND_CUDA_EVENT', 'CUPTI_ACTIVITY_KIND_SYNCHRONIZATION'}
    if not required <= names:
        return {'matched_event_sync_ids': 0, 'records': [],
                'status': 'unavailable: CUDA event and synchronization activity tables not both present'}
    ec = columns(conn, 'CUPTI_ACTIVITY_KIND_CUDA_EVENT')
    sc = columns(conn, 'CUPTI_ACTIVITY_KIND_SYNCHRONIZATION')
    if not {'eventSyncId', 'streamId'} <= ec or not {'eventSyncId', 'streamId'} <= sc:
        return {'matched_event_sync_ids': 0, 'records': [],
                'status': 'unavailable: eventSyncId/streamId missing in one or both tables'}
    event_rows = defaultdict(list)
    for sync, stream in conn.execute('SELECT eventSyncId, streamId FROM CUPTI_ACTIVITY_KIND_CUDA_EVENT WHERE eventSyncId IS NOT NULL'):
        event_rows[str(sync)].append(str(stream))
    observed = []
    for sync, waiting in conn.execute('SELECT eventSyncId, streamId FROM CUPTI_ACTIVITY_KIND_SYNCHRONIZATION WHERE eventSyncId IS NOT NULL'):
        matching = event_rows.get(str(sync), [])
        if len(matching) == 1:
            observed.append({'event_sync_id': str(sync), 'recording_stream': matching[0],
                             'waiting_stream': str(waiting)})
    return {'matched_event_sync_ids': len(observed), 'records': observed[:100],
            'status': 'observed CUDA event record/wait association only; GPU producer completion edge not reconstructed'}


def analyze_gpu_dependencies(path):
    with database(path) as conn:
        vendor = identify(conn)
        events, missing = _events(conn, vendor)
        evidence = _sync_evidence(conn) if vendor == 'nvidia' else {
            'matched_event_sync_ids': 0, 'records': [],
            'status': 'no ROCm event dependency adapter for this schema'}
    streams = defaultdict(list)
    absent_stream = 0
    for event in events:
        if event.kind not in ('kernel', 'copy', 'memset'):
            continue
        if event.stream is None:
            absent_stream += 1
            continue
        streams[(event.pid, event.device, event.stream)].append(event)
    chain_reports = []
    inversions = 0
    for (pid, device, stream), items in sorted(streams.items(), key=lambda x: str(x[0])):
        sorted_items = sorted(items, key=lambda x: (x.start, x.end))
        overlap_pairs = sum(1 for a, b in zip(sorted_items, sorted_items[1:]) if a.end > b.start)
        inversions += overlap_pairs
        chain_reports.append({'pid': pid, 'device': device, 'stream': stream,
                              'recorded_activities': len(sorted_items),
                              'sum_duration_ns': sum(e.end - e.start for e in sorted_items),
                              'first_start_ns': sorted_items[0].start,
                              'last_end_ns': max(e.end for e in sorted_items),
                              'overlapping_adjacent_intervals': overlap_pairs})
    return {'source': str(path), 'vendor': vendor, 'per_stream_observations': chain_reports,
            'events_without_stream': absent_stream, 'stream_overlaps': inversions,
            'cuda_event_dependencies': evidence, 'missing_domains': missing,
            'warnings': [
                'Per-stream activity ordering is observed, not an inferred full inter-stream dependency DAG.',
                'Events/synchronization IDs indicate runtime relationships; recording GPU completion requires further evidence.',
                'No global critical path or exposed communication time is claimed without a complete verified DAG.']}
