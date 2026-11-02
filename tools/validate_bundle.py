#!/usr/bin/env python3
"""Validate the single explicit skill and references."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "prof-tools"


def main():
    installed = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
    assert installed == ["prof-tools"], installed
    content = (SKILL / "SKILL.md").read_text()
    assert "name: prof-tools" in content.split("---", 2)[1]
    assert "disable-model-invocation: true" in content.split("---", 2)[1]
    md_files = [SKILL / "SKILL.md", *SKILL.rglob("*.md")]
    for file in set(md_files):
        for rel in re.findall(r"\]\(([^)#]+\.md)\)", file.read_text()):
            if rel.startswith(("http:", "https:")):
                continue
            assert (file.parent / rel).is_file(), (file, rel)
    for name in ("h100-sxm5.md", "mi300a.md", "method-and-porting.md"):
        assert (SKILL / "references/hardware" / name).is_file()
    print("Validated single opt-in prof-tools skill, all local reference links, and 3 hardware references")


if __name__ == "__main__":
    main()
