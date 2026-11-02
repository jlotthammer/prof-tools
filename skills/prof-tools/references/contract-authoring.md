# Agent-owned workload and opportunity contracts

This reference is for the **optimization agent**, not a setup task for the user. A normal request is “Optimize this repository for representative training throughput without changing its behavior; use Labcoat.” The user should never be asked to hand-write `workload.json` or `opportunities.json`.

The CLI is a deterministic validator and executor. It does **not** use a language model to guess numerical requirements or generate benchmark code. You, the invoking agent, must do the repository investigation and author the adapters and contracts.

## 1. Discover the actual contract

- Read project instructions, public interfaces, existing tests, example commands, launch scripts, production configurations, dataset metadata, device/topology constraints and recent Labcoat experiments. Identify the complete operation the user values: training step, request, batch, simulation, etc.
- Prefer actual workload frequencies and shape distributions. If weights are unknown, explain and defend a provisional distribution; do not claim it represents production. Include boundaries and important rare regimes even if their weights are small. Keep the independent final confirmation set separate from exploratory measurements.
- Establish the **required semantics**: output tensors, dtypes/shapes, mutations and state, gradients, random distributions, convergence, numerical tolerances, error behavior, synchronization, distributed invariants and input provenance. Reuse a trusted oracle or construct an independently understandable small reference plus domain invariants. Do not compare an implementation only to itself, weaken tolerances to pass, or hide unsupported checks.
- Capture environment and baseline performance before optimizing. Preserve timing measurement methodology and actual inputs. Memory is a secondary measurement unless a specified capacity/operational constraint binds.
- If information needed to establish correctness or the objective is genuinely absent, ask the user **one focused decision**, rather than inventing a scientific tolerance, a workload distribution, or a performance target. Proceed with explicitly labeled exploratory profiling when only confirmatory evidence is blocked.

## 2. Author the *one* project workload contract

Create a source-controlled `perf/workload.json` and the smallest necessary benchmark/output adapters, using the exact supported schema in `examples/sequence-window-case/suite.json` (source distribution). The agent owns this authoring; the user does not. Prefer adapting existing project tests and entrypoints over building a separate miniature application.

Minimal illustrative structure (commands and cases are project-specific):

```json
{
  "schema_version": 1,
  "metric": "step_ms",
  "direction": "lower",
  "pairs": 6,
  "warmup": 1,
  "max_case_regression": 0.05,
  "workloads": [
    {
      "id": "representative",
      "weight": 1.0,
      "workload": {"case": "representative", "seed": 23, "precision": "bf16"},
      "baseline": ["python", "-m", "myapp.perf_case", "--impl", "baseline"],
      "candidate": ["python", "-m", "myapp.perf_case", "--impl", "candidate"],
      "verification": {
        "reference": ["python", "-m", "myapp.perf_case", "--impl", "oracle", "--output", "{output}"],
        "baseline": ["python", "-m", "myapp.perf_case", "--impl", "baseline", "--output", "{output}"],
        "candidate": ["python", "-m", "myapp.perf_case", "--impl", "candidate", "--output", "{output}"],
        "atol": 0.0001,
        "rtol": 0.0001
      }
    }
  ]
}
```

Numbers above demonstrate the schema; **they are not default scientific tolerances, benchmark weights, or duration requirements**. Derive actual values from the application. Add required `checks` / `required_categories` for gradients, mutations, invariants, distributions, safety and distributed behavior when applicable. For numerical comparisons each command must export a JSON object with matching `workload`, `input_id` and named typed `tensors` (see `examples/sequence-window-case/windowbench/run.py`). Timing commands must emit exactly one `PROF_TOOLS_RESULT=<JSON>` line with `workload`, `input_id`, `output_digest` and a positive metric in `metrics`. The output fingerprint must match an independently verified full output for the same deterministic input. Use separate statistical or behavioral oracles for stochastic outputs when exact digest comparison is inappropriate.

Validate without performing the entire expensive suite:

```bash
python -c 'import json; from prof_tools.suite import validate_suite; validate_suite(json.load(open("perf/workload.json")))'
```

All contract authoring and baseline commits take place in a separate, independent Git clone of the original source. First inspect the original source Git status: a clone does not include uncommitted work. Preserve and apply a deliberate patch for necessary pre-existing changes to the preparation checkout; never silently drop or attribute them to an optimization. Use `git clone --no-local --no-hardlinks` outside the original repository and remove its `origin` remote before making changes; no experimental or benchmark-preparation commit belongs in the source repository. Run the original unoptimized candidate and verify that the contract detects a deliberately wrong output, bad input identity and any mandatory project-specific invariant. Establish that the baseline executes the intended code path. Commit the contract, adapters and tests **before** freezing the original `base_commit`; this committed version defines the baseline for all exploration and final confirmation. A revised correctness criterion or workload changes the experiment and requires a new documented baseline and Labcoat hypothesis—not a silent edit to a running campaign.

During evaluation from the project checkout, the conventional command is:

```bash
prof-tools evaluate --outdir /path/outside/repo/experiment-evidence
```

By default it reads `perf/workload.json`. The optional `--spec` exists for projects with an existing committed alternative. Store evidence outside the source checkout so the clean-tree and worktree gates still work.

## 3. Diagnose, then author the opportunity map

Analyze real code and representative traces before enumerating fixes. Screen every family **algebra, dataflow, scheduling, memory, library, kernel, distributed**, recording a reasoned `considered` or `ruled_out`. For each selected candidate provide a concrete mechanism, cost, and cheap falsification test. Include the measured per-workload baseline durations and the same weights/identities as the frozen performance contract. Report exposed critical-path time as **unknown** unless causally supported. Do not treat total kernel/collective duration as exposed time.

The supported shape is illustrated by `examples/opportunities.sample.json` and `examples/sequence-window-case/opportunities.example.json`. Write this derived artifact under the campaign's **external** output directory, for example `../perf-evidence/opportunities.json`; it is not another project configuration file, and should not dirty the original checkout.

Validate its semantics before creating branches:

```bash
python -c 'from prof_tools.opportunity import analyze_opportunities; analyze_opportunities("../perf-evidence/opportunities.json")'
```

Then invoke the campaign adapter using the generated path:

```bash
prof-tools campaign start --repo <isolated-preparation-clone> --base "$(git rev-parse HEAD)" \
  --opportunities ../perf-evidence/opportunities.json \
  --worktrees ../perf-experiments \
  --labcoat-repo ../project-labcoat \
  --out ../perf-evidence/campaign.json
```

Labcoat records the pre-registered hypotheses, parents, evidence, patches, and final decisions. Never introduce a second mutable experiment journal. The agent runtime, not this CLI, launches the specialist agents.

## 4. Maintain the freeze through consolidation

Use the same source-controlled workload contract in every experiment and on the consolidated exact final commit. Do not quietly change benchmark input generation, weights, tolerances, oracle or measurement methodology to rescue a promising candidate. If the original base contains `perf/workload.json`, `prof-tools finalize` checks that the final version is byte-for-byte identical and that the final evaluation names the same contract digest. The source code and adapters implementing the benchmark must also be reviewed for semantic changes; a matching contract file alone cannot prove an unchanged execution path.

The user receives a report about what mattered: the observed benefit, tested correctness, resource tradeoffs, clean final diff, uncertainties and remaining limitations. They should not need to inspect internal JSON unless they want the evidence.
