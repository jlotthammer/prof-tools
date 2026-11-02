import unittest
from prof_tools.stats import comparison
from prof_tools.hardware import ridge, gemm_ai, wave_efficiency


class StatisticsTest(unittest.TestCase):
    def test_speedup(self):
        r = comparison([10] * 4, [8] * 4)
        self.assertAlmostEqual(r["geometric_speedup"], 1.25)
        self.assertAlmostEqual(r["speedup_ci"][0], 1.25)

    def test_higher_is_better(self):
        self.assertAlmostEqual(comparison([8, 8], [10, 10], "higher")["geometric_speedup"], 1.25)

    def test_reject_bad_data(self):
        with self.assertRaises(ValueError):
            comparison([0, 1], [1, 1])

    def test_hardware(self):
        self.assertAlmostEqual(ridge("mi300a", "bf16"), 185.0188679245, places=4)
        self.assertAlmostEqual(gemm_ai(900, 900, 900), 300)
        self.assertEqual(wave_efficiency(264, 132)["last_wave_fill"], 1)
        self.assertEqual(wave_efficiency(133, 132)["waves"], 2)

if __name__ == "__main__":
    unittest.main()
