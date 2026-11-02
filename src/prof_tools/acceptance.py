"""Stateless evidence gates for integrated optimizations; Labcoat owns decisions."""

import hashlib
import json
from pathlib import Path
import subprocess

REVIEW_CHECKS = (
    "semantic_preservation",
    "conceptual_economy",
    "coherent_public_api",
    "dataflow_and_ownership",
    "optimization_necessity",
    "simpler_alternatives",
    "scope_discipline",
    "exploration_residue_removed",
    "maintainable_tests",
    "diff_accountability",
)


def _json(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def assess(verification, benchmark):
    """Never conflate an unprofiled performance finding with correctness."""
    blockers = []
    checks = verification.get("checks")
    required = verification.get("required_categories")
    if (verification.get("status") != "PASS" or not isinstance(checks, list) or not checks
            or any(c.get("status") != "PASS" for c in checks)
            or not isinstance(required, list) or not required
            or not set(required) <= {c.get("category") for c in checks}):
        blockers.append("verification missing, incomplete or failed")
    peaks = benchmark.get("peak_memory_observed")
    limit = benchmark.get("memory_limit_bytes")
    memory_rescue = (isinstance(peaks, dict) and isinstance(limit, (int, float))
                     and peaks.get("baseline", 0) > limit >= peaks.get("candidate", float("inf"))
                     and benchmark.get("memory_constraint") == "PASS")
    if not benchmark.get("measured_without_profiler"):
        blockers.append("unprofiled process measurement not established")
    if benchmark.get("outcome") != "FASTER" and not memory_rescue:
        blockers.append("independent application improvement not established")
    if benchmark.get("metric_scope") != "application":
        blockers.append("benchmark is not an application-level measurement")
    if not verification.get("workload") or verification.get("workload") != benchmark.get("workload"):
        blockers.append("verification and performance workload identities differ")
    if benchmark.get("memory_constraint") == "FAIL":
        blockers.append("measured peak-memory limit exceeded")
    if benchmark.get("memory_constraint") == "NOT_EVALUATED" and benchmark.get("memory_limit_bytes") is not None:
        blockers.append("memory capacity constraint was not evaluated")
    return {"status": "ELIGIBLE_FOR_DESIGN_REVIEW" if not blockers else "BLOCKED",
            "blockers": blockers, "memory_constraint": benchmark.get("memory_constraint", "NOT_EVALUATED"),
            "objective_basis": "capacity_feasibility" if memory_rescue else "performance",
            "note": ("Capacity rescue can justify a slower application only under a real capacity requirement; "
                     "the performance tradeoff must be reviewed in Labcoat. " if memory_rescue else "") +
                    "Eligibility is not a KEEP decision; Labcoat owns experiment conclusions and integration."}


def _git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _git_blob(repo, commit, path):
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"],
                            capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _review_checks(design, changed_files, tracked_files):
    """Validate attestations and referenced paths; never pretend to judge design quality."""
    blockers = []
    checks = design.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    if set(checks) != set(REVIEW_CHECKS):
        blockers.append("design review must provide exactly the required semantic review dimensions")

    observed_evidence = set()
    for name in REVIEW_CHECKS:
        check = checks.get(name)
        if not isinstance(check, dict) or check.get("status") != "PASS":
            blockers.append(f"unsupported or failed design review: {name}")
            continue
        evidence = check.get("evidence")
        locations = check.get("locations")
        if not _nonempty(evidence):
            blockers.append(f"missing reasoning for design review: {name}")
        elif evidence.strip() in observed_evidence:
            blockers.append(f"reused boilerplate reasoning for design review: {name}")
        else:
            observed_evidence.add(evidence.strip())
        if not isinstance(locations, list) or not locations:
            blockers.append(f"design review must cite source files for: {name}")
        elif any(not isinstance(path, str) or path not in tracked_files for path in locations):
            blockers.append(f"design review cites missing or untracked source file for: {name}")

    accounted = design.get("changed_files")
    if not isinstance(accounted, list):
        accounted = []
    annotated = set()
    for entry in accounted:
        if not isinstance(entry, dict) or not _nonempty(entry.get("path")):
            blockers.append("changed_files entries require a file path")
            continue
        path = entry["path"]
        if path in annotated:
            blockers.append(f"changed file appears multiple times in review: {path}")
        annotated.add(path)
        if not _nonempty(entry.get("purpose")) or not _nonempty(entry.get("necessity")):
            blockers.append(f"changed file lacks purpose and necessity: {path}")
    if annotated != set(changed_files):
        blockers.append("design review must justify every file in the exact base-to-final diff")

    api = design.get("public_api")
    if not isinstance(api, dict) or any(not _nonempty(api.get(key)) for key in
                                        ("before", "after", "compatibility")):
        blockers.append("design review requires explicit before/after API and compatibility analysis")

    alternatives = design.get("simpler_alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        blockers.append("design review must evaluate a concrete simpler alternative (including the original design)")
    else:
        for alternative in alternatives:
            if (not isinstance(alternative, dict)
                    or not all(_nonempty(alternative.get(k)) for k in ("option", "tradeoff", "evidence"))
                    or alternative.get("disposition") not in ("adopted", "rejected", "deferred")):
                blockers.append("simpler alternative requires option, tradeoff, evidence and disposition")

    return blockers


def integration_review(repo, base, evaluation_path, design_path):
    """Check final-commit evidence and the structure of an independent semantic review.

    Review content is an attestation, not an algorithmic proof of architecture quality.
    """
    repo = Path(repo)
    head = _git(repo, "rev-parse", "HEAD")
    base_sha = _git(repo, "rev-parse", "--verify", f"{base}^{{commit}}")
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=normal"):
        raise ValueError("integration review requires a clean committed working tree")
    _git(repo, "merge-base", "--is-ancestor", base_sha, head)
    if _git(repo, "diff", "--check", f"{base_sha}..{head}"):
        raise ValueError("integration diff contains whitespace errors")
    files = _git(repo, "diff", "--no-renames", "--name-only", f"{base_sha}..{head}").splitlines()
    tracked_files = set(_git(repo, "ls-tree", "-r", "--name-only", base_sha).splitlines())
    tracked_files.update(_git(repo, "ls-tree", "-r", "--name-only", head).splitlines())

    design = _json(design_path)
    blockers = []
    if design.get("base_commit") != base_sha or design.get("final_commit") != head:
        blockers.append("design review does not identify the exact base and final commits")
    if not _nonempty(design.get("reviewer")) or not _nonempty(design.get("summary")):
        blockers.append("independent reviewer identity and architectural rationale are required")
    blockers.extend(_review_checks(design, files, tracked_files))

    evaluation = _json(evaluation_path)
    if evaluation.get("schema_version") != 1 or not isinstance(evaluation.get("verification"), dict) or not isinstance(evaluation.get("performance"), dict):
        raise ValueError("finalize requires a complete prof-tools evaluation artifact")
    verification = evaluation["verification"]
    benchmark = evaluation["performance"]
    evidence = assess(verification, benchmark)
    if evaluation.get("assessment") != evidence or evaluation.get("code_commit") != benchmark.get("code_commit"):
        blockers.append("evaluation summary disagrees with independently recomputed evidence")
    blockers.extend(evidence["blockers"])
    if verification.get("code_commit") != head or benchmark.get("code_commit") != head:
        blockers.append("verification and benchmark must both report the exact consolidated commit")

    # A source-controlled workload contract is part of the original experiment
    # definition. It cannot change during consolidation, even if the tests pass.
    frozen_contract = _git_blob(repo, base_sha, "perf/workload.json")
    if frozen_contract is not None:
        final_contract = _git_blob(repo, head, "perf/workload.json")
        if final_contract != frozen_contract:
            blockers.append("frozen workload contract changed since the original base")
        if evaluation.get("workload_contract_sha256") != hashlib.sha256(frozen_contract).hexdigest():
            blockers.append("final evaluation was not produced with the frozen workload contract")
    numstat = _git(repo, "diff", "--no-renames", "--numstat", f"{base_sha}..{head}")
    added, removed = 0, 0
    for line in numstat.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            added += int(cols[0]) if cols[0].isdigit() else 0
            removed += int(cols[1]) if cols[1].isdigit() else 0
    return {"status": "READY_FOR_LABCOAT_INTEGRATION" if not blockers else "BLOCKED",
            "blockers": blockers, "base_commit": base_sha, "final_commit": head,
            "diff": {"files": files, "files_changed": len(files), "lines_added": added, "lines_removed": removed},
            "performance_and_correctness": evidence,
            "design_review": {"reviewer": design.get("reviewer"), "summary": design.get("summary"),
                              "dimensions": list(REVIEW_CHECKS),
                              "changed_files_accounted_for": len(design.get("changed_files", [])) if isinstance(design.get("changed_files"), list) else 0},
            "limitations": ["Structural checks and reviewer attestations cannot mechanically prove elegant architecture or reviewer independence.",
                            "Evidence identifies the final commit but cannot prove subprocesses executed that exact code path.",
                            "Labcoat records the final KEEP, REVERT or PARTIAL decision and branch lineage."]}
