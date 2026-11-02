from contextlib import contextmanager
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from prof_tools.auto_diagnosis import auto_diagnose
from prof_tools.counters import csv_counters, counter_summary, compare_counter_reports, sqlite_counters
from prof_tools.dependencies import analyze_dependency_graph
from prof_tools.distributed import analyze_ranks
from prof_tools.gpu_dependencies import analyze_gpu_dependencies
from prof_tools.intervals import merge, duration, subtract, intersection_duration
from prof_tools.torch_trace import analyze_torch_trace


@contextmanager
def connected(path):
    con = sqlite3.connect(path)
    try:
        with con:
            yield con
    finally:
        con.close()


def make_trace(path):
    with connected(path) as con:
        con.executescript('''
        CREATE TABLE StringIds(id INT,value TEXT);
        INSERT INTO StringIds VALUES (1,'matmul'),(2,'ncclAllReduce'),(3,'cudaLaunchKernel'),(4,'cudaStreamSynchronize');
        CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL(start INT,end INT,shortName INT,deviceId INT,streamId INT,correlationId INT,globalPid INT);
        INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES (10,60,1,0,1,11,100),(40,80,2,0,2,12,100);
        CREATE TABLE CUPTI_ACTIVITY_KIND_RUNTIME(start INT,end INT,nameId INT,correlationId INT,globalPid INT);
        INSERT INTO CUPTI_ACTIVITY_KIND_RUNTIME VALUES (0,5,3,11,100),(5,9,3,12,100),(70,90,4,13,100);
        CREATE TABLE CUPTI_ACTIVITY_KIND_CUDA_EVENT(eventSyncId INT,streamId INT);
        INSERT INTO CUPTI_ACTIVITY_KIND_CUDA_EVENT VALUES (991,1);
        CREATE TABLE CUPTI_ACTIVITY_KIND_SYNCHRONIZATION(eventSyncId INT,streamId INT);
        INSERT INTO CUPTI_ACTIVITY_KIND_SYNCHRONIZATION VALUES (991,2);
        CREATE TABLE NVTX_EVENTS(start INT,end INT,text TEXT);
        INSERT INTO NVTX_EVENTS VALUES (0,100,'step');
        ''')


def capture(path, **overrides):
    data = {'vendor':'nvidia','architecture':'sm_90a','profiler':'ncu','profiler_version':'2026.1',
            'command':'ncu --csv --page raw kernel', 'replay_mode':'kernel replay',
            'workload_id':'same-inputs', 'device_id':'GPU-uuid',
            'conditions': {'shape':[128,128,128], 'dtype':'bf16'}}
    data.update(overrides)
    path.write_text(json.dumps(data))


