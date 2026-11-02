"""Controlled independent-process A/B benchmarking.

Contract: each child emits one PROF_TOOLS_RESULT=<JSON> with positive numerical
metrics and optional workload identity. Its own benchmark must warm up and
measure the correct end-to-end work; this runner only provides outer replication.
"""
import json
import math
import os
from pathlib import Path
import random
import shlex
import subprocess
import time
from .environment import inventory
from .stats import comparison

PREFIX = "PROF_TOOLS_RESULT="


def parse_result(output, metric):
    lines = [line[len(PREFIX):] for line in output.splitlines() if line.startswith(PREFIX)]
    if len(lines) != 1:
        raise ValueError(f"expected exactly one PROF_TOOLS_RESULT= line, saw {len(lines)}")
    obj = json.loads(lines[0])
    value = obj["metrics"][metric]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{metric} must be finite and positive")
    if not isinstance(obj.get("workload"), dict) or not obj["workload"]:
        raise ValueError("nonempty workload identity is required in every result")
    return float(value), obj


def invoke(command, metric, directory, name, index, timeout, env):
    args = shlex.split(command)
    if not args:
        raise ValueError("benchmark command cannot be empty")
    if Path(args[0]).name in {"nsys", "ncu", "rocprofv3", "rocprof-compute", "rocprof-sys-sample",
                                "perf", "py-spy", "scalene", "memray", "pyinstrument",
                                "samply", "valgrind", "heaptrack", "flamegraph", "cargo-flamegraph"}:
        raise ValueError("benchmark must be unprofiled")
    if "-m" in args:
        modules = [args[i + 1] for i, token in enumerate(args[:-1]) if token == "-m"]
        if any(m in {"cProfile", "profile", "scalene", "memray", "pyinstrument", "profiling.sampling"}
               for m in modules):
            raise ValueError("benchmark must not run Python profiler modules")
    t0 = time.perf_counter()
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{name} run {index} timed out after {timeout}s") from exc
    log = directory / f"{name}_{index:03d}.log"
    log.write_text(f"argv: {args!r}\nexit_code: {cp.returncode}\n\nSTDOUT\n{cp.stdout}\nSTDERR\n{cp.stderr}")
    if cp.returncode != 0:
        raise RuntimeError(f"{name} run {index} exit {cp.returncode}; see {log}")
    value, payload = parse_result(cp.stdout, metric)
    return {"value": value, "runtime_s": time.perf_counter() - t0, "log": log.name, "payload": payload}


def run_trials(baseline, candidate, metric, outdir, pairs=6, warmup=1,
               direction="lower", min_gain=0.0, seed=2026, timeout=3600,
               metric_scope="application", memory_metric=None, memory_limit_bytes=None):
    if pairs < 2 or warmup < 0 or min_gain < 0:
        raise ValueError("pairs >=2, warmup >=0, min_gain >=0 required")
    if metric_scope not in {"application", "kernel"}:
        raise ValueError("metric_scope must be application or kernel")
    if memory_limit_bytes is not None and (memory_metric is None or memory_limit_bytes <= 0):
        raise ValueError("memory limit requires a positive value and memory metric")
    out = Path(outdir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    metadata = {"baseline_command": baseline, "candidate_command": candidate,
                "metric": metric, "direction": direction, "min_gain": min_gain,
                "seed": seed, "warmup": warmup, "metric_scope": metric_scope,
                "memory_metric": memory_metric, "memory_limit_bytes": memory_limit_bytes,
                "environment": inventory()}
    (out / "manifest.json").write_text(json.dumps(metadata, indent=2))
    trials = []
    rng = random.Random(seed)
    identity = None
    def execute(label, index):
        nonlocal identity
        command = baseline if label == "baseline" else candidate
        result = invoke(command, metric, out, label, index, timeout, env)
        payload_identity = result["payload"]["workload"]
        if identity is None:
            identity = payload_identity
        elif identity != payload_identity:
            raise ValueError(f"workload identity differs in {label} run {index}; see {result['log']}")
        if memory_metric:
            mem = result["payload"].get("metrics", {}).get(memory_metric)
            if isinstance(mem, bool) or not isinstance(mem, (int, float)) or not math.isfinite(mem) or mem < 0:
                raise ValueError(f"missing/invalid memory metric {memory_metric} in {label} run {index}")
        return result
    for i in range(warmup):
        for label in ("baseline", "candidate"):
            execute(label, i)
    for i in range(pairs):
        order = ["baseline", "candidate"]
        rng.shuffle(order)
        pair = {"index": i, "order": order}
        for label in order:
            pair[label] = execute(label, i + warmup)
        trials.append(pair)
        (out / "trials.json").write_text(json.dumps(trials, indent=2))
    values_b = [t["baseline"]["value"] for t in trials]
    values_c = [t["candidate"]["value"] for t in trials]
    cmp = comparison(values_b, values_c, direction, seed=seed)
    lo, hi = cmp["speedup_ci"]
    outcome = "FASTER" if lo > 1 + min_gain else "SLOWER" if hi < 1 else "INCONCLUSIVE"
    peaks = None
    memory_constraint = "NOT_EVALUATED"
    if memory_metric:
        peaks = {label: max(float(t[label]["payload"]["metrics"][memory_metric]) for t in trials)
                 for label in ("baseline", "candidate")}
        memory_constraint = ("NOT_CONSTRAINED" if memory_limit_bytes is None else
                             "PASS" if peaks["candidate"] <= memory_limit_bytes else "FAIL")
    result = {"outcome": outcome, "metric": metric, "direction": direction,
              "metric_scope": metric_scope, "memory_metric": memory_metric,
              "peak_memory_observed": peaks, "memory_limit_bytes": memory_limit_bytes,
              "memory_constraint": memory_constraint,
              "code_commit": (metadata["environment"]["git"].get("output", "").strip()
                              if metadata["environment"]["git"].get("exit_code") == 0 else None),
              "min_gain": min_gain, "workload": identity, "statistics": cmp,
              "correctness": "NOT_EVALUATED", "measured_without_profiler": True}
    (out / "comparison.json").write_text(json.dumps(result, indent=2))
    (out / "report.md").write_text(
        f"# Paired benchmark\n\nOutcome (performance only): **{outcome}**. Correctness not evaluated.\n\n"
        f"Metric: `{metric}` ({direction} is better); {pairs} matched pairs.\n\n"
        f"Geometric speedup: **{cmp['geometric_speedup']:.4f}×**; "
        f"{cmp['confidence']:.0%} paired-bootstrap CI: "
        f"**[{lo:.4f}, {hi:.4f}]×**. Minimum prespecified gain: {min_gain:.1%}.\n\n"
        f"Median baseline: {cmp['baseline_median']:.6g}; candidate: {cmp['candidate_median']:.6g}.\n\n"
        f"Raw logs: `trials.json`, `*_NNN.log`. Machine/environment: `manifest.json`.\n\n"
        "The CI describes repeated processes on this machine and workload, not portability across hosts or workload configurations. "
        "Final acceptance additionally requires independently verified correctness.\n")
    return result
