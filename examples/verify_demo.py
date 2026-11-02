#!/usr/bin/env python3
"""Tiny correctness fixture for the verifier; real projects supply their own tests."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--implementation', choices=['baseline', 'candidate'], required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    x = list(range(6))
    result = [sum(i * j for j in range(i + 1)) for i in x]
    if args.implementation == 'candidate':
        result = [i * i * (i + 1) // 2 for i in x]
    payload = {"workload": {"kind": "sum_weighted", "n": 6},
               "input_id": "deterministic-0..5", "tensors": {
                   "result": {"shape": [6], "dtype": "int64", "data": result}}}
    Path(args.out).write_text(json.dumps(payload))


if __name__ == '__main__':
    main()
