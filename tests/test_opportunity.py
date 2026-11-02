import unittest
from prof_tools.opportunity import FAMILIES, opportunity_map


def example():
    return {"schema_version": 1,
            "objective": {"metric_scope": "application", "direction": "lower", "memory": {"mode": "secondary"}},
            "workloads": [{"id": "small", "weight": .6, "baseline_ms": 100},
                          {"id": "large", "weight": .4, "baseline_ms": 200}],
            "family_screening": {k: {"status": "considered", "reason": "examined dataflow"} for k in FAMILIES},
            "candidates": [{"id": "compute", "family": "kernel", "mechanism": "tile weights",
                "falsification_test": "profile exposed time", "cost": "low",
                "per_workload": {"small": {"exposed_ms": 2, "speedup_ceiling": 2},
                                 "large": {"exposed_ms": 4, "speedup_ceiling": 2}}},
                {"id": "graph", "family": "dataflow", "mechanism": "eliminate redundant stage",
                "falsification_test": "check computational graph", "cost": "medium",
                "per_workload": {"small": {"exposed_ms": 20, "speedup_ceiling": 2},
                                 "large": {"exposed_ms": 40, "speedup_ceiling": 2}}}]}


class OpportunityTests(unittest.TestCase):
    def test_weighted_impact_and_branch_diversity(self):
        r = opportunity_map(example())
        self.assertEqual(r['initial_branches'], ['graph', 'compute'])
        self.assertAlmostEqual(r['candidates'][0]['conditional_weighted_max_savings_ms'], 14)
        self.assertAlmostEqual(r['candidates'][1]['conditional_weighted_max_savings_ms'], 1.4)

    def test_do_not_invent_exposed_latency(self):
        s = example()
        del s['candidates'][0]['per_workload']['large']
        r = opportunity_map(s)
        self.assertIsNone(next(c for c in r['candidates'] if c['id'] == 'compute')['conditional_weighted_max_savings_ms'])

    def test_memory_is_secondary_except_guardrail(self):
        s = example()
        s['objective']['memory'] = {"mode": "constraint", "limit_bytes": 1000}
        s['candidates'][1]['projected_peak_bytes'] = 2000
        result = opportunity_map(s)
        self.assertEqual(result['initial_branches'], ['compute'])
        self.assertEqual(next(c for c in result['candidates'] if c['id'] == 'graph')['memory_feasibility'], 'FAIL')

    def test_reject_incomplete_screening(self):
        s = example()
        del s['family_screening']['algebra']
        with self.assertRaisesRegex(ValueError, 'seven'):
            opportunity_map(s)

if __name__ == '__main__':
    unittest.main()