class TypedCounters(unittest.TestCase):
    def test_ncu_notices_headers_and_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'metrics.csv'; p.write_text('==PROF== Connected\nID,Kernel Name,Metric Name,Metric Unit,Metric Value\n1,mm,sm__throughput.avg.pct_of_peak_sustained_elapsed,%,74.5\n1,mm,dram__bytes.sum,byte,4096\n')
            rows=csv_counters(p)
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0].kernel,'mm')
            self.assertEqual(rows[0].unit,'%')
            self.assertEqual(rows[1].value,4096)

    def test_missing_units_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.csv';p.write_text('Metric Name,Metric Value\nfoo,4\n')
            with self.assertRaises(ValueError): csv_counters(p)

    def test_rocm_csv_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'r.csv';p.write_text('Metric_ID,Result,Units,Dispatch\nSQ_VALU_UTIL,50,%,7\n')
            rows=csv_counters(p, {'metric':'Metric_ID','value':'Result','unit':'Units','dispatch':'Dispatch'})
            self.assertEqual(rows[0].metric,'SQ_VALU_UTIL')
            self.assertEqual(rows[0].dispatch,'7')

    def test_rocm_sqlite_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'counter.db'
            with connected(db) as con:
                con.executescript('CREATE VIEW metrics AS SELECT "VALU" AS label, 0.75 AS reading, "fraction" AS units;')
            rows=sqlite_counters(db, 'metrics', {'metric':'label','value':'reading','unit':'units'})
            self.assertEqual(rows[0].value,0.75)
            with self.assertRaises(ValueError): sqlite_counters(db,'metrics',{})

    def test_counter_provenance_and_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            a=tmp/'a.csv'; b=tmp/'b.csv'; ca=tmp/'ca.json';cb=tmp/'cb.json'
            a.write_text('ID,Kernel Name,Metric Name,Metric Unit,Metric Value\n2,gemm,dram__bytes.sum,byte,500\n')
            b.write_text('ID,Kernel Name,Metric Name,Metric Unit,Metric Value\n2,gemm,dram__bytes.sum,byte,350\n')
            capture(ca);capture(cb)
            self.assertEqual(counter_summary(a,ca)['distinct_metrics'],1)
            self.assertEqual(compare_counter_reports(a,b,ca,cb)['changes'][0]['delta'],-150)
            capture(cb, architecture='sm_100')
            with self.assertRaisesRegex(ValueError, 'not comparable'):
                compare_counter_reports(a,b,ca,cb)

    def test_duplicated_keys_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a.csv';b=root/'b.csv';ma=root/'ma.json';mb=root/'mb.json'
            header='ID,Kernel Name,Metric Name,Metric Unit,Metric Value\n'
            a.write_text(header+'1,mm,x,%,10\n1,mm,x,%,15\n');b.write_text(header+'1,mm,x,%,9\n')
            capture(ma);capture(mb)
            compare=compare_counter_reports(a,b,ma,mb)
            self.assertEqual(compare['matched'],0)
            self.assertEqual(compare['ambiguous_keys'],1)


