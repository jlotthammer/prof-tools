"""Paired, process-level comparisons; no profiler-derived performance decisions."""
import math
import random
import statistics


def comparison(baselines, candidates, direction="lower", confidence=0.95, draws=10000, seed=101):
    if direction not in ("lower", "higher"):
        raise ValueError("direction must be lower or higher")
    if len(baselines) != len(candidates) or len(baselines) < 2:
        raise ValueError("at least two matched pairs are required")
    if any(not math.isfinite(x) or x <= 0 for x in (*baselines, *candidates)):
        raise ValueError("all metrics must be finite and positive")
    ratios = [(b / c if direction == "lower" else c / b) for b, c in zip(baselines, candidates)]
    logs = [math.log(x) for x in ratios]
    rng = random.Random(seed)
    boot = []
    for _ in range(draws):
        boot.append(math.exp(sum(logs[rng.randrange(len(logs))] for _ in logs) / len(logs)))
    boot.sort()
    alpha = (1 - confidence) / 2
    lo = boot[int(alpha * (draws - 1))]
    hi = boot[int((1 - alpha) * (draws - 1))]
    return {
        "pairs": len(logs), "confidence": confidence,
        "baseline_median": statistics.median(baselines),
        "candidate_median": statistics.median(candidates),
        "geometric_speedup": math.exp(statistics.mean(logs)),
        "speedup_ci": [lo, hi],
        "pair_speedups": ratios,
        "baseline_cv": statistics.stdev(baselines) / statistics.mean(baselines),
        "candidate_cv": statistics.stdev(candidates) / statistics.mean(candidates),
    }
