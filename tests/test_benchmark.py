import json
import sys
import tempfile
import unittest
from pathlib import Path
from prof_tools.benchmark import parse_result, run_trials


class BenchmarkTest(unittest.TestCase):
    def test_parse(self):
        v, obj = parse_result('PROF_TOOLS_RESULT={"metrics":{"time_ms": 5}, "workload":{"batch":8}}\n', 'time_ms')
        self.assertEqual(v, 5)
        self.assertEqual(obj['workload'], {"batch":8})

    def test_reject_legacy_result_protocol(self):
        with self.assertRaisesRegex(ValueError, "PROF_TOOLS_RESULT"):
            parse_result('GPU_PERF_RESULT={"metrics":{"time_ms":5}}', 'time_ms')

    def test_missing_workload_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "workload identity"):
            parse_result('PROF_TOOLS_RESULT={"metrics":{"time_ms":5}}', 'time_ms')

    def test_result_requires_exactly_one_line(self):
        with self.assertRaises(ValueError):
            parse_result('PROF_TOOLS_RESULT={"metrics":{"time_ms":5}}\nPROF_TOOLS_RESULT={"metrics":{"time_ms":6}}', 'time_ms')

    def test_memory_limit_is_independent_of_performance(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "memory"
            script = Path(d) / "mem.py"
            script.write_text("import json,sys; print('PROF_TOOLS_RESULT='+json.dumps({'metrics':{'ms':float(sys.argv[1]),'peak_memory_bytes':int(sys.argv[2])},'workload':{'shape':8}}))")
            import shlex
            base = f'{shlex.quote(sys.executable)} {shlex.quote(str(script))} 10 100'
            cand = f'{shlex.quote(sys.executable)} {shlex.quote(str(script))} 8 200'
            result = run_trials(base, cand, 'ms', out, pairs=2, warmup=0,
                                memory_metric='peak_memory_bytes', memory_limit_bytes=150)
            self.assertEqual(result['outcome'], 'FASTER')
            self.assertEqual(result['memory_constraint'], 'FAIL')
            self.assertEqual(result['peak_memory_observed']['candidate'], 200)

    def test_outer_runner(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "run"
            script = Path(d) / "mock.py"
            script.write_text("import sys, json; print('PROF_TOOLS_RESULT='+json.dumps({'metrics': {'time_ms':float(sys.argv[1])}, 'workload':{'batch':8}}))")
            import sys, shlex
            base = f'{shlex.quote(sys.executable)} {shlex.quote(str(script))} 10'
            cand = f'{shlex.quote(sys.executable)} {shlex.quote(str(script))} 8'
            r = run_trials(base, cand, 'time_ms', out, pairs=3, warmup=0)
            self.assertEqual(r['outcome'], 'FASTER')
            self.assertEqual(len(json.loads((out / 'trials.json').read_text())), 3)
            self.assertEqual(r['correctness'], 'NOT_EVALUATED')

if __name__ == "__main__":
    unittest.main()
