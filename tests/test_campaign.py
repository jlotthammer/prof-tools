import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from prof_tools.campaign import start_campaign


def git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def opportunities():
    families = ("algebra", "dataflow", "scheduling", "memory", "library", "kernel", "distributed")
    return {"schema_version": 1,
            "objective": {"metric_scope": "application", "direction": "lower", "memory": {"mode": "secondary"}},
            "workloads": [{"id": "main", "weight": 1.0, "baseline_ms": 50}],
            "family_screening": {name: {"status": "considered", "reason": "measured application dataflow"} for name in families},
            "candidates": [{"id": "algebra", "family": "algebra", "mechanism": "remove redundant work",
                            "falsification_test": "count operations", "cost": "low",
                            "per_workload": {"main": {"exposed_ms": 15, "speedup_ceiling": 3}}},
                           {"id": "kernel", "family": "kernel", "mechanism": "fuse launches",
                            "falsification_test": "check dispatch count", "cost": "medium",
                            "per_workload": {"main": {"exposed_ms": 10, "speedup_ceiling": 2}}}]}


class CampaignTests(unittest.TestCase):
    def make_repo(self, root):
        repo = root / "project"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "ci@example.invalid")
        git(repo, "config", "user.name", "Test")
        (repo / "file.py").write_text("x=1\n")
        git(repo, "add", "file.py")
        git(repo, "commit", "-qm", "initial")
        return repo

    def test_start_creates_distinct_worktrees_with_one_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            base = git(repo, "rev-parse", "HEAD")
            spec = root / "opportunities.json"
            spec.write_text(json.dumps(opportunities()))
            worktrees = root / "branches"
            report = start_campaign(str(spec), str(repo), base, str(worktrees))
            self.assertEqual(report["base_commit"], base)
            self.assertEqual(len(report["branches"]), 2)
            self.assertEqual({x["brief"]["family"] for x in report["branches"]}, {"kernel", "algebra"})
            for item in report["branches"]:
                self.assertEqual(git(item["worktree"], "rev-parse", "HEAD"), base)
            self.assertFalse((repo / "campaign.json").exists())
            with self.assertRaises(FileExistsError):
                start_campaign(str(spec), str(repo), base, str(worktrees))

    def test_experimental_code_and_labcoat_commits_cannot_pollute_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            base = git(repo, "rev-parse", "HEAD")
            source_branches = git(repo, "branch", "--list")
            spec = root / "opportunities.json"
            spec.write_text(json.dumps(opportunities()))
            campaign = start_campaign(str(spec), str(repo), base, str(root / "campaign"))
            first = campaign["branches"][0]
            worker = Path(first["worktree"])
            bare = Path(campaign["campaign_git_dir"])
            notes_repo = Path(campaign["labcoat_repository"])

            # The worker's .git points to the campaign, not the source.
            self.assertEqual(Path(git(worker, "rev-parse", "--git-common-dir")).resolve(), bare)
            self.assertEqual(git(bare, "remote"), "")
            self.assertTrue((worker / "notes").is_symlink())
            self.assertEqual((worker / "notes").resolve(), notes_repo / "notes")
            self.assertEqual(git(worker, "status", "--porcelain"), "")

            (worker / "file.py").write_text("x=999\n")
            git(worker, "add", "file.py")
            git(worker, "commit", "-qm", "failed experimental approach")
            experimental = git(worker, "rev-parse", "HEAD")
            self.assertEqual(git(repo, "rev-parse", "HEAD"), base)
            self.assertEqual(git(repo, "branch", "--list"), source_branches)
            self.assertNotEqual(experimental, base)
            self.assertNotIn(experimental, git(repo, "rev-list", "--all"))

            note = notes_repo / "notes" / "experiment.md"
            note.write_text("---\nstate: ACTIVE\n---\n")
            git(notes_repo, "add", "notes/experiment.md")
            git(notes_repo, "commit", "-qm", "preregister hypothesis")
            labcoat_commit = git(notes_repo, "rev-parse", "HEAD")
            self.assertNotIn(labcoat_commit, git(repo, "rev-list", "--all"))
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            self.assertFalse((repo / "notes").exists())
            self.assertEqual((repo / "file.py").read_text(), "x=1\n")

    def test_preparation_contract_commit_remains_outside_original_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = self.make_repo(root)
            original_sha = git(original, "rev-parse", "HEAD")
            prep = root / "preparation"
            subprocess.run(["git", "clone", "-q", "--no-local", "--no-hardlinks",
                            str(original), str(prep)], check=True)
            git(prep, "remote", "remove", "origin")
            git(prep, "config", "user.name", git(original, "config", "user.name"))
            git(prep, "config", "user.email", git(original, "config", "user.email"))
            (prep / "perf").mkdir()
            (prep / "perf" / "workload.json").write_text('{"schema_version": 1}\n')
            git(prep, "add", "perf/workload.json")
            git(prep, "commit", "-qm", "freeze independent benchmark contract")
            prepared_sha = git(prep, "rev-parse", "HEAD")
            self.assertNotEqual(prepared_sha, original_sha)
            spec = root / "opportunities.json"
            spec.write_text(json.dumps(opportunities()))
            result = start_campaign(str(spec), str(prep), prepared_sha, str(root / "campaign"))
            self.assertEqual(result["base_commit"], prepared_sha)
            self.assertEqual(git(original, "rev-parse", "HEAD"), original_sha)
            self.assertNotIn(prepared_sha, git(original, "rev-list", "--all"))
            self.assertNotIn("prof-tools/", git(original, "branch", "--list"))
            self.assertFalse((original / "perf").exists())
            self.assertEqual(git(original, "status", "--porcelain"), "")

    def test_public_campaign_cli_and_output_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            spec = root / "opportunities.json"
            spec.write_text(json.dumps(opportunities()))
            cmd = [sys.executable, "-m", "prof_tools.cli", "campaign", "start",
                   "--repo", str(repo), "--base", "HEAD",
                   "--opportunities", str(spec), "--worktrees", str(root / "worktrees")]
            bad = subprocess.run([*cmd, "--out", str(repo / "campaign.json")],
                                 capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse((root / "worktrees").exists())
            good = subprocess.run([*cmd, "--out", str(root / "campaign.json")],
                                  capture_output=True, text=True, check=True)
            report = json.loads(good.stdout)
            self.assertEqual(len(report["branches"]), 2)
            self.assertEqual(report, json.loads((root / "campaign.json").read_text()))

    def test_reject_dirty_source_and_invalid_screening(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            spec = root / "opportunities.json"
            spec.write_text(json.dumps(opportunities()))
            (repo / "dirty").write_text("untracked")
            with self.assertRaisesRegex(ValueError, "clean"):
                start_campaign(str(spec), str(repo), "HEAD", str(root / "worktrees"))
            (repo / "dirty").unlink()
            doc = opportunities()
            del doc["family_screening"]["dataflow"]
            spec.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "seven"):
                start_campaign(str(spec), str(repo), "HEAD", str(root / "worktrees"))

    def test_cli_public_surface_excludes_legacy_commands(self):
        help_text = subprocess.run([sys.executable, "-m", "prof_tools.cli", "--help"],
                                   capture_output=True, text=True, check=True).stdout
        self.assertIn("campaign", help_text)
        self.assertIn("evaluate", help_text)
        for old in ("opportunities", "campaign-plan", "campaign-prepare", "verify", "bench", "suite", "assess", "integration-review"):
            self.assertFalse(any(line.startswith(f"    {old} ") for line in help_text.splitlines()))
            bad = subprocess.run([sys.executable, "-m", "prof_tools.cli", old], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)


if __name__ == "__main__":
    unittest.main()
