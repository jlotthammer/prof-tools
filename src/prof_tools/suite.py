"""Representative workload suite using existing verification and unprofiled runner.

Pure validation and aggregation are separated from the subprocess orchestration.
The suite is an evidence artifact, not an experiment tracker or Labcoat replacement.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import re
import shlex

from .benchmark import run_trials
from .verify import run_verification, tensor_digest, validate_spec as validate_verification_spec


def validate_suite(spec: dict) -> None:
    if spec.get("schema_version") != 1 or spec.get("direction", "lower") != "lower":
        raise ValueError("suite requires schema_version=1 and lower-is-better metric")
    if not isinstance(spec.get("metric"), str) or not spec["metric"]:
        raise ValueError("suite requires a metric")
    cases = spec.get("workloads")
    if not isinstance(cases, list) or not cases:
        raise ValueError("suite requires workloads")
    ids = set()
    weight = 0.0
    for item in cases:
        name = item.get("id") if isinstance(item, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) or name in ids:
            raise ValueError("workload ids must be unique and path safe")
        ids.add(name)
        if not isinstance(item.get("workload"), dict) or not item["workload"]:
            raise ValueError(f"{name}: explicit nonempty workload identity required")
        w = item.get("weight")
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or w <= 0:
            raise ValueError(f"{name}: positive finite weight required")
        weight += w
        for key in ("baseline", "candidate"):
            cmd = item.get(key)
            if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) and x for x in cmd):
                raise ValueError(f"{name}: {key} requires an argv list")
        verification = item.get("verification")
        if not isinstance(verification, dict):
            raise ValueError(f"{name}: independent verification commands required")
        for key in ("reference", "baseline", "candidate"):
            argv = verification.get(key)
            if (not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv)
                    or not any("{output}" in part for part in argv)):
                raise ValueError(f"{name}: verification.{key} requires argv with {{output}}")
        for key in ("atol", "rtol"):
            value = verification.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name}: explicit finite nonnegative verification.{key} required")
        extra_checks = item.get("checks", [])
        required_categories = item.get("required_categories", ["forward"])
        if not isinstance(extra_checks, list) or not isinstance(required_categories, list) or "forward" not in required_categories:
            raise ValueError(f"{name}: checks must be a list and required_categories must include forward")
        if extra_checks:
            validate_verification_spec({"schema_version": 1, "workload": item["workload"],
                "required_categories": required_categories,
                "cases": [{"id": "baseline_output", "type": "compare", "category": "forward",
                           "reference": verification["reference"], "candidate": verification["baseline"],
                           "atol": verification["atol"], "rtol": verification["rtol"]},
                          *extra_checks]})
        elif required_categories != ["forward"]:
            raise ValueError(f"{name}: additional required verification categories need corresponding checks")
        if item["baseline"] == item["candidate"]:
            raise ValueError(f"{name}: baseline and candidate commands identical")
    if abs(weight - 1.0) > 1e-6:
        raise ValueError("workload weights must sum to one")
    if spec.get("pairs", 6) < 2 or spec.get("warmup", 1) < 0:
        raise ValueError("pairs >= 2 and warmup >= 0 required")
    if spec.get("memory_limit_bytes") is not None and (not isinstance(spec.get("memory_limit_bytes"), int) or spec["memory_limit_bytes"] <= 0 or not spec.get("memory_metric")):
        raise ValueError("a binding memory limit requires a positive integer and a memory metric")
    if spec.get("max_case_regression", 0.05) < 0:
        raise ValueError("max_case_regression must be nonnegative")


def summarize_suite(rows: list[dict], *, max_regression: float, seed: int = 2026) -> dict:
    """Resample paired trial observations within each workload; aggregate weighted time."""
    if not rows:
        raise ValueError("empty suite")
    for r in rows:
        if len(r["pairs"]) < 2 or r["weight"] <= 0:
            raise ValueError("each workload requires >= 2 paired measurements")
    def aggregate(choices):
        return (sum(r["weight"] * sum(p["baseline"] for p in choices[i]) / len(choices[i]) for i, r in enumerate(rows)),
                sum(r["weight"] * sum(p["candidate"] for p in choices[i]) / len(choices[i]) for i, r in enumerate(rows)))
    observed = [[dict(p) for p in r["pairs"]] for r in rows]
    base, cand = aggregate(observed)
    rng = random.Random(seed)
    boots = []
    for _ in range(2000):
        resampled = [[rng.choice(r["pairs"]) for _ in r["pairs"]] for r in rows]
        b, c = aggregate(resampled)
        boots.append(b / c)
    boots.sort()
    per_case = []
    for row in rows:
        b = sum(p["baseline"] for p in row["pairs"]) / len(row["pairs"])
        c = sum(p["candidate"] for p in row["pairs"]) / len(row["pairs"])
        per_case.append({"id": row["id"], "weight": row["weight"], "baseline_ms": b,
                         "candidate_ms": c, "speedup": b / c,
                         "regression_fraction": max(0.0, c / b - 1)})
    lo, hi = boots[49], boots[1949]
    blockers = []
    if any(r.get("verification") != "PASS" for r in rows):
        blockers.append("not every workload passed independent correctness verification")
    if lo <= 1:
        blockers.append("weighted application speedup not established by paired-bootstrap interval")
    if any(r["regression_fraction"] > max_regression for r in per_case):
        blockers.append("per-workload regression exceeds required guardrail")
    return {"status": "ELIGIBLE_FOR_REVIEW" if not blockers else "BLOCKED",
            "blockers": blockers, "weighted_baseline_ms": base, "weighted_candidate_ms": cand,
            "weighted_speedup": base / cand, "weighted_speedup_ci_95": [lo, hi],
            "max_case_regression": max_regression, "per_case": per_case,
            "limitations": ["Bootstrap captures process-level sampling, not hardware or dataset uncertainty.",
                            "The correctness corpus and workload weights are supplied by the project.",
                            "This report is not a Labcoat decision or a proof of algorithmic equivalence."]}


def run_suite(spec_path: str, outdir: str) -> dict:
    spec = json.loads(Path(spec_path).read_text())
    validate_suite(spec)
    out = Path(outdir).resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"suite output directory not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "suite_spec.json").write_text(json.dumps(spec, indent=2))
    workload_definition = {"metric": spec["metric"], "direction": spec.get("direction", "lower"),
                           "cases": [{"id": w["id"], "weight": w["weight"], "workload": w["workload"]} for w in spec["workloads"]]}
    suite_id = hashlib.sha256(json.dumps(workload_definition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    suite_identity = {"suite_id": suite_id, "case_count": len(spec["workloads"])}
    rows = []
    commits = set()
    for item in spec["workloads"]:
        workdir = out / item["id"]
        workdir.mkdir()
        v_spec = {"schema_version": 1, "workload": item["workload"],
                  "required_categories": item.get("required_categories", ["forward"]),
                  "cases": [{"id": f"{label}_equivalence", "category": "forward", "type": "compare",
                             "reference": item["verification"]["reference"], "candidate": item["verification"][label],
                             "atol": item["verification"]["atol"], "rtol": item["verification"]["rtol"]}
                            for label in ("baseline", "candidate")] + item.get("checks", [])}
        v_path = workdir / "verification_spec.json"
        v_path.write_text(json.dumps(v_spec, indent=2))
        verification = run_verification(v_path, workdir / "verification", timeout=spec.get("timeout", 600))
        if verification.get("code_commit"):
            commits.add(verification["code_commit"])
        row = {"id": item["id"], "weight": item["weight"], "verification": verification["status"],
               "workload": item["workload"], "verification_report": str(workdir / "verification" / "verification.json")}
        if verification["status"] == "PASS":
            expected = {}
            for label in ("baseline", "candidate"):
                verified = json.loads((workdir / "verification" / f"{label}_equivalence" / "candidate.json").read_text())
                expected[label] = {"digest": tensor_digest(verified["tensors"]),
                                   "input_id": verified["input_id"]}
            b = run_trials(shlex.join(item["baseline"]), shlex.join(item["candidate"]),
                           spec["metric"], workdir / "benchmark", pairs=spec.get("pairs", 6),
                           warmup=spec.get("warmup", 1), seed=spec.get("seed", 2026),
                           timeout=spec.get("timeout", 600), metric_scope="application",
                           memory_metric=spec.get("memory_metric"), memory_limit_bytes=spec.get("memory_limit_bytes"))
            if b.get("code_commit"):
                commits.add(b["code_commit"])
            if b.get("code_commit") != verification.get("code_commit"):
                raise ValueError(f"{item['id']}: verification and benchmarking executed at different Git commits")
            if b["workload"] != item["workload"]:
                raise ValueError(f"{item['id']}: benchmark workload differs from verification")
            trials = json.loads((workdir / "benchmark" / "trials.json").read_text())
            for trial in trials:
                for label in ("baseline", "candidate"):
                    payload = trial[label]["payload"]
                    if (payload.get("output_digest") != expected[label]["digest"]
                            or payload.get("input_id") != expected[label]["input_id"]):
                        raise ValueError(f"{item['id']}: {label} timed output differs from independently verified output")
            if b["memory_constraint"] == "FAIL":
                row["verification"] = "FAIL"
                row["memory_error"] = "candidate exceeded binding peak-memory limit"
            row["pairs"] = [{"baseline": p["baseline"]["value"], "candidate": p["candidate"]["value"]}
                            for p in trials]
            row["benchmark_report"] = str(workdir / "benchmark" / "comparison.json")
        rows.append(row)
        (out / "progress.json").write_text(json.dumps(rows, indent=2))
    if len(commits) > 1:
        raise ValueError("suite cases executed at different Git revisions")
    code_commit = next(iter(commits)) if commits else None
    all_correct = all(r["verification"] == "PASS" for r in rows)
    required_categories = sorted({cat for item in spec["workloads"]
                                  for cat in item.get("required_categories", ["forward"])})
    verification_report = {"schema_version": 1, "status": "PASS" if all_correct else "FAIL",
         "required_categories": required_categories, "workload": suite_identity, "code_commit": code_commit,
         "checks": [{"id": r["id"] + ":" + cat, "category": cat, "status": r["verification"],
                     "evidence": r["verification_report"]}
                    for r, item in zip(rows, spec["workloads"])
                    for cat in item.get("required_categories", ["forward"])]}
    (out / "suite_verification.json").write_text(json.dumps(verification_report, indent=2))
    if not all_correct:
        result = {"status": "BLOCKED", "blockers": ["one or more workloads failed correctness"],
                  "workloads": rows}
    else:
        result = summarize_suite(rows, max_regression=spec.get("max_case_regression", 0.05), seed=spec.get("seed", 2026))
        result["workloads"] = [{k: v for k, v in r.items() if k != "pairs"} for r in rows]
    result.update({"workload": suite_identity, "code_commit": code_commit,
                   "metric_scope": "application", "measured_without_profiler": True,
                   "outcome": "FASTER" if result["status"] == "ELIGIBLE_FOR_REVIEW" else "INCONCLUSIVE",
                   "metric": spec["metric"], "direction": "lower",
                   "memory_limit_bytes": spec.get("memory_limit_bytes"),
                   "memory_constraint": ("PASS" if all_correct and spec.get("memory_limit_bytes") is not None
                                         else "NOT_CONSTRAINED" if spec.get("memory_limit_bytes") is None
                                         else "FAIL"),
                   "verification_report": str(out / "suite_verification.json")})
    (out / "suite_report.json").write_text(json.dumps(result, indent=2))
    return result
