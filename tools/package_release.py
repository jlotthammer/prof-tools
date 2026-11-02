#!/usr/bin/env python3
"""Deterministic archive + SHA256SUMS for distributable skill bundle.

Run after tests and `tools/generate_full_reference.py`. No network or dependencies.
"""
from hashlib import sha256
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT.parent / f"{ROOT.name}.zip"
CHECKSUMS = ROOT / "SHA256SUMS.txt"


def included(path: Path) -> bool:
    parts = path.relative_to(ROOT).parts
    return not any(part in {"__pycache__", ".pytest_cache", "build", "dist"}
                   or part.endswith(".egg-info") for part in parts) and not path.name.endswith((".pyc", ".pyo"))


def main():
    sources = sorted(p for p in ROOT.rglob("*") if p.is_file() and included(p) and p != CHECKSUMS)
    CHECKSUMS.write_text("".join(f"{sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n"
                                    for p in sources))
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in sources + [CHECKSUMS]:
            arc = f"{ROOT.name}/{p.relative_to(ROOT).as_posix()}"
            info = zipfile.ZipInfo(arc, date_time=(2026, 10, 30, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((stat.S_IFREG | (p.stat().st_mode & 0o777)) << 16)
            archive.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(sources) + 1
    print(f"Wrote {ARCHIVE} with {len(sources)+1} files ({ARCHIVE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
