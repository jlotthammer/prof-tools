import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from prof_tools.acceptance import REVIEW_CHECKS, integration_review


def git(path, *argv):
    return subprocess.run(['git', '-C', str(path), *argv], check=True,
                          capture_output=True, text=True).stdout.strip()


class IntegrationReviewTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        root = Path(self.workspace.name)
        self.repo = root / 'code'
        self.repo.mkdir()
        self.artifacts = root / 'reports'
        self.artifacts.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.name', 'Test Reviewer')
        git(self.repo, 'config', 'user.email', 'test@example.com')
        (self.repo / 'code.py').write_text('value = 1\n')
        (self.repo / 'perf').mkdir()
        (self.repo / 'perf' / 'workload.json').write_text('{"schema_version": 1, "metric": "ms"}\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'baseline')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'code.py').write_text('value = 2\n')
        (self.repo / 'test_code.py').write_text('assert 2 == 2\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'consolidated')
        self.head = git(self.repo, 'rev-parse', 'HEAD')
        self.verify = self.artifacts / 'verify.json'
        self.bench = self.artifacts / 'bench.json'
        self.evaluation = self.artifacts / 'evaluation.json'
        self.design_path = self.artifacts / 'review.json'
        self.verify.write_text(json.dumps({
            'status': 'PASS', 'workload': {'x': 1},
            'checks': [{'status': 'PASS', 'category': 'forward'}],
            'required_categories': ['forward'], 'code_commit': self.head}))
        self.bench.write_text(json.dumps({
            'outcome': 'FASTER', 'measured_without_profiler': True,
            'metric_scope': 'application', 'workload': {'x': 1}, 'code_commit': self.head}))
        self.write_evaluation()
        self.design = {
            'base_commit': self.base, 'final_commit': self.head,
            'reviewer': 'independent reviewer',
            'summary': 'The final implementation uses one clear interface and was reviewed against the original source.',
            'public_api': {
                'before': 'code.py exported value before consolidation',
                'after': 'code.py continues to export value',
                'compatibility': 'No public API or call-site changes',
            },
            'changed_files': [
                {'path': 'code.py', 'purpose': 'Change implementation',
                 'necessity': 'Required for validated behavior'},
                {'path': 'test_code.py', 'purpose': 'Test required behavior',
                 'necessity': 'Protect original semantic contract'},
            ],
            'simpler_alternatives': [
                {'option': 'Retain original code.py function',
                 'tradeoff': 'Avoids added complexity but does not deliver required speedup',
                 'evidence': 'Application benchmark compares original and replacement',
                 'disposition': 'rejected'}],
            'checks': {name: {
                'status': 'PASS',
                'evidence': f'Inspected {name}: checked code.py implementation and test_code.py behavior in the full diff.',
                'locations': ['code.py', 'test_code.py'],
            } for name in REVIEW_CHECKS},
        }

    def write_evaluation(self):
        verification = json.loads(self.verify.read_text())
        benchmark = json.loads(self.bench.read_text())
        from prof_tools.acceptance import assess
        self.evaluation.write_text(json.dumps({"schema_version": 1,
            "code_commit": self.head, "verification": verification,
            "workload_contract_sha256": hashlib.sha256((self.repo / 'perf' / 'workload.json').read_bytes()).hexdigest(),
            "performance": benchmark, "assessment": assess(verification, benchmark)}))

    def review(self):
        self.design_path.write_text(json.dumps(self.design))
        return integration_review(self.repo, self.base, self.evaluation, self.design_path)

    def test_complete_semantic_review_passes(self):
        report = self.review()
        self.assertEqual(report['status'], 'READY_FOR_LABCOAT_INTEGRATION')
        self.assertEqual(report['diff']['files_changed'], 2)
        self.assertEqual(report['design_review']['changed_files_accounted_for'], 2)
        self.assertEqual(len(report['design_review']['dimensions']), 10)

    def test_finalization_cli_consumes_one_evaluation_artifact(self):
        import sys
        self.design_path.write_text(json.dumps(self.design))
        result_path = self.artifacts / 'final.json'
        proc = subprocess.run([sys.executable, '-m', 'prof_tools.cli', 'finalize',
             '--repo', str(self.repo), '--base', self.base,
             '--evaluation', str(self.evaluation), '--design-review', str(self.design_path),
             '--out', str(result_path)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(proc.stdout)['status'], 'READY_FOR_LABCOAT_INTEGRATION')
        self.assertEqual(json.loads(result_path.read_text())['final_commit'], self.head)

    def test_old_six_check_attestation_fails(self):
        self.design['checks'] = dict(list(self.design['checks'].items())[:6])
        result = self.review()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertTrue(any('ten' in item or 'required semantic' in item for item in result['blockers']))

    def test_repeated_generic_evidence_is_rejected(self):
        for check in self.design['checks'].values():
            check['evidence'] = 'reviewed diff and tests'
        self.assertIn('reused boilerplate', ' '.join(self.review()['blockers']))

    def test_nonexistent_source_citation_is_rejected(self):
        self.design['checks']['conceptual_economy']['locations'] = ['untracked.py']
        self.assertIn('missing or untracked', ' '.join(self.review()['blockers']))

    def test_unaccounted_file_is_rejected(self):
        self.design['changed_files'] = self.design['changed_files'][:1]
        self.assertIn('every file', ' '.join(self.review()['blockers']))

    def test_missing_api_and_alternative_is_rejected(self):
        self.design['public_api'].pop('before')
        self.design['simpler_alternatives'] = []
        blockers = ' '.join(self.review()['blockers'])
        self.assertIn('before/after API', blockers)
        self.assertIn('simpler alternative', blockers)

    def test_failed_semantic_contract_blocks(self):
        self.design['checks']['semantic_preservation']['status'] = 'FAIL'
        self.assertIn('semantic_preservation', ' '.join(self.review()['blockers']))

    def test_wrong_evidence_revision_blocks(self):
        report = json.loads(self.bench.read_text())
        report['code_commit'] = self.base
        self.bench.write_text(json.dumps(report))
        self.write_evaluation()
        self.assertIn('exact consolidated commit', ' '.join(self.review()['blockers']))

    def test_missing_frozen_contract_digest_blocks(self):
        evaluation = json.loads(self.evaluation.read_text())
        evaluation.pop('workload_contract_sha256')
        self.evaluation.write_text(json.dumps(evaluation))
        self.assertIn('frozen workload contract', ' '.join(self.review()['blockers']))

    def test_changed_frozen_contract_blocks_even_with_matching_final_evidence(self):
        (self.repo / 'perf' / 'workload.json').write_text('{"schema_version": 1, "metric": "easier_ms"}\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'change contract')
        self.head = git(self.repo, 'rev-parse', 'HEAD')
        self.design['final_commit'] = self.head
        self.design['changed_files'].append({'path': 'perf/workload.json',
            'purpose': 'Change metric', 'necessity': 'Deliberately test moving goalposts'})
        for location in (self.verify, self.bench):
            report = json.loads(location.read_text())
            report['code_commit'] = self.head
            location.write_text(json.dumps(report))
        self.write_evaluation()
        self.assertIn('frozen workload contract changed', ' '.join(self.review()['blockers']))

    def test_dirty_working_tree_is_rejected(self):
        (self.repo / 'code.py').write_text('value = 3\n')
        with self.assertRaisesRegex(ValueError, 'clean committed'):
            self.review()


if __name__ == '__main__':
    unittest.main()
