import cProfile
import json
import subprocess
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

from prof_tools.trace_diagnostics import diagnose, compare_traces, inspect_schema, step_diagnostics, export_events
from prof_tools.cpu_compare import compare_stacks, compare_pstats


class TraceDiagnosticsTest(unittest.TestCase):
    def make_nvidia(self, p, extra=0):
        conn = sqlite3.connect(p)
        conn.executescript('''
        CREATE TABLE StringIds(id INTEGER, value TEXT);
        INSERT INTO StringIds VALUES (1,'gemm'),(2,'ncclAllReduce'),(3,'cudaLaunchKernel'),(4,'cudaDeviceSynchronize');
        CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL(start INTEGER,end INTEGER,shortName INTEGER,deviceId INTEGER,streamId INTEGER,correlationId INTEGER);
        CREATE TABLE CUPTI_ACTIVITY_KIND_RUNTIME(start INTEGER,end INTEGER,nameId INTEGER,correlationId INTEGER);
        CREATE TABLE CUPTI_ACTIVITY_KIND_MEMCPY(start INTEGER,end INTEGER,bytes INTEGER,deviceId INTEGER,streamId INTEGER,correlationId INTEGER,copyKind INTEGER);
        CREATE TABLE NVTX_EVENTS(start INTEGER,end INTEGER,text TEXT);
        INSERT INTO NVTX_EVENTS VALUES (0,200,'step');
        INSERT INTO CUPTI_ACTIVITY_KIND_RUNTIME VALUES (0,10,3,10),(150,170,4,99);
        INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES (20,100,1,0,1,10),(60,120,2,0,2,11);
        INSERT INTO CUPTI_ACTIVITY_KIND_MEMCPY VALUES (80,130,4096,0,3,12,1);
        ''')
        if extra:
            conn.execute('INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES (130,?,?,0,1,15)', (160+extra, 1))
        conn.commit(); conn.close()

    def test_kernel_memcpy_overlap_collective_and_latency(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'n.sqlite'; self.make_nvidia(db)
            r = diagnose(db, range_name='step')
            d = r['per_device']['0']
            self.assertEqual(d['kernel_busy_union_ns'], 100)
            self.assertEqual(d['copy_busy_union_ns'], 50)
            self.assertEqual(d['kernel_copy_overlap_ns'], 40)
            self.assertEqual(d['any_gpu_activity_union_ns'], 110)
            self.assertEqual(d['compute_collective_overlap_ns'], 40)
            self.assertEqual(d['observed_no_activity_ns'], 90)
            self.assertEqual(r['launch_queue_diagnostics']['median_launch_to_start_ns'], 10)
            self.assertEqual(r['synchronization_api_observations']['calls'], 1)
            self.assertEqual(r['domains']['copy']['top'][0]['calls'], 1)
            self.assertIn('CUPTI_ACTIVITY_KIND_KERNEL', inspect_schema(db)['tables'])
            steps = step_diagnostics(db, 'step')
            self.assertEqual(steps['marker_count'], 1)
            self.assertEqual(steps['host_marker_duration_ns']['median'], 200)

    def test_jsonl_export(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'n.sqlite'; out = Path(t)/'events.jsonl'
            self.make_nvidia(db)
            report = export_events(db, out, kind='kernel', start_ns=30, end_ns=90)
            self.assertEqual(report['exported_events'], 2)
            events = [json.loads(line) for line in out.read_text().splitlines()]
            self.assertEqual(events[0]['start'], 30)
            self.assertEqual(events[0]['end'], 90)
            with self.assertRaises(FileExistsError):
                export_events(db, out)

    def test_compare(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)/'base.sqlite'; candidate = Path(t)/'new.sqlite'
            self.make_nvidia(base); self.make_nvidia(candidate, 20)
            report = compare_traces(base, candidate)
            self.assertTrue(any(r['candidate_calls'] != r['baseline_calls'] for r in report['kernel_changes']))

    def test_rocpd_views_and_domains(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'rocm.db'; c = sqlite3.connect(db)
            c.executescript('''
            CREATE VIEW kernels AS SELECT 'mfma' AS name, 10 AS start_time, 80 AS end_time, 0 AS agent_abs_index, 1 AS stream_id, 3 AS correlation_id;
            CREATE VIEW memory_copies AS SELECT 'H2D' AS name, 40 AS start_time, 100 AS end_time, 8192 AS size, 0 AS dst_agent_abs_index;
            CREATE VIEW regions_and_samples AS SELECT 'hipLaunchKernel' AS name, 0 AS start_time, 5 AS end_time, 3 AS correlation_id, 'HIP_RUNTIME_API' AS category;
            ''')
            c.close()
            r = diagnose(db)
            self.assertEqual(r['per_device']['0']['kernel_copy_overlap_ns'], 40)
            self.assertEqual(r['launch_queue_diagnostics']['median_launch_to_start_ns'], 5)
            self.assertEqual(r['domains']['copy']['top'][0]['sum_ns'], 60)
            self.assertEqual(r['domains']['api']['top'][0]['name'], 'hipLaunchKernel')

    def test_missing_optional_domains_are_visible(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'n.sqlite'; c = sqlite3.connect(db)
            c.executescript('''CREATE TABLE StringIds(id INT,value TEXT);
            INSERT INTO StringIds VALUES (1,'gemm');
            CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL(start INT,end INT,shortName INT);
            INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES(0,10,1);''')
            c.close()
            r = diagnose(db)
            self.assertIn('CUPTI_ACTIVITY_KIND_MEMCPY', r['missing_domains'])
            self.assertNotIn('copy', r['domains'])
            self.assertEqual(r['per_device']['unknown']['kernel_busy_union_ns'], 10)

    def test_cli_trace_report_and_jsonl(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'n.sqlite'; output = Path(t)/'report.json'; events = Path(t)/'all.jsonl'
            self.make_nvidia(db)
            for option in (['diagnose', '--trace', str(db), '--out', str(output)],
                           ['inspect', '--kind', 'trace-events', '--file', str(db), '--out', str(events)],
                           ['diagnose', '--trace', str(db), '--marker', 'step']):
                proc = subprocess.run([sys.executable, '-m', 'prof_tools.cli', *option],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('gpu_trace', json.loads(output.read_text())['sources'])
            self.assertGreater(len(events.read_text().splitlines()), 2)

    def test_pstats_diff(self):
        with tempfile.TemporaryDirectory() as t:
            a = Path(t)/'a.pstats'; b = Path(t)/'b.pstats'
            for file, repeat in ((a, 2), (b, 3)):
                profile = cProfile.Profile()
                profile.runcall(lambda: sum(sum(range(100)) for _ in range(repeat)))
                profile.dump_stats(str(file))
            result = compare_pstats(a, b)
            self.assertTrue(result['changes'])

    def test_stack_diff(self):
        with tempfile.TemporaryDirectory() as t:
            a = Path(t)/'a.folded'; b = Path(t)/'b.folded'
            a.write_text('main;a 7\nmain;b 3\n'); b.write_text('main;a 4\nmain;b 6\n')
            r = compare_stacks(a, b)
            self.assertAlmostEqual(next(x['delta_exclusive_fraction'] for x in r['changes'] if x['frame']=='a'), -0.3)

if __name__ == '__main__':
    unittest.main()
