"""Foreground, resumable, single-worker campaign orchestration."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def _identity(campaign_file: Path, campaign: dict) -> dict:
    branches = campaign.get("branches")
    if not isinstance(branches, list) or not branches:
        raise ValueError("campaign report must contain prepared branches")
    normalized = []
    for branch in branches:
        worktree = Path(branch["worktree"]).resolve()
        if not worktree.is_dir() or not (worktree / ".git").exists():
            raise ValueError(f"campaign worktree is missing: {worktree}")
        normalized.append({"id": branch["id"], "branch": branch["branch"],
                           "worktree": str(worktree), "brief": branch["brief"],
                           "status": "pending", "session_id": None})
    git_dir = Path(campaign["campaign_git_dir"]).resolve()
    if not git_dir.is_dir() or not (git_dir / "HEAD").is_file():
        raise ValueError("campaign_git_dir is not an existing bare Git repository")
    return {"schema_version": 1, "campaign_file": str(campaign_file),
            "campaign_sha256": hashlib.sha256(campaign_file.read_bytes()).hexdigest(),
            "campaign_git_dir": str(git_dir),
            "labcoat_repository": str(Path(campaign["labcoat_repository"]).resolve()),
            "base_commit": campaign["base_commit"], "branches": normalized}


def _session_id(output: str) -> str | None:
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            return event["thread_id"]
    return None


def reserve_evaluation(phase: str) -> Path | None:
    """Atomically consume one campaign evaluation slot for a CLI evaluation."""
    state_value = os.environ.get("PROF_TOOLS_CAMPAIGN_STATE")
    if not state_value:
        common_dir = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                                    capture_output=True, text=True, check=False)
        if common_dir.returncode:
            return None
        state_value = str((Path(common_dir.stdout.strip()).resolve().parent / "campaign-run.json"))
        if not Path(state_value).is_file():
            return None
    if phase not in {"candidate", "final"}:
        raise ValueError("evaluation phase must be candidate or final")
    state_path = Path(state_value).resolve()
    state = _read_json(state_path)
    now = time.time()
    if phase == "candidate" and state["status"] != "running":
        raise ValueError("candidate evaluations are available only during candidate exploration")
    if phase == "final" and state["status"] != "ready_for_final_review":
        raise ValueError("final evaluation is available only after candidate exploration completes")
    deadline = state["candidate_deadline_epoch"] if phase == "candidate" else state["deadline_epoch"]
    if now >= deadline:
        raise ValueError(f"{phase} evaluation time budget has expired")
    directory = state_path.parent / "evaluation-reservations"
    directory.mkdir(exist_ok=True)
    maximum = state["limits"]["max_candidate_evaluations"]
    slots = range(maximum) if phase == "candidate" else range(1)
    prefix = "candidate" if phase == "candidate" else "final"
    for index in slots:
        path = directory / (f"candidate-{index + 1:04d}.json" if phase == "candidate" else "final.json")
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w") as handle:
            json.dump({"phase": phase, "started_at_utc": datetime.now(timezone.utc).isoformat()}, handle)
        return path
    raise ValueError(f"{prefix} evaluation budget is exhausted")


def _worker_prompt(state: dict, branch: dict) -> str:
    brief = branch["brief"]
    return f"""Use Prof Tools and Labcoat to test this optimization hypothesis.

Objective: {state['objective']}
Base commit: {state['base_commit']}
Hypothesis: {brief['hypothesis']}
Optimization family: {brief['family']}
Falsification test: {brief['falsification_test']}

