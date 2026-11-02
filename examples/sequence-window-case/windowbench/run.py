"""Contract-compatible workload command for prof-tools suite and private evaluator."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import time

from .data import PUBLIC_CASES, build, identity, digest_input
from prof_tools.verify import tensor_digest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", choices=["baseline", "candidate", "oracle"], required=True)
    parser.add_argument("--case", default="short")
    parser.add_argument("--config-json", help="alternative case description (for a separately operated holdout)")
    parser.add_argument("--verify-output", help="write complete values for strict independent comparison")
    args = parser.parse_args(argv)
    if args.config_json:
        config = json.loads(Path(args.config_json).read_text())
    else:
        config = PUBLIC_CASES[args.case]
    dataset = build(config)
    workload = identity(args.case, config)
    input_id = digest_input(dataset)
    run = importlib.import_module("windowbench." + args.implementation).features
    started = time.perf_counter_ns()
    counts, hydrophobic, charge = run(dataset)
    if not (len(counts) == len(hydrophobic) == len(charge) == sum(map(len, (s[0] for s in dataset)))):
        raise ValueError("incomplete output")
    tensors = {
        "valid_count": {"dtype": "int64", "shape": [len(counts)], "data": counts},
        "hydrophobic_count": {"dtype": "int64", "shape": [len(hydrophobic)], "data": hydrophobic},
        "charge_sum": {"dtype": "int64", "shape": [len(charge)], "data": charge}}
    # Downstream consumption fingerprints every returned element.
    digest = tensor_digest(tensors)
    elapsed_ms = (time.perf_counter_ns() - started) / 1e6
    if args.verify_output:
        Path(args.verify_output).write_text(json.dumps({"workload": workload, "input_id": input_id, "tensors": tensors}))
    else:
        print("PROF_TOOLS_RESULT=" + json.dumps({"workload": workload,
             "metrics": {"step_ms": elapsed_ms}, "output_digest": digest, "input_id": input_id}))


if __name__ == "__main__":
    main()
