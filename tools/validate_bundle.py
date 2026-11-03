#!/usr/bin/env python3
"""Validate the explicit skills and their local references."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def main():
    installed = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
    assert installed == ["analyze", "optimize"], installed
    for skill_name in installed:
        skill = ROOT / "skills" / skill_name
        content = (skill / "SKILL.md").read_text()
        assert f"name: {skill_name}" in content.split("---", 2)[1]
        assert "disable-model-invocation: true" in content.split("---", 2)[1]
        md_files = [skill / "SKILL.md", *skill.rglob("*.md")]
        for file in set(md_files):
            for rel in re.findall(r"\]\(([^)#]+\.md)\)", file.read_text()):
                if rel.startswith(("http:", "https:")):
                    continue
                assert (file.parent / rel).is_file(), (file, rel)
    for name in ("h100-sxm5.md", "mi300a.md", "method-and-porting.md"):
        assert (ROOT / "skills/optimize/references/hardware" / name).is_file()
    print("Validated analyze and optimize skills, all local reference links, and 3 hardware references")


if __name__ == "__main__":
    main()
