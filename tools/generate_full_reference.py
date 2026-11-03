#!/usr/bin/env python3
"""Generate one reviewable reference document from authoritative skill Markdown."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/optimize"


def main():
    paths = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md")),
             *sorted((SKILL / "references/hardware").glob("*.md")),
             *sorted((SKILL / "references/details").glob("*.md")),
             *sorted((ROOT / "agents-optional").glob("*.md"))]
    parts = ["# Prof Tools Toolkit v1.3.0 — analysis and optimization skills, CPU/CUDA/ROCm references\n\n",
             "The installable Markdown files are authoritative; this document is a concatenated review copy.\n\n"]
    for path in paths:
        parts.extend([f"\n---\n\n## `{path.relative_to(ROOT)}`\n\n", path.read_text(), "\n"])
    (ROOT / "FULL_SKILLS_AND_HARDWARE.md").write_text("".join(parts))
    print(f"Generated {len(paths)} sections")


if __name__ == "__main__":
    main()
