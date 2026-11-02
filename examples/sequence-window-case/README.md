# Optimization campaign acceptance exercise: masked sequence neighborhoods

This is a **real, executable CPU optimization problem**, not a mock timing function. It models per-residue local composition and net charge on ragged biological sequences, with masks for unobserved residues and distinct window radii. The baseline repeatedly scans each neighborhood and performs redundant work. The agent must improve the complete workload without changing *any* computed integer feature.

## Agent-visible source

- `windowbench/data.py`: deterministic public data generator and workload identity.
- `windowbench/baseline.py`: deliberately slow correct implementation.
- `windowbench/candidate.py`: only intended editable optimization target, initially the baseline.
- `windowbench/oracle.py`: simple independent correctness oracle.
- `windowbench/run.py`: process-level application benchmark and complete-output verification envelope.
- `suite.json`: frozen public benchmark distribution and acceptance checks.

No optimized reference or private holdout cases are present in this directory or in the public toolkit ZIP.

## Quick start

```bash
python -m pip install -e /path/to/prof_tools
cd /path/to/prof_tools/examples/sequence-window-case
prof-tools evaluate --spec suite.json --outdir /tmp/sequence-public-baseline
```

The initial candidate is identical to baseline. Expect **correctness PASS** but **performance BLOCKED**. This is a successful negative control. A candidate that returns constant/random outputs must fail complete-output verification even if it is extremely fast.

Explore multiple families from the real dataflow: algebraic/algorithmic reduction of redundant work; representation and locality; Python/NumPy/C++ acceleration; streaming; and algorithmic precomputation. Keep memory secondary unless capacity becomes binding. Before implementing, map the relevant algorithmic complexity and full-stage timing, not only the inner loop.

For CPU profiling:

```bash
python -m cProfile -o /tmp/sequence-baseline.pstats -m windowbench.run --case medium --implementation baseline
prof-tools diagnose --cpu-profile /tmp/sequence-baseline.pstats --top 20
```

## Private holdout

The **separately distributed** private evaluator contains an optimized reference and additional hidden cases. Store it in a separate private repository/service with access controls, never in an `unread/` directory inside the coding agent's checkout. The included trusted local evaluator is not a sandbox; for a genuinely untrusted agent run the candidate in an isolated environment without access to private evaluator files/credentials.

Use the private holdout **once** after choosing the final candidate. The private score is not a replacement for repeated public experiments or final-commit correctness verification.

## Desired output

A separate Labcoat note for each meaningful hypothesis, measured application speedups and constraints, a clean final patch from original base, independently verified correctness, and ten-dimensional architecture review. Do not merge exploratory branches directly.
