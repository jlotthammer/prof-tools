"""Pure interval arithmetic. All intervals are half-open [start, end) in ns."""
from __future__ import annotations


def merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def duration(intervals):
    return sum(end - start for start, end in merge(intervals))


def intersection_duration(a, b):
    first, second = merge(a), merge(b)
    i = j = total = 0
    while i < len(first) and j < len(second):
        total += max(0, min(first[i][1], second[j][1]) - max(first[i][0], second[j][0]))
        if first[i][1] <= second[j][1]:
            i += 1
        else:
            j += 1
    return total


def subtract(a, b):
    """Return pieces of union(a) outside union(b)."""
    first, second = merge(a), merge(b)
    result = []
    j = 0
    for start, end in first:
        while j < len(second) and second[j][1] <= start:
            j += 1
        cursor = start
        k = j
        while k < len(second) and second[k][0] < end:
            lo, hi = second[k]
            if cursor < lo:
                result.append((cursor, min(lo, end)))
            cursor = max(cursor, min(hi, end))
            if cursor >= end:
                break
            k += 1
        if cursor < end:
            result.append((cursor, end))
    return result
