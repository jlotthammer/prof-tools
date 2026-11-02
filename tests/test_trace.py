import sqlite3
import tempfile
import unittest
from pathlib import Path
from prof_tools.trace import union_duration
from prof_tools.trace_diagnostics import diagnose


class TraceTest(unittest.TestCase):
    def test_union(self):
        self.assertEqual(union_duration([(0, 10), (4, 15), (20, 30)]), 25)

    def test_nvidia_schema(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "n.sqlite"
            c = sqlite3.connect(p)
            c.executescript("""CREATE TABLE StringIds (id INT, value TEXT);
            CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL (start INT, end INT, shortName INT, deviceId INT);
            INSERT INTO StringIds VALUES (1, 'gemm');
            INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES (100, 200, 1, 0), (150, 250, 1, 0);
            """)
            c.executescript("CREATE TABLE NVTX_EVENTS (start INT, end INT, text TEXT); INSERT INTO NVTX_EVENTS VALUES (120, 220, 'train_step');")
            c.commit(); c.close()
            r = diagnose(p)
            window = diagnose(p, range_name='train_step')
            self.assertEqual(window['selected_window']['start_ns'], 120)
            self.assertEqual(window['per_device']['0']['kernel_busy_union_ns'], 100)
            self.assertEqual(r["vendor"], "nvidia")
            self.assertEqual(r["per_device"]["0"]["kernel_busy_union_ns"], 150)
            self.assertEqual(r["domains"]["kernel"]["duration_sum_ns"], 200)

    def test_rocpd_schema(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.db"
            c = sqlite3.connect(p)
            c.executescript("""CREATE VIEW kernels AS SELECT 'mfma' AS name, 10 AS start, 30 AS end, 20 AS duration, 0 AS agent_abs_index;
            """)
            c.commit(); c.close()
            r = diagnose(p)
            self.assertEqual(r["vendor"], "amd")
            self.assertEqual(r["per_device"]["0"]["kernel_busy_union_ns"], 20)

    def test_rocpd_duration_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.db"
            c = sqlite3.connect(p)
            c.executescript("CREATE VIEW kernels AS SELECT 'mfma' AS name, 200 AS duration;")
            c.commit(); c.close()
            r = diagnose(p)
            self.assertNotIn("kernel", r["domains"])
            self.assertIn("kernels (no absolute intervals)", r["missing_domains"])

if __name__ == "__main__":
    unittest.main()
