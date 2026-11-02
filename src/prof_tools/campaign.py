"""Prepare isolated campaign checkouts; Labcoat owns canonical experiment records.

The source repository is read-only. Experimental Git objects and refs live in a
separate bare repository; Labcoat notes live in another independent repository.
"""
from __future__ import annotations

from datetime import date
from .opportunity import analyze_opportunities
from pathlib import Path
import shutil
import re
import secrets
import subprocess


def _git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if p.returncode:
        raise ValueError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def _copy_author_identity(source: Path, destination: Path) -> None:
    """Carry repository-local identity into independent experiment repositories."""
    for name in ("user.name", "user.email"):
        existing = subprocess.run(["git", "-C", str(destination), "config", "--get", name],
                                  capture_output=True, text=True)
        if existing.returncode == 0:
            continue
        value = subprocess.run(["git", "-C", str(source), "config", "--get", name],
                               capture_output=True, text=True)
        if value.returncode == 0:
            _git(destination, "config", "--local", name, value.stdout.strip())


def _safe(value: str) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return value[:48] or "candidate"


def plan_campaign(opportunities: dict, repo: str, base: str) -> dict:
    repository = Path(repo).resolve()
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=normal"):
        raise ValueError("campaign planning requires a clean repository")
    base_sha = _git(repository, "rev-parse", "--verify", f"{base}^{{commit}}")
    candidates = {x["id"]: x for x in opportunities.get("candidates", [])}
    selected = opportunities.get("initial_branches")
    if not isinstance(selected, list) or not selected or len(selected) != len(set(selected)):
        raise ValueError("opportunity report must select distinct initial branches")
    branches = []
    for candidate_id in selected:
        if candidate_id not in candidates:
            raise ValueError(f"unknown selected candidate {candidate_id}")
        c = candidates[candidate_id]
        experiment_id = f"{date.today():%Y-%m-%d}-{secrets.token_hex(4)}"
        branches.append({"id": experiment_id, "candidate_id": candidate_id,
                         "family": c["family"], "branch": f"prof-tools/{experiment_id}-{_safe(candidate_id)}",
                         "hypothesis": c["mechanism"], "falsification_test": c["falsification_test"],
                         "base_commit": base_sha,
                         "labcoat": {"class": "EXPLORATORY", "state": "ACTIVE", "parents": [],
                                     "artifact_directory": f"notes/artifacts/{experiment_id}/"}})
    plan = {"schema_version": 1, "repository": str(repository), "base_commit": base_sha,
            "branches": branches,
            "ownership": {"experiments": "Labcoat notes Git repository and isolated campaign Git repository",
                          "measurements": "prof-tools result artifacts",
                          "dispatch": "calling agent/coordinator runtime"},
            "instructions": ["Read Labcoat SKILL.md, footguns.md and orchestration.md before changing code.",
                             "Search previous Labcoat experiments and preregister ACTIVE note in a distinct commit.",
                             "Workers own distinct worktrees, notes and artifact paths; never share mutable outputs.",
                             "Run prof-tools evaluate against the representative workload contract before reporting an improvement.",
                             "Keep alternatives independent in the campaign repository; final integration starts from original base, not merged exploration branches. Land only the clean final patch in source."]}
    return plan


def _initialize_notes_repo(directory: Path) -> None:
    """Create a separate, persistent Labcoat repository; never create notes in source."""
    if directory.exists():
        if not directory.is_dir():
            raise ValueError("Labcoat repository path is not a directory")
        if (directory / ".git").exists():
            if _git(directory, "rev-parse", "--show-toplevel") != str(directory):
                raise ValueError("Labcoat must own an independent Git repository")
        elif any(directory.iterdir()):
            raise ValueError("Labcoat directory exists without its own Git repository")
        else:
            _git_init(directory)
    else:
        directory.mkdir(parents=True)
        _git_init(directory)
    (directory / "notes").mkdir(exist_ok=True)


def _git_init(directory: Path) -> None:
    proc = subprocess.run(["git", "init", "-q", str(directory)], capture_output=True, text=True)
    if proc.returncode:
        raise ValueError(f"git init Labcoat repository: {proc.stderr.strip()}")


