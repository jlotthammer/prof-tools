"""Validated event dependency DAG; never fabricate edges across GPU streams."""
from collections import defaultdict
import json
from pathlib import Path


def analyze_dependency_graph(source):
    doc = json.loads(Path(source).read_text())
    nodes = doc.get('nodes', [])
    edges = doc.get('edges', [])
    if not nodes:
        raise ValueError('dependency graph requires nodes')
    keys = [str(row['id']) for row in nodes]
    if len(keys) != len(set(keys)):
        raise ValueError('dependency graph contains duplicate IDs')
    indexed = {str(row['id']): row for row in nodes}
    for row in nodes:
        if row.get('duration_ns', -1) < 0:
            raise ValueError('dependency graph nodes require nonnegative duration_ns')
    neighbors = defaultdict(list)
    indegree = {key: 0 for key in indexed}
    for edge in edges:
        if not {'from', 'to', 'evidence'} <= edge.keys():
            raise ValueError('each dependency edge needs from, to, evidence')
        start, end = str(edge['from']), str(edge['to'])
        if start not in indexed or end not in indexed or not isinstance(edge['evidence'], str) or not edge['evidence'].strip():
            raise ValueError('edge references missing nodes or lacks explicit evidence')
        neighbors[start].append(end)
        indegree[end] += 1
    ready = sorted(key for key, degree in indegree.items() if degree == 0)
    longest = {key: (indexed[key]['duration_ns'], [key]) for key in indexed}
    visited = 0
    while ready:
        node = ready.pop(0)
        visited += 1
        for child in neighbors[node]:
            value, path = longest[node]
            option = (value + indexed[child]['duration_ns'], path + [child])
            if option[0] > longest[child][0]:
                longest[child] = option
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()
    if visited != len(indexed):
        raise ValueError('dependency graph contains a cycle')
    duration_ns, critical_nodes = max(longest.values(), key=lambda pair: pair[0])
    return {'source': str(Path(source).resolve()), 'nodes': len(indexed), 'edges': len(edges),
            'longest_weighted_path_ns': duration_ns, 'path': critical_nodes,
            'interpretation': 'longest sum of supplied node durations along supplied edges, not wall-clock iteration duration',
            'requirements': 'complete verified dependency edges and node weights required for causal interpretation'}
