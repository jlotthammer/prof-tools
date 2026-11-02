"""Stateless optimization opportunity screening and diverse branch selection.

Estimates are conditional Amdahl-style illustrations, not inferred critical paths.
Experiment lineage belongs in Labcoat, not here.
"""

import json
import math
from pathlib import Path

FAMILIES = ("algebra", "dataflow", "scheduling", "memory", "library", "kernel", "distributed")
COST = {"low": 0, "medium": 1, "high": 2}


def opportunity_map(spec):
    if spec.get("schema_version") != 1:
        raise ValueError("opportunity schema_version must be 1")
    objective = spec.get("objective", {})
    if objective.get("metric_scope") != "application" or objective.get("direction") != "lower":
        raise ValueError("opportunity model requires a lower-is-better application-level duration metric")
    workloads = spec.get("workloads")
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("representative workload population required")
    ids = set()
    for w in workloads:
        if not isinstance(w.get("id"), str) or not w["id"] or w["id"] in ids:
            raise ValueError("workload IDs must be unique and nonempty")
        ids.add(w["id"])
        for key in ("weight", "baseline_ms"):
            n = w.get(key)
            if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or n <= 0:
                raise ValueError(f"workload {w['id']}: positive finite {key} required")
    weight_total = sum(w["weight"] for w in workloads)
    if abs(weight_total - 1) > 1e-6:
        raise ValueError("workload weights must sum to 1")
    screening = spec.get("family_screening")
    if not isinstance(screening, dict) or set(screening) != set(FAMILIES):
        raise ValueError("screen all seven optimization families with evidence or a reason for exclusion")
    for family, decision in screening.items():
        if not isinstance(decision, dict) or decision.get("status") not in ("considered", "ruled_out") or not decision.get("reason"):
            raise ValueError(f"family {family} requires status and reason")
    candidates = spec.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("at least one falsifiable candidate required")
    names = set()
    output = []
    for candidate in candidates:
        name = candidate.get("id")
        family = candidate.get("family")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("candidate IDs must be unique and nonempty")
        names.add(name)
        if family not in FAMILIES or screening[family]["status"] != "considered":
            raise ValueError(f"candidate {name} belongs to an excluded or unknown family")
        if not candidate.get("mechanism") or not candidate.get("falsification_test") or candidate.get("cost") not in COST:
            raise ValueError(f"candidate {name}: mechanism, falsification_test and low/medium/high cost required")
        predicted = 0.0
        unknown = []
        for w in workloads:
            entry = candidate.get("per_workload", {}).get(w["id"])
            if not isinstance(entry, dict) or entry.get("exposed_ms") is None or entry.get("speedup_ceiling") is None:
                unknown.append(w["id"])
                continue
            exposed, local = entry["exposed_ms"], entry["speedup_ceiling"]
            if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in (exposed, local)) or not 0 <= exposed <= w["baseline_ms"] or local < 1:
                raise ValueError(f"candidate {name}: impossible exposure/speedup values for {w['id']}")
            predicted += w["weight"] * exposed * (1 - 1 / local)
        current = {"id": name, "family": family, "mechanism": candidate["mechanism"],
                   "falsification_test": candidate["falsification_test"], "cost": candidate["cost"],
                   "memory_effect": candidate.get("memory_effect", "unknown"),
                   "unknown_exposure_workloads": unknown,
                   "conditional_weighted_max_savings_ms": round(predicted, 6) if not unknown else None,
                   "ceiling_is_verified": False}
        memory = objective.get("memory", {})
        if memory.get("mode", "secondary") not in ("secondary", "constraint"):
            raise ValueError("memory mode must be secondary or constraint")
        if memory.get("mode") == "constraint":
            if not isinstance(memory.get("limit_bytes"), int) or memory["limit_bytes"] <= 0:
                raise ValueError("memory constraint requires positive limit_bytes")
            projection = candidate.get("projected_peak_bytes")
            current["memory_feasibility"] = ("UNKNOWN" if projection is None else
                                             "PASS" if isinstance(projection, int) and 0 <= projection <= memory["limit_bytes"] else "FAIL")
        else:
            current["memory_feasibility"] = "SECONDARY"
        output.append(current)
    # Diversity first, then conditional estimate, with low effort as a tie-breaker.
    ranked = sorted(output, key=lambda c: (c["memory_feasibility"] == "FAIL",
        c["conditional_weighted_max_savings_ms"] is None,
        -(c["conditional_weighted_max_savings_ms"] or 0), COST[c["cost"]], c["id"]))
    selected = []
    seen = set()
    for c in ranked:
        if c["memory_feasibility"] != "FAIL" and c["family"] not in seen and len(selected) < 3:
            selected.append(c["id"])
            seen.add(c["family"])
    if len(selected) < min(2, len({x["family"] for x in ranked if x["memory_feasibility"] != "FAIL"})):
        raise ValueError("could not establish diverse branches")
    return {"schema_version": 1, "objective": objective, "family_screening": screening,
            "candidates": ranked, "initial_branches": selected,
            "next_action": "Run cheapest discriminating measurements in isolated Labcoat branches; do not merge these implementations directly.",
            "limitations": ["Conditional savings assume specified exposed serial time, unchanged workload and no compensating bottlenecks.",
                            "Unknown critical-path exposure is never replaced with cumulative kernel duration.",
                            "Memory is a secondary metric unless a specified hard capacity constraint is threatened.",
                            "Branch ranking is a heuristic for exploration, not a causal or statistical finding."]}


def analyze_opportunities(path):
    return opportunity_map(json.loads(Path(path).read_text()))
