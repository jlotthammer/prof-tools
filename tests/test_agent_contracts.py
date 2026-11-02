"""The public workflow should not require users to supply benchmark JSON."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from prof_tools.cli import _parser


class AgentContractsTests(unittest.TestCase):
    def test_evaluate_uses_one_conventional_project_contract(self):
        args = _parser().parse_args(["evaluate", "--outdir", "/tmp/evidence"])
        self.assertEqual(args.spec, "perf/workload.json")
        self.assertEqual(args.outdir, "/tmp/evidence")

    def test_explicit_existing_contract_is_still_supported(self):
        args = _parser().parse_args(["evaluate", "--spec", "tests/perf.json", "--outdir", "/tmp/evidence"])
        self.assertEqual(args.spec, "tests/perf.json")

    def test_missing_contract_instructs_agent_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as work:
            proc = subprocess.run([sys.executable, "-m", "prof_tools.cli", "evaluate",
                                   "--outdir", str(Path(work) / "evidence")], cwd=work,
                                  env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
                                  capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("agent must author and commit", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_single_skill_assigns_contract_authoring_to_agent(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / "skills/prof-tools/SKILL.md").read_text()
        guide = (root / "skills/prof-tools/references/contract-authoring.md").read_text()
        self.assertIn("not JSON files", skill)
        self.assertIn("perf/workload.json", skill)
        self.assertIn("trusted oracle", guide)
        self.assertIn("frozen", guide)


if __name__ == "__main__":
    unittest.main()
