"""Stateless correctness comparisons and subprocess-backed verification.

This checks explicitly supplied contracts; it does not prove arbitrary programs equivalent.
Commands are trusted project code, run without a shell, with isolated output paths.
"""

import hashlib
import json
import math
import re
from pathlib import Path
import subprocess


def tensor_digest(tensors):
    """Stable fingerprint of complete typed output tensors, independent of dict order.

    This detects accidental differences between verified and timed outputs; it
    is not proof against adversarial candidates that deliberately spoof hashes.
    """
    if not isinstance(tensors, dict) or not tensors:
        raise ValueError("nonempty typed tensor map required")
    encoded = json.dumps(tensors, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


CATEGORIES = frozenset({"execution", "forward", "gradient", "state", "invariant", "boundary", "distribution", "concurrency", "distributed", "safety"})


def _object(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def validate_spec(spec):
    if spec.get("schema_version") != 1:
        raise ValueError("verification schema_version must be 1")
    if not isinstance(spec.get("workload"), dict) or not spec["workload"]:
        raise ValueError("verification requires a nonempty workload identity")
    required = spec.get("required_categories")
    if not isinstance(required, list) or not required or len(set(required)) != len(required) or set(required) - CATEGORIES:
        raise ValueError("required_categories must be a nonempty list of unique supported categories")
    cases = spec.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("verification must contain cases")
    names = set()
    for case in cases:
        name = case.get("id")
        if not isinstance(name, str) or not name or name in names or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in {".", ".."}:
            raise ValueError("case IDs must be unique, nonempty path-safe strings")
        names.add(name)
        if case.get("category") not in CATEGORIES:
            raise ValueError(f"case {name}: invalid category")
        if case.get("type") not in ("compare", "test"):
            raise ValueError(f"case {name}: expected type compare or test")
        keys = ("reference", "candidate") if case["type"] == "compare" else ("command",)
        for key in keys:
            command = case.get(key)
            if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
                raise ValueError(f"case {name}: {key} must be an argv list")
        if case["type"] == "compare":
            if not all(any("{output}" in x for x in case[key]) for key in ("reference", "candidate")):
                raise ValueError(f"case {name}: output placeholder is required")
            for key in ("atol", "rtol"):
                value = case.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"case {name}: explicit nonnegative finite {key} required")
    if set(required) - {c["category"] for c in cases}:
        raise ValueError("each required category must have at least one case")


def compare_tensors(reference, candidate, *, atol, rtol):
    """Compare JSON tensor envelopes; shape, dtype, keys and input identity are strict.

    Payload: {workload:{...}, input_id:'...', tensors:{name:{dtype,shape,data}}}.
    Scalars use shape []; data is a flat list. Nonfinite values fail closed.
    """
    if reference.get("workload") != candidate.get("workload"):
        raise ValueError("reference/candidate workloads differ")
    if not isinstance(reference.get("input_id"), str) or not reference["input_id"] or reference["input_id"] != candidate.get("input_id"):
        raise ValueError("missing or mismatched input_id")
    a = reference.get("tensors")
    b = candidate.get("tensors")
    if not isinstance(a, dict) or not a or not isinstance(b, dict) or set(a) != set(b):
        raise ValueError("tensor keys differ or are empty")
    summaries = {}
    overall = True
    for name in sorted(a):
        t, u = a[name], b[name]
        if t.get("dtype") != u.get("dtype") or not isinstance(t.get("dtype"), str):
            raise ValueError(f"{name}: dtype differs")
        shape = t.get("shape")
        if shape != u.get("shape") or not isinstance(shape, list) or any(not isinstance(d, int) or isinstance(d, bool) or d < 0 for d in shape):
            raise ValueError(f"{name}: invalid or different shapes")
        length = math.prod(shape)
        aa, bb = t.get("data"), u.get("data")
        if not isinstance(aa, list) or not isinstance(bb, list) or len(aa) != length or len(bb) != length:
            raise ValueError(f"{name}: flattened data length differs from shape")
        bad = 0
        max_abs = 0.0
        max_rel = 0.0
        for x, y in zip(aa, bb):
            if (isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float))
                    or not isinstance(y, (int, float)) or not math.isfinite(x) or not math.isfinite(y)):
                bad += 1
                continue
            diff = abs(x - y)
            max_abs = max(max_abs, diff)
            max_rel = max(max_rel, diff / max(abs(x), 1e-300))
            if diff > atol + rtol * abs(x):
                bad += 1
        summaries[name] = {"elements": length, "mismatches": bad, "max_abs_error": max_abs, "max_rel_error": max_rel}
        overall = overall and bad == 0
    return {"status": "PASS" if overall else "FAIL", "tensors": summaries}


def _execute(argv, output, timeout, log):
    command = [part.replace("{output}", str(output)) for part in argv]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.write_text(f"command: {command!r}\nFAILED ({exc})\n")
        return False
    log.write_text(f"command: {command!r}\nexit_code: {completed.returncode}\n\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}")
    return completed.returncode == 0


def run_verification(spec_path, outdir, timeout=600):
    spec = _object(spec_path)
    validate_spec(spec)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    out = Path(outdir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, indent=2))
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    code_commit = revision.stdout.strip() if revision.returncode == 0 else None
    checks = []
    for case in spec["cases"]:
        folder = out / case["id"]
        folder.mkdir()
        result = {"id": case["id"], "category": case["category"], "type": case["type"], "status": "FAIL"}
        if case["type"] == "test":
            if _execute(case["command"], folder / "unused.json", timeout, folder / "test.log"):
                result["status"] = "PASS"
            result["evidence"] = str((folder / "test.log").relative_to(out))
        else:
            a, b = folder / "reference.json", folder / "candidate.json"
            ref_ok = _execute(case["reference"], a, timeout, folder / "reference.log")
            cand_ok = _execute(case["candidate"], b, timeout, folder / "candidate.log")
            if ref_ok and cand_ok and a.is_file() and b.is_file():
                try:
                    ref, cand = _object(a), _object(b)
                    if ref.get("workload") != spec["workload"] or cand.get("workload") != spec["workload"]:
                        raise ValueError("outputs do not match the verification workload")
                    result.update(compare_tensors(ref, cand, atol=case["atol"], rtol=case["rtol"]))
                except (ValueError, KeyError, TypeError) as exc:
                    result["error"] = str(exc)
            else:
                result["error"] = "reference or candidate command failed or omitted its output"
            result["evidence"] = str(folder.relative_to(out))
        checks.append(result)
        (out / "checks.json").write_text(json.dumps(checks, indent=2))
    passed_categories = {c["category"] for c in checks if c["status"] == "PASS"}
    status = "PASS" if all(c["status"] == "PASS" for c in checks) and set(spec["required_categories"]) <= passed_categories else "FAIL"
    report = {"schema_version": 1, "status": status, "workload": spec["workload"],
              "required_categories": spec["required_categories"], "checks": checks,
              "code_commit": code_commit,
              "limitations": ["Project tests and numeric tolerances are user-defined; a PASS is not a proof of semantic equivalence.",
                              "Use independent invariants, sanitizers and statistical tests for changes requiring them."]}
    (out / "verification.json").write_text(json.dumps(report, indent=2))
    return report
