import unittest

try:
    import torch
except ImportError:
    torch = None

from prof_tools.torch_checks import assert_torch_equivalent


@unittest.skipIf(torch is None, 'PyTorch is an optional dependency')
class TorchChecksTests(unittest.TestCase):
    def test_equivalent_forward_and_gradient(self):
        t = torch.arange(1, 5, dtype=torch.float64).requires_grad_()
        r = assert_torch_equivalent(lambda x: x * (x + 2),
                                    lambda x: x * x + 2 * x,
                                    (t,), atol=1e-10, rtol=1e-10)
        self.assertEqual(r['input_gradients'], 1)

    def test_fake_fast_constant_fails(self):
        t = torch.arange(1, 5, dtype=torch.float32).requires_grad_()
        with self.assertRaises(AssertionError):
            assert_torch_equivalent(lambda x: x.square(), lambda x: torch.rand_like(x),
                                    (t,), atol=0, rtol=0)

    def test_same_forward_wrong_gradient_fails(self):
        t = torch.arange(1, 5, dtype=torch.float64).requires_grad_()
        with self.assertRaisesRegex(AssertionError, 'input_gradients'):
            assert_torch_equivalent(lambda x: x.square(), lambda x: x.detach() * x,
                                    (t,), atol=0, rtol=0)

    def test_input_mutation_fails(self):
        t = torch.arange(1, 5, dtype=torch.float32)
        def mutating(x):
            x.add_(1)
            return x
        with self.assertRaisesRegex(AssertionError, 'candidate_inputs'):
            assert_torch_equivalent(lambda x: x + 1, mutating, (t,), atol=0, rtol=0,
                                    check_gradients=False)

if __name__ == '__main__':
    unittest.main()