def prepare_campaign(plan: dict, worktrees: str, labcoat_repo: str | None = None) -> dict:
    if plan.get("schema_version") != 1:
        raise ValueError("unrecognized campaign plan")
    repository = Path(plan["repository"]).resolve()
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=normal"):
        raise ValueError("source repository must be clean")
    if _git(repository, "rev-parse", "--verify", f"{plan['base_commit']}^{{commit}}") != plan["base_commit"]:
        raise ValueError("base commit missing")

    destination = Path(worktrees).resolve()
    notes_repo = (Path(labcoat_repo).resolve() if labcoat_repo
                  else repository.parent / f"{repository.name}-labcoat")
    if any(path == repository or repository in path.parents for path in (destination, notes_repo)):
        raise ValueError("campaign and Labcoat repositories must be outside the source repository")
    if destination == notes_repo or destination in notes_repo.parents or notes_repo in destination.parents:
        raise ValueError("campaign and Labcoat repositories must have separate directories")
    if destination.exists():
        raise FileExistsError("campaign destination must be new")
    if notes_repo.exists() and not (notes_repo / ".git").is_dir() and any(notes_repo.iterdir()):
        raise ValueError("existing Labcoat path is not an independent Git repository")
    if not plan["branches"]:
        raise ValueError("campaign requires experiment branches")

    destination.mkdir(parents=True)
    git_dir = destination / "campaign.git"
    allocated = []
    try:
        # --no-local makes an independent Git object database. No alternates,
        # shared .git directory, or experimental refs in the source repository.
        cmd = ["git", "clone", "--bare", "--no-local", "--no-hardlinks",
               str(repository), str(git_dir)]
        cloned = subprocess.run(cmd, capture_output=True, text=True)
        if cloned.returncode:
            raise ValueError(f"isolated campaign clone: {cloned.stderr.strip()}")
        _copy_author_identity(repository, git_dir)
        # Even accidental `git push` must not target the source repo.
        subprocess.run(["git", "--git-dir", str(git_dir), "remote", "remove", "origin"],
                       capture_output=True, check=False)
        with (git_dir / "info" / "exclude").open("a") as exclude:
            exclude.write("\n/notes\n")
        if _git(git_dir, "rev-parse", "--verify", f"{plan['base_commit']}^{{commit}}") != plan["base_commit"]:
            raise ValueError("source baseline not in isolated clone")
        _initialize_notes_repo(notes_repo)
        _copy_author_identity(repository, notes_repo)
        (destination / "worktrees").mkdir()
        for item in plan["branches"]:
            location = destination / "worktrees" / item["id"]
            _git(git_dir, "worktree", "add", "-b", item["branch"],
                 str(location), plan["base_commit"])
            (location / "notes").symlink_to(notes_repo / "notes", target_is_directory=True)
            allocated.append({"id": item["id"], "worktree": str(location),
                              "branch": item["branch"],
                              "brief": {**item, "worktree": str(location),
                                        "labcoat_repository": str(notes_repo)}})
    except (ValueError, OSError):
        # None of these Git changes touched the source repository. This path
        # runs before workers can write experiment evidence.
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return {"source": str(repository), "base_commit": plan["base_commit"],
            "campaign_git_dir": str(git_dir), "labcoat_repository": str(notes_repo),
            "prepared": allocated,
            "next_action": "Workers commit experiments in the isolated campaign Git repository and ACTIVE/COMPLETE notes in the separate Labcoat Git repository. Never push experiment refs to source. After independent final validation, land only a consolidated patch."}



def start_campaign(opportunity_spec: str, repo: str, base: str, worktrees: str, labcoat_repo: str | None = None) -> dict:
    """Validate and prepare a branch portfolio; Labcoat owns experiment notes.

    No campaign-state database or persistent intermediate planning artifact.
    """
    report = analyze_opportunities(opportunity_spec)
    plan = plan_campaign(report, repo, base)
    prepared = prepare_campaign(plan, worktrees, labcoat_repo)
    return {"schema_version": 1, "base_commit": plan["base_commit"],
            "repository": plan["repository"], "opportunities": report,
            "campaign_git_dir": prepared["campaign_git_dir"],
            "labcoat_repository": prepared["labcoat_repository"],
            "branches": prepared["prepared"],
            "next_action": prepared["next_action"],
            "experiment_records": "Separate Labcoat Git repository and isolated campaign Git repository"}
