"""Optional PyTorch-only correctness assertions for project test commands.

Nothing here is called in a timed benchmark. This helper checks pure callables
with tensor inputs/outputs and input VJPs, not arbitrary model training semantics.
"""


def assert_torch_equivalent(reference, candidate, inputs, *, atol, rtol, seed=0, check_gradients=True):
    """Assert forward and input-gradient agreement on identical independent inputs.

    Inputs may be nested tuples/lists/dicts of tensors and immutable scalars.
    Float tensors requiring gradients retain that flag. State, optimizer updates,
    collective behavior and statistical equivalence need separate project tests.
    """
    import torch

    if atol < 0 or rtol < 0:
        raise ValueError("tolerances must be nonnegative")

    def clone(value):
        if isinstance(value, torch.Tensor):
            return value.detach().clone().requires_grad_(value.requires_grad)
        if isinstance(value, tuple):
            return tuple(clone(v) for v in value)
        if isinstance(value, list):
            return [clone(v) for v in value]
        if isinstance(value, dict):
            return {k: clone(v) for k, v in value.items()}
        return value

    def tensors(value):
        if isinstance(value, torch.Tensor):
            return [value]
        if isinstance(value, (tuple, list)):
            return [t for v in value for t in tensors(v)]
        if isinstance(value, dict):
            return [t for k in sorted(value) for t in tensors(value[k])]
        return []

    def close(actual, expected, path):
        if isinstance(expected, torch.Tensor):
            if not isinstance(actual, torch.Tensor):
                raise AssertionError(f"{path}: output type changed")
            try:
                torch.testing.assert_close(actual, expected, atol=atol, rtol=rtol, equal_nan=False,
                                           check_dtype=True, check_device=True)
            except AssertionError as exc:
                raise AssertionError(f"{path}: {exc}") from exc
        elif isinstance(expected, dict):
            if not isinstance(actual, dict) or actual.keys() != expected.keys():
                raise AssertionError(f"{path}: mapping structure changed")
            for key in expected:
                close(actual[key], expected[key], f"{path}.{key}")
        elif isinstance(expected, (tuple, list)):
            if type(actual) is not type(expected) or len(actual) != len(expected):
                raise AssertionError(f"{path}: sequence structure changed")
            for i, (a, b) in enumerate(zip(actual, expected)):
                close(a, b, f"{path}[{i}]")
        elif type(actual) is not type(expected) or actual != expected:
            raise AssertionError(f"{path}: non-tensor value differs")

    reference_inputs = clone(inputs)
    candidate_inputs = clone(inputs)
    reference_initial = clone(reference_inputs)
    candidate_initial = clone(candidate_inputs)
    cuda_ids = sorted({t.device.index for t in tensors(inputs) if t.device.type == "cuda"})

    def invoke(fn, values):
        with torch.random.fork_rng(devices=cuda_ids):
            torch.manual_seed(seed)
            return fn(*values) if isinstance(values, tuple) else fn(values)

    ref = invoke(reference, reference_inputs)
    cand = invoke(candidate, candidate_inputs)
    close(cand, ref, "outputs")
    close(reference_inputs, reference_initial, "reference_inputs")
    close(candidate_inputs, candidate_initial, "candidate_inputs")

    gradients_compared = 0
    if check_gradients:
        ref_inputs = [t for t in tensors(reference_inputs) if t.requires_grad]
        cand_inputs = [t for t in tensors(candidate_inputs) if t.requires_grad]
        if len(ref_inputs) != len(cand_inputs) or not ref_inputs:
            raise ValueError("input-gradient verification needs corresponding grad-enabled tensor inputs")
        ref_outputs = [t for t in tensors(ref) if t.is_floating_point() or t.is_complex()]
        cand_outputs = [t for t in tensors(cand) if t.is_floating_point() or t.is_complex()]
        if not ref_outputs or len(ref_outputs) != len(cand_outputs):
            raise ValueError("input-gradient verification needs differentiable tensor outputs")
        if any(x.requires_grad != y.requires_grad for x, y in zip(ref_outputs, cand_outputs)):
            raise AssertionError("output gradient availability differs")
        ref_outputs = [t for t in ref_outputs if t.requires_grad]
        cand_outputs = [t for t in cand_outputs if t.requires_grad]
        if not ref_outputs:
            raise AssertionError("neither implementation supplies differentiable outputs")
        # A deterministic non-uniform VJP probe reduces cancellation that a simple sum might hide.
        generators = {}
        probes = []
        for tensor in ref_outputs:
            device = tensor.device
            key = (device.type, device.index)
            if key not in generators:
                generators[key] = torch.Generator(device=device).manual_seed(seed + 1)
            probes.append(torch.randn(tensor.shape, dtype=tensor.dtype, device=device,
                                      generator=generators[key]))
        ref_grads = torch.autograd.grad(ref_outputs, ref_inputs, probes, allow_unused=True)
        cand_grads = torch.autograd.grad(cand_outputs, cand_inputs, probes, allow_unused=True)
        for i, (a, b) in enumerate(zip(cand_grads, ref_grads)):
            if (a is None) != (b is None):
                raise AssertionError(f"input_gradients[{i}]: gradient availability differs")
            if a is not None:
                close(a, b, f"input_gradients[{i}]")
                gradients_compared += 1
    return {"status": "PASS", "output_tensors": len(tensors(ref)),
            "input_gradients": gradients_compared,
            "limitations": "Test on representative shapes; state transitions and stochastic distributions need independent checks."}
