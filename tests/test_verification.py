import json
import sys
import tempfile
from pathlib import Path
import unittest

from prof_tools.verify import compare_tensors, run_verification, validate_spec
from prof_tools.acceptance import assess


class VerificationTests(unittest.TestCase):
    def test_numeric_forward_fails_random_or_wrong_shape(self):
        base = {"workload": {"case": 1}, "input_id": "seed-12",
                "tensors": {"y": {"dtype": "float32", "shape": [2], "data": [1.0, 2.0]}}}
        other = json.loads(json.dumps(base))
        self.assertEqual(compare_tensors(base, other, atol=0, rtol=0)["status"], "PASS")
        other["tensors"]["y"]["data"][0] = 999
        self.assertEqual(compare_tensors(base, other, atol=0, rtol=0)["status"], "FAIL")
        other["tensors"]["y"]["data"][0] = float('nan')
        self.assertEqual(compare_tensors(base, other, atol=0, rtol=0)["status"], "FAIL")
        other["tensors"]["y"]["shape"] = [1, 2]
        with self.assertRaisesRegex(ValueError, 'shapes'):
            compare_tensors(base, other, atol=0, rtol=0)

    def test_requires_both_explicit_tolerances_and_full_coverage(self):
        with self.assertRaisesRegex(ValueError, 'required category'):
            validate_spec({"schema_version": 1, "workload": {"x": 1},
                "required_categories": ["forward", "gradient"],
                "cases": [{"id": "a", "category": "forward", "type": "test", "command": ["true"]}]})

    def test_end_to_end_good_and_bad_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / 'write.py'
            script.write_text('''import json, sys
p, mode = sys.argv[1:]
json.dump({"workload":{"shape":[3]}, "input_id":"fixed-array-seed-1", "tensors":{"forward":{"shape":[3],"dtype":"float32","data":[1.0,2.0,3.0] if mode != "bad" else [4.0,5.0,6.0]}}}, open(p, 'w'))
''')
            def execute(mode, folder):
                spec = {"schema_version": 1, "workload": {"shape": [3]},
                        "required_categories": ["forward", "invariant"],
                        "cases": [
                            {"id": "compare", "category": "forward", "type": "compare", "atol": 0, "rtol": 0,
                             "reference": [sys.executable, str(script), "{output}", "ok"],
                             "candidate": [sys.executable, str(script), "{output}", mode]},
                            {"id": "invariant", "category": "invariant", "type": "test",
                             "command": [sys.executable, "-c", "assert 2 + 2 == 4"]},
                        ]}
                path = Path(d) / f'{mode}.spec.json'
                path.write_text(json.dumps(spec))
                return run_verification(path, Path(d) / folder)
            good = execute('ok', 'good')
            self.assertEqual(good['status'], 'PASS')
            bad = execute('bad', 'bad')
            self.assertEqual(bad['status'], 'FAIL')
            bench = {"outcome": "FASTER", "measured_without_profiler": True,
                     "metric_scope": "application", "workload": {"shape": [3]},
                     "memory_constraint": "NOT_CONSTRAINED"}
            self.assertEqual(assess(good, bench)['status'], 'ELIGIBLE_FOR_DESIGN_REVIEW')
            self.assertEqual(assess(bad, bench)['status'], 'BLOCKED')
            bench['metric_scope'] = 'kernel'
            self.assertEqual(assess(good, bench)['status'], 'BLOCKED')
            bench['metric_scope'] = 'application'
            bench.update({'outcome': 'SLOWER', 'memory_limit_bytes': 150,
                          'memory_constraint': 'PASS',
                          'peak_memory_observed': {'baseline': 200, 'candidate': 100}})
            self.assertEqual(assess(good, bench)['objective_basis'], 'capacity_feasibility')
            self.assertEqual(assess(good, bench)['status'], 'ELIGIBLE_FOR_DESIGN_REVIEW')

if __name__ == '__main__':
    unittest.main()
