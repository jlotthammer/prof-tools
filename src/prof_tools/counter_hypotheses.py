"""Conservative suggestions from *exact* vendor metric identities.

No cross-architecture metric translation: counters with unmatched names are
still retained as typed evidence for the architecture-specific skill.
"""
from collections import defaultdict


def nvidia_saturation_hypotheses(capture, counters):
    if capture.vendor != 'nvidia':
        return []
    grouped = defaultdict(dict)
    for row in counters:
        if row.unit != '%':
            continue
        key = (row.device, row.process, row.context, row.stream, row.kernel, row.dispatch)
        grouped[key][row.metric] = row.value
    observations = []
    for (device, process, context, stream, kernel, dispatch), metrics in grouped.items():
        sm = metrics.get('sm__throughput.avg.pct_of_peak_sustained_elapsed')
        dram = metrics.get('dram__throughput.avg.pct_of_peak_sustained_elapsed')
        if sm is None or dram is None:
            continue
        if not (0 <= sm <= 100 and 0 <= dram <= 100):
            continue
        if dram >= 75 and sm <= 40:
            observations.append({'code': 'HIGH_DRAM_LOW_SM_THROUGHPUT',
                                 'device': device, 'process': process, 'context': context, 'stream': stream,
                                 'kernel': kernel, 'dispatch': dispatch,
                                 'dram_percent': dram, 'sm_percent': sm,
                                 'interpretation': 'high observed DRAM throughput with comparatively low SM throughput',
                                 'next_check': 'confirm bytes moved, cache behavior, roofline AI, and replay conditions; test traffic reduction'})
        elif sm >= 75 and dram <= 40:
            observations.append({'code': 'HIGH_SM_LOW_DRAM_THROUGHPUT',
                                 'device': device, 'process': process, 'context': context, 'stream': stream,
                                 'kernel': kernel, 'dispatch': dispatch,
                                 'dram_percent': dram, 'sm_percent': sm,
                                 'interpretation': 'high observed SM throughput with comparatively low DRAM throughput',
                                 'next_check': 'confirm executed precision, tensor-core instruction mix and issue bottlenecks'})
    return observations
