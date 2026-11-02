import json
from pathlib import Path
import sys
import tempfile
import unittest

from prof_tools.suite import summarize_suite, validate_suite, run_suite
from prof_tools.acceptance import assess
from prof_tools.workflow import evaluate


class SuiteTests(unittest.TestCase):
    def test_missing_or_duplicate_workloads(self):
        with self.assertRaisesRegex(ValueError, "workloads"):
            validate_suite({"schema_version": 1, "metric": "ms", "workloads": []})

    def test_weighted_aggregation_not_average_of_speedups(self):
        rows = [
            {"id": "small", "weight": .9, "verification": "PASS", "pairs": [{"baseline": 2., "candidate": 1.} for _ in range(4)]},
            {"id": "large", "weight": .1, "verification": "PASS", "pairs": [{"baseline": 200., "candidate": 100.} for _ in range(4)]},
        ]
        report = summarize_suite(rows, max_regression=.10)
        self.assertEqual(report["status"], "ELIGIBLE_FOR_REVIEW")
        self.assertAlmostEqual(report["weighted_speedup"], 2.)

    def test_per_shape_regression_blocks_weighted_win(self):
        rows = [
            {"id": "fast", "weight": .9, "verification": "PASS", "pairs": [{"baseline": 100., "candidate": 40.} for _ in range(3)]},
            {"id": "slow", "weight": .1, "verification": "PASS", "pairs": [{"baseline": 5., "candidate": 6.} for _ in range(3)]},
        ]
        report = summarize_suite(rows, max_regression=.1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("regression" in x for x in report["blockers"]))

    def test_additional_project_invariant_is_a_required_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "result.py"
            script.write_text('import json,sys\nfrom pathlib import Path\nout=sys.argv[-1]\nPath(out).write_text(json.dumps({"workload":{"test":1},"input_id":"same","tensors":{"x":{"dtype":"int64","shape":[1],"data":[3]}}}))\n')
            command = [sys.executable, str(script), "{output}"]
            work = {"id": "example", "weight": 1.0, "workload": {"test": 1},
                    "baseline": [sys.executable, "-c", "print('baseline')"],
                    "candidate": [sys.executable, "-c", "print('candidate')"],
                    "verification": {"reference": command, "baseline": command, "candidate": command,
                                     "atol": 0.0, "rtol": 0.0},
                    "required_categories": ["forward", "invariant"],
                    "checks": [{"id": "conservation", "category": "invariant", "type": "test",
                                "command": [sys.executable, "-c", "raise SystemExit(1)"]}]}
            spec = root / "suite.json"
            spec.write_text(json.dumps({"schema_version": 1, "metric": "ms", "pairs": 2,
                                        "warmup": 0, "workloads": [work]}))
            result = evaluate(str(spec), str(root / "evaluation"))
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["verification"]["status"], "FAIL")
            self.assertFalse((root / "evaluation" / "example" / "benchmark").exists())

    def test_evaluate_requires_valid_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'contract.json'
            path.write_text(json.dumps({'schema_version': 1, 'workloads': []}))
            with self.assertRaises(ValueError):
                evaluate(str(path), str(Path(directory) / 'outputs'))

    def test_end_to_end_correctness_and_timed_output_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / 'case.py'
            script.write_text('''import hashlib,json,sys
from prof_tools.verify import tensor_digest
from pathlib import Path
args=sys.argv[1:]
impl=args[args.index('--impl')+1]
values=[2,4,6] if impl != 'wrong' else [0,0,0]
workload={'case':'fixture','version':1}
if '--output' in args:
    out=args[args.index('--output')+1]
    Path(out).write_text(json.dumps({'workload':workload,'input_id':'fixed','tensors':{
     'valid_count':{'dtype':'int64','shape':[3],'data':values},
     'hydrophobic_count':{'dtype':'int64','shape':[3],'data':values},
     'charge_sum':{'dtype':'int64','shape':[3],'data':values}}}))
else:
    tensors={k:{'dtype':'int64','shape':[3],'data':values} for k in ('valid_count','hydrophobic_count','charge_sum')}
    fingerprint=tensor_digest(tensors)
    ms={'reference':10,'candidate':5,'wrong':.001}[impl]
    print('PROF_TOOLS_RESULT='+json.dumps({'workload':workload,'input_id':'fixed','output_digest':fingerprint,'metrics':{'ms':ms}}))
''')
            base = [sys.executable, str(script)]
            def argv(impl):
                return base + ['--impl', impl]
            case = {"id": "fixture", "weight": 1.0, "workload": {"case": "fixture", "version": 1},
                    "baseline": argv("reference"), "candidate": argv("candidate"),
                    "verification": {"reference": argv("reference") + ['--output','{output}'],
                                     "baseline": argv("reference") + ['--output','{output}'],
                                     "candidate": argv("candidate") + ['--output','{output}'],
                                     "atol": 0.0, "rtol": 0.0}}
            spec = {"schema_version": 1, "metric": "ms", "pairs": 3, "warmup": 0, "workloads": [case]}
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec))
            evaluated = evaluate(str(spec_path), str(root / 'good'))
            self.assertEqual(evaluated['status'], 'ELIGIBLE_FOR_DESIGN_REVIEW')
            self.assertTrue((root / 'good' / 'evaluation.json').is_file())
            self.assertEqual(evaluated['verification']['status'], 'PASS')
            good = evaluated['performance']
            self.assertEqual(good['status'], 'ELIGIBLE_FOR_REVIEW')
            v = json.loads((root / 'good' / 'suite_verification.json').read_text())
            self.assertEqual(assess(v, good)['status'], 'ELIGIBLE_FOR_DESIGN_REVIEW')
            bad = json.loads(spec_path.read_text())
            bad['workloads'][0]['candidate'] = argv('wrong')
            bad['workloads'][0]['verification']['candidate'] = argv('wrong') + ['--output','{output}']
            spec_path.write_text(json.dumps(bad))
            failed = run_suite(str(spec_path), str(root / 'failed'))
            self.assertEqual(failed['status'], 'BLOCKED')
            # Cheating only during timed runs must not pass.
            bad['workloads'][0]['verification']['candidate'] = argv('candidate') + ['--output','{output}']
            spec_path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, 'timed output differs'):
                run_suite(str(spec_path), str(root / 'cheating'))


if __name__ == '__main__':
    unittest.main()
