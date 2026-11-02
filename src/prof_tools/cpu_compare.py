"""Diff trusted deterministic Python function profiles and folded stack samples."""
from .cpu import cprofile_summary, collapsed_stacks_summary


def compare_pstats(baseline, candidate, top=30):
    if top < 1:
        raise ValueError('top must be positive')
    left = cprofile_summary(baseline, top=10**9, sort='self')
    right = cprofile_summary(candidate, top=10**9, sort='self')
    def keyed(data):
        return {(x['filename'], x['line'], x['function']): x for x in data['functions']}
    a, b = keyed(left), keyed(right)
    diffs = []
    for key in a.keys() | b.keys():
        x, y = a.get(key, {}), b.get(key, {})
        diffs.append({'location': f'{key[0]}:{key[1]}:{key[2]}',
                      'baseline_calls': x.get('total_calls', 0),
                      'candidate_calls': y.get('total_calls', 0),
                      'baseline_self_s': x.get('self_time_s', 0),
                      'candidate_self_s': y.get('self_time_s', 0),
                      'delta_self_s': y.get('self_time_s', 0) - x.get('self_time_s', 0),
                      'baseline_cumulative_s': x.get('cumulative_time_s', 0),
                      'candidate_cumulative_s': y.get('cumulative_time_s', 0)})
    diffs.sort(key=lambda x: (-abs(x['delta_self_s']), x['location']))
    return {'format': 'cProfile per-function diagnostic diff', 'changes': diffs[:top],
            'warnings': ['Instrumented profiles do not establish performance speedup.',
                         'Functions align by exact filename/line/name; source line moves and different paths break matching.',
                         'Cumulative times overlap in recursive call trees, and do not add to overall runtime.']}


def compare_stacks(baseline, candidate, top=30):
    if top < 1:
        raise ValueError('top must be positive')
    a = collapsed_stacks_summary(baseline, top=10**9)
    b = collapsed_stacks_summary(candidate, top=10**9)
    left = {x['frame']: x for x in a['frames']}
    right = {x['frame']: x for x in b['frames']}
    diffs = []
    for frame in left.keys() | right.keys():
        x, y = left.get(frame, {}), right.get(frame, {})
        diffs.append({'frame': frame, 'baseline_exclusive_fraction': x.get('exclusive_fraction', 0),
                      'candidate_exclusive_fraction': y.get('exclusive_fraction', 0),
                      'delta_exclusive_fraction': y.get('exclusive_fraction', 0) - x.get('exclusive_fraction', 0),
                      'baseline_inclusive_fraction': x.get('inclusive_fraction', 0),
                      'candidate_inclusive_fraction': y.get('inclusive_fraction', 0)})
    diffs.sort(key=lambda x: (-abs(x['delta_exclusive_fraction']), x['frame']))
    return {'format': 'folded stack sample fraction diagnostic diff', 'changes': diffs[:top],
            'sample_weight_baseline': a['total_leaf_weight'], 'sample_weight_candidate': b['total_leaf_weight'],
            'warnings': ['Sample fractions are not timings or speedups.',
                         'Both inputs must use the same sampling mode, profiling frequency, thread coverage and symbol conventions.',
                         'A frame fraction can increase simply because another frame became faster.']}
