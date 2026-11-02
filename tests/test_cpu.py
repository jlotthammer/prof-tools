import cProfile
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prof_tools.cpu import cpu_inventory, cprofile_summary, collapsed_stacks_summary
from prof_tools.benchmark import parse_result


class CpuToolsTests(unittest.TestCase):
    def test_inventory_is_non_mutating_and_jsonable(self):
        info = cpu_inventory()
        self.assertIn("architecture", info)
        self.assertIn("affinity_cpu_count", info)
        self.assertIn("cgroup_v2_cpu_quota_cores", info)
        self.assertIn("tools", info)
        json.dumps(info)

    def test_pstats_read_and_sort(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "calls.pstats"
            profiler = cProfile.Profile()
            def f():
                return sum(x * x for x in range(50))
            profiler.runcall(f)
            profiler.dump_stats(str(output))
            result = cprofile_summary(output, top=10, sort="cumulative")
            self.assertGreater(result["function_count"], 0)
            self.assertGreater(result["total_function_calls"], 0)
            self.assertTrue(any(x["function"] == "f" for x in result["functions"]))
            self.assertGreaterEqual(result["sum_self_time_s"], 0)

    def test_pstats_invalid_sort_and_top(self):
        with self.assertRaises(ValueError):
            cprofile_summary("not-read.pstats", top=0)
        with self.assertRaises(ValueError):
            cprofile_summary("not-read.pstats", sort="foobar")

    def test_collapsed_summary_inclusive_exclusive_and_recursion(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sample.folded"
            output.write_text("main;foo 4\nmain;foo;foo 2\nmain;bar 3\n")
            result = collapsed_stacks_summary(output)
            self.assertEqual(result["total_leaf_weight"], 9)
            frames = {r["frame"]: r for r in result["frames"]}
            self.assertEqual(frames["main"]["inclusive_weight"], 9)
            self.assertEqual(frames["foo"]["inclusive_weight"], 6)
            self.assertEqual(frames["foo"]["exclusive_weight"], 6)
            self.assertEqual(frames["bar"]["exclusive_weight"], 3)
            self.assertEqual(sum(x["exclusive_weight"] for x in frames.values()), 9)

    def test_collapsed_bad_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.txt"
            for content in ("root;child", "root;child inf", "root;child 0", "root;;child 12", "# only comment\n"):
                path.write_text(content)
                with self.assertRaises(ValueError, msg=content):
                    collapsed_stacks_summary(path)

    def test_real_cpu_child_protocol(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "benchmark_cpu.py"
        values = []
        checksums = []
        for variant in ("baseline", "candidate"):
            process = subprocess.run([sys.executable, str(example), "--variant", ("reference" if variant == "baseline" else "candidate"),
                                      "--elements", "200", "--steps", "3"],
                                     capture_output=True, text=True, check=True)
            latency, payload = parse_result(process.stdout, "iteration_ms")
            self.assertGreater(latency, 0)
            values.append(payload["workload"])
            checksums.append(payload["workload"]["checksum"])
        self.assertEqual(values[0], values[1])
        self.assertEqual(checksums[0], checksums[1])

    def test_cli_cpu_commands(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            folded = Path(directory) / "folded.txt"
            folded.write_text("main;f 4\n")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root / "src")
            cmd = [sys.executable, "-m", "prof_tools.cli", "diagnose", "--cpu-profile", str(folded), "--cpu-format", "folded"]
            process = subprocess.run(cmd, capture_output=True, text=True, env=env, check=True)
            self.assertEqual(json.loads(process.stdout)["sources"]["cpu_profile"]["total_leaf_weight"], 4)
            p = subprocess.run([sys.executable, "-m", "prof_tools.cli", "inspect", "--kind", "cpu-environment"],
                               capture_output=True, text=True, env=env, check=True)
            self.assertIn("cpu_name", json.loads(p.stdout))


if __name__ == "__main__":
    unittest.main()
