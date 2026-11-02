#!/usr/bin/env python3
"""Portable CPU measurement adapter. Examples are illustrative, not optimized code.

The two variants must compute precisely the same integer checksum. The process
warms its own workload, times the steady-state region with a wall timer and
emits the exact workload identity for the shared A/B runner.
"""
import argparse
import json
import operator
import time


def compute_reference(values):
    out = 0
    for x in values:
        out += x * x
    return out


def compute_candidate(values):
    return sum(map(operator.mul, values, values))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant", choices=["reference", "candidate"], required=True)
    p.add_argument("--elements", type=int, default=100_000)
    p.add_argument("--steps", type=int, default=12)
    p.add_argument("--warmup", type=int, default=4)
    args = p.parse_args()
    if min(args.elements, args.steps) < 1 or args.warmup < 0:
        p.error("elements and steps must be positive; warmup must be nonnegative")
    values = list(range(args.elements))
    fn = compute_reference if args.variant == "reference" else compute_candidate
    expected = args.elements * (args.elements - 1) * (2 * args.elements - 1) // 6
    for _ in range(args.warmup):
        if fn(values) != expected:
            raise RuntimeError("checksum mismatch during warmup")
    t_wall = time.perf_counter_ns()
    t_cpu = time.process_time_ns()
    for _ in range(args.steps):
        checksum = fn(values)
        if checksum != expected:
            raise RuntimeError("checksum mismatch")
    cpu_ns = time.process_time_ns() - t_cpu
    wall_ns = time.perf_counter_ns() - t_wall
    print("PROF_TOOLS_RESULT=" + json.dumps({
        "metrics": {"iteration_ms": (wall_ns / args.steps) / 1e6,
                    "cpu_process_ms": (cpu_ns / args.steps) / 1e6},
        "workload": {"kind": "integer_sum_squares", "elements": args.elements,
                     "steps": args.steps, "checksum": expected},
    }))


if __name__ == "__main__":
    main()