Work only in the assigned worktree: {branch['worktree']}
Read the installed Prof Tools and Labcoat instructions. Preregister an ACTIVE Labcoat note before editing. Run correctness checks and use `prof-tools evaluate --phase candidate` for evidence; the shared campaign budget limits evaluations. Preserve failures, commit experiment work to this isolated campaign branch, and complete the note. Do not merge, push, or modify the source repository."""


@contextmanager
def _campaign_lock(campaign_path: str):
    campaign = _read_json(Path(campaign_path).resolve())
    # OS-managed locking releases on process exit and leaves no stale lock file.
    lock_file = open(Path(campaign["campaign_git_dir"]) / "HEAD", "r")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise ValueError("another campaign runner already owns this campaign") from exc
    try:
        yield
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def _stop_process(process: subprocess.Popen) -> str:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = process.communicate()
    return output or ""


def _run_campaign(campaign_path: str, *, objective: str | None = None,
                  time_budget_minutes: float | None = None,
                  max_evaluations: int | None = None, reserve_minutes: float = 15,
                  resume: bool = False, dry_run: bool = False) -> dict:
    campaign_file = Path(campaign_path).resolve()
    campaign = _read_json(campaign_file)
    root = Path(campaign["campaign_git_dir"]).resolve().parent
    state_path = root / "campaign-run.json"
    if not dry_run and not shutil.which("codex"):
        raise ValueError("Codex CLI is required to run a campaign")
    if resume:
        state = _read_json(state_path)
        identity = _identity(campaign_file, campaign)
        for key in ("campaign_file", "campaign_sha256", "campaign_git_dir", "base_commit"):
            if state.get(key) != identity[key]:
                raise ValueError(f"campaign changed since run initialization: {key}")
        if state["status"] not in {"ready", "paused", "running", "ready_for_final_review"}:
            raise ValueError(f"campaign cannot resume from state {state['status']!r}")
    else:
        if state_path.exists():
            raise FileExistsError(f"campaign state exists; resume it with --resume: {state_path}")
        if not objective or not objective.strip():
            raise ValueError("campaign run requires --objective")
        if (not isinstance(time_budget_minutes, (int, float)) or
                not math.isfinite(time_budget_minutes) or not math.isfinite(reserve_minutes) or
                reserve_minutes <= 0 or time_budget_minutes <= reserve_minutes):
            raise ValueError("time budget must exceed reserved finalization minutes")
        if not isinstance(max_evaluations, int) or max_evaluations < 2:
            raise ValueError("max evaluations must allow at least one candidate and one final evaluation")
        now = time.time()
        state = {**_identity(campaign_file, campaign), "objective": objective.strip(),
                 "started_at_utc": datetime.now(timezone.utc).isoformat(),
                 "deadline_epoch": now + time_budget_minutes * 60,
                 "candidate_deadline_epoch": now + (time_budget_minutes - reserve_minutes) * 60,
                 "limits": {"max_candidate_evaluations": max_evaluations - 1,
                            "reserved_final_evaluations": 1, "max_workers": 1,
                            "reserve_minutes": reserve_minutes},
                 "status": "ready", "active_branch": None}
        if dry_run:
            return {"status": state["status"], "state_file": str(state_path),
                    "limits": state["limits"], "branches": state["branches"],
                    "next_action": "Dry run: no state was written and no worker was started."}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(state_path, state)
    if dry_run:
        return {"status": state["status"], "state_file": str(state_path),
                "limits": state["limits"], "branches": state["branches"],
                "next_action": "Dry run: no worker was started."}
    codex = shutil.which("codex")
    state["status"] = "running"
    env = os.environ.copy()
    env["PROF_TOOLS_CAMPAIGN_STATE"] = str(state_path)
    for branch in state["branches"]:
        if branch["status"] == "complete":
            continue
        remaining = state["candidate_deadline_epoch"] - time.time()
        if remaining <= 0:
            state["status"] = "paused"
            break
        branch["status"] = "running"
        state["active_branch"] = branch["id"]
        _write_json(state_path, state)
        prompt = _worker_prompt(state, branch)
        command = [codex, "exec", "--cd", branch["worktree"], "--sandbox", "workspace-write",
                   "--add-dir", state["campaign_git_dir"], "--add-dir",
                   str(Path(state["labcoat_repository"]) / "notes"), "--json"]
        if branch["session_id"]:
            command = [codex, "exec", "resume", branch["session_id"], prompt, "--json"]
        else:
            command.append(prompt)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=env, start_new_session=True)
        try:
            output, error = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            output = _stop_process(process)
            error = "worker stopped at candidate deadline"
            branch["session_id"] = _session_id(output) or branch["session_id"]
            branch["status"] = "paused"
            state["status"] = "paused"
            (root / f"worker-{branch['id']}.log").write_text(output)
            _write_json(state_path, state)
            return {"status": "paused", "state_file": str(state_path),
                    "active_branch": branch["id"], "session_id": branch["session_id"],
                    "reason": "candidate time expired; resume with --resume"}
        except KeyboardInterrupt:
            output = _stop_process(process)
            branch["session_id"] = _session_id(output) or branch["session_id"]
            branch["status"] = "paused"
            state["status"] = "paused"
            (root / f"worker-{branch['id']}.log").write_text(output + "\n--- STDERR ---\n" + "interrupted by user")
            _write_json(state_path, state)
            return {"status": "paused", "state_file": str(state_path),
                    "active_branch": branch["id"], "session_id": branch["session_id"],
                    "reason": "interrupted by user; resume with --resume"}
        branch["session_id"] = _session_id(output) or branch["session_id"]
        (root / f"worker-{branch['id']}.log").write_text(output + "\n--- STDERR ---\n" + error)
        if process.returncode:
            branch["status"] = "paused"
            state["status"] = "paused"
            _write_json(state_path, state)
            return {"status": "paused", "state_file": str(state_path),
                    "active_branch": branch["id"], "session_id": branch["session_id"],
                    "reason": f"Codex exited {process.returncode}; see worker log"}
        branch["status"] = "complete"
        state["active_branch"] = None
        _write_json(state_path, state)
    else:
        state["status"] = "ready_for_final_review"
    _write_json(state_path, state)
    reservations = root / "evaluation-reservations"
    return {"status": state["status"], "state_file": str(state_path),
            "completed_branches": [x["id"] for x in state["branches"] if x["status"] == "complete"],
            "candidate_evaluations": len(list(reservations.glob("candidate-*.json"))) if reservations.exists() else 0,
            "next_action": "Integrate and independently review the selected change, then use `prof-tools evaluate --phase final` and `prof-tools finalize`."}


def run_campaign(campaign_path: str, *, objective: str | None = None,
                 time_budget_minutes: float | None = None,
                 max_evaluations: int | None = None, reserve_minutes: float = 15,
                 resume: bool = False, dry_run: bool = False) -> dict:
    arguments = {"objective": objective, "time_budget_minutes": time_budget_minutes,
                 "max_evaluations": max_evaluations, "reserve_minutes": reserve_minutes,
                 "resume": resume, "dry_run": dry_run}
    if dry_run:
        return _run_campaign(campaign_path, **arguments)
    with _campaign_lock(campaign_path):
        return _run_campaign(campaign_path, **arguments)
