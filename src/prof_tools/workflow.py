"""High-level evaluation workflow over stateless correctness and measurement primitives.

Labcoat owns durable experiments; this module only produces evidence.
"""
from pathlib import Path
import hashlib
import json
from .suite import run_suite
from .acceptance import assess, integration_review


def evaluate(spec: str, outdir: str) -> dict:
    performance = run_suite(spec, outdir)
    verification = json.loads((Path(outdir) / "suite_verification.json").read_text())
    assessment = assess(verification, performance)
    result = {"schema_version": 1,
              "status": assessment["status"],
              "workload_contract_sha256": hashlib.sha256(Path(spec).read_bytes()).hexdigest(),
              "code_commit": performance.get("code_commit"),
              "verification": verification,
              "performance": performance,
              "assessment": assessment,
              "workload": performance.get("workload"),
              "note": "Evidence only. Labcoat owns experiment history and repository decisions."}
    (Path(outdir) / "evaluation.json").write_text(json.dumps(result, indent=2))
    return result


def finalize(repo: str, base: str, evaluation: str, design_review: str) -> dict:
    return integration_review(repo, base, evaluation, design_review)
