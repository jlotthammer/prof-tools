#!/usr/bin/env python3
"""Install the complete skill bundle into a target project without overwriting by default."""
import argparse
from pathlib import Path
import shutil


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True, help="target repository root")
    p.add_argument("--client", choices=["claude", "codex"], required=True)
    p.add_argument("--with-agents", action="store_true", help="Claude only, opt in to five optional agent templates")
    p.add_argument("--force", action="store_true", help="replace previously installed toolkit skill directories")
    args = p.parse_args()
    if args.with_agents and args.client != "claude":
        p.error("--with-agents currently supports only Claude Code")
    repo = Path(__file__).resolve().parent.parent
    source = repo / "skills"
    dest = args.project.resolve() / (".claude/skills" if args.client == "claude" else ".agents/skills")
    skills = sorted(x for x in source.iterdir() if x.is_dir() and (x / "SKILL.md").is_file())
    jobs = [(skill, dest / skill.name) for skill in skills]
    if args.with_agents:
        jobs.extend((agent, args.project.resolve() / ".claude/agents" / agent.name) for agent in (repo / "agents-optional").glob("*.md"))
    existing = [str(t) for _, t in jobs if t.exists()]
    if existing and not args.force:
        p.error("would overwrite installed files (pass --force to replace): " + ", ".join(existing))
    for src, dst in jobs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        print(f"installed {dst}")
    print("Tip: `prof-tools` CLI is installed separately with `python -m pip install -e <toolkit>`")

if __name__ == "__main__":
    main()