class Timeline(unittest.TestCase):
    def test_interval_pure_functions(self):
        self.assertEqual(merge([(3,7),(1,5),(8,9)]),[(1,7),(8,9)])
        self.assertEqual(duration([(1,3),(2,6)]),5)
        self.assertEqual(subtract([(0,10)],[(2,4),(6,9)]),[(0,2),(4,6),(9,10)])
        self.assertEqual(intersection_duration([(0,10)],[(2,4),(6,9)]),5)

    def test_torch_flow_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.json'
            events=[
                {'ph':'X','pid':1,'tid':2,'cat':'cpu_op','name':'aten::mm','ts':0,'dur':100},
                {'ph':'X','pid':1,'tid':3,'cat':'kernel','name':'gemm','ts':25,'dur':50},
                {'ph':'s','pid':1,'tid':2,'id':77,'ts':10},
                {'ph':'f','pid':1,'tid':3,'id':77,'ts':30},
            ]
            p.write_text(json.dumps({'traceEvents':events}))
            report=analyze_torch_trace(p)
            self.assertEqual(report['flow_attribution']['matched'],1)
            self.assertEqual(report['gpu_union_ns'],50000)
            self.assertEqual(report['flow_attribution']['samples'][0]['cpu_op'],'aten::mm')

    def test_gpu_dependency_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'n.sqlite';make_trace(p)
            r=analyze_gpu_dependencies(p)
            self.assertEqual(r['cuda_event_dependencies']['matched_event_sync_ids'],1)
            self.assertEqual(len(r['per_stream_observations']),2)

    def test_rank_manifest_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i in (0,1):make_trace(root/f'r{i}.db')
            manifest={'step_marker':'step', 'ranks':[
                {'rank':0,'trace':'r0.db','clock_domain':'ptp-A','clock_offset_ns':100,'alignment_error_ns':5},
                {'rank':1,'trace':'r1.db','clock_domain':'ptp-A','clock_offset_ns':0,'alignment_error_ns':5}],
                'collectives':[
                {'rank':0,'sequence_id':'3','kind':'all_reduce','start_ns':40,'end_ns':80},
                {'rank':1,'sequence_id':'3','kind':'all_reduce','start_ns':10,'end_ns':70}]}
            path=root/'ranks.json';path.write_text(json.dumps(manifest))
            data=analyze_ranks(path)
            self.assertEqual(data['collectives'][0]['start_skew_ns'],130)
            self.assertEqual(data['collectives'][0]['slowest_observed_duration_rank'],'1')
            self.assertEqual(data['cross_rank_clock_alignment'],'explicit')
            del manifest['ranks'][1]['clock_offset_ns']
            path.write_text(json.dumps(manifest))
            self.assertIsNone(analyze_ranks(path)['collectives'][0]['start_skew_ns'])

    def test_dependency_dag_and_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'dag.json'
            doc={'nodes':[{'id':'a','duration_ns':10},{'id':'b','duration_ns':30},{'id':'c','duration_ns':20}],
                 'edges':[{'from':'a','to':'b','evidence':'stream order'}, {'from':'a','to':'c','evidence':'explicit event wait'}]}
            p.write_text(json.dumps(doc))
            self.assertEqual(analyze_dependency_graph(p)['longest_weighted_path_ns'],40)
            doc['edges'].append({'from':'b','to':'a','evidence':'bad loop'})
            p.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'cycle'):analyze_dependency_graph(p)

    def test_unified_cli_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            db=root/'trace.db';make_trace(db)
            cap=root/'capture.json';capture(cap)
            metrics=root/'counter.csv';metrics.write_text('ID,Kernel Name,Metric Name,Metric Unit,Metric Value\n1,mm,x,%,50\n')
            report=auto_diagnose(trace=db,counter_file=metrics,counter_manifest=cap,marker='step')
            self.assertIn('gpu_dependency_evidence',report['sources'])
            self.assertIn('steps',report['sources'])
            self.assertIn('counters',report['sources'])
            self.assertTrue(any(f['code']=='COLLECTIVE_ACTIVITY' for f in report['findings']))
            args=['diagnose','--trace',str(db),'--counter-file',str(metrics),'--counter-manifest',str(cap),'--marker','step']
            proc=subprocess.run([sys.executable,'-m','prof_tools.cli',*args],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['schema_version'],1)


    def test_nvidia_counter_hypothesis_and_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cap=root/'capture.json';capture(cap)
            csv_file=root/'metrics.csv'
            csv_file.write_text('ID,Kernel Name,Metric Name,Metric Unit,Metric Value\n'
                                '1,mm,sm__throughput.avg.pct_of_peak_sustained_elapsed,%,25\n'
                                '1,mm,dram__throughput.avg.pct_of_peak_sustained_elapsed,%,89\n')
            report=auto_diagnose(counter_file=csv_file,counter_manifest=cap)
            self.assertTrue(any(f['code']=='HIGH_DRAM_LOW_SM_THROUGHPUT' for f in report['findings']))
            md=root/'report.md'
            proc=subprocess.run([sys.executable,'-m','prof_tools.cli','diagnose','--counter-file',str(csv_file),
                                '--counter-manifest',str(cap),'--markdown',str(md)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn('HIGH_DRAM_LOW_SM_THROUGHPUT',md.read_text())

    def test_cuda_graph_launch_not_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'graph.sqlite';make_trace(p)
            with connected(p) as con:
                con.execute('ALTER TABLE CUPTI_ACTIVITY_KIND_KERNEL ADD COLUMN graphNodeId INT')
                con.execute('UPDATE CUPTI_ACTIVITY_KIND_KERNEL SET graphNodeId=19 WHERE correlationId=11')
            from prof_tools.trace_diagnostics import diagnose
            result=diagnose(p)
            self.assertEqual(result['launch_queue_diagnostics']['matched_unique_launches'],1)
            self.assertEqual(result['launch_queue_diagnostics']['ambiguous_or_unmatched_launches'],1)

    def test_reject_incompatible_clock_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            make_trace(root/'r0.db');make_trace(root/'r1.db')
            p=root/'ranks.json'
            p.write_text(json.dumps({'ranks':[
                {'rank':0,'trace':'r0.db','clock_domain':'clock-A','clock_offset_ns':0,'alignment_error_ns':1},
                {'rank':1,'trace':'r1.db','clock_domain':'clock-B','clock_offset_ns':0,'alignment_error_ns':1}]}))
            with self.assertRaisesRegex(ValueError,'clock_domain'):
                analyze_ranks(p)

if __name__=='__main__':
    unittest.main()
