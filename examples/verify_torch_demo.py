#!/usr/bin/env python3
"""Optional PyTorch assertion adapter to use in a verification `type: test` case."""
import torch
from prof_tools.torch_checks import assert_torch_equivalent


def main():
    input_tensor = torch.arange(1, 1025, dtype=torch.float64).requires_grad_()
    result = assert_torch_equivalent(
        lambda x: x * (x + 2),
        lambda x: x.square() + 2 * x,
        (input_tensor,), atol=1e-10, rtol=1e-10,
    )
    print(result)


if __name__ == '__main__':
    main()
