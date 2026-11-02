---
name: optimize
description: Explicit, budgeted optimization workflow: use Prof Tools and Labcoat to explore evidence-based hypotheses, verify representative workloads, then consolidate and independently review the final design.
disable-model-invocation: true
---

# Optimize performance with evidence

Run only when explicitly requested. **Invoking `/optimize` opts into Labcoat for this campaign**; the user does not need to invoke `/labcoat` or approve Labcoat a second time. Do not load Labcoat merely because ordinary debugging or benchmarking is happening outside this workflow. `prof-tools` measures and validates; **Labcoat** owns experiment notes, lineage, decisions and preregistration. The user’s original source Git repository must not receive experiment branches, notes, intermediate commits or preparation changes. Work in an independent preparation clone and an isolated campaign repository; only the consolidated final patch belongs in source.

## Agent workflow

1. **Translate the user's ordinary-language goal into an executable contract, yourself.** The user supplies the repository and objective, **not JSON files**. Inspect source Git status and record any pre-existing modifications before cloning; a normal clone excludes uncommitted changes, so reproduce required changes in the preparation clone with an explicit patch instead of silently dropping them. First create an independent preparation clone outside the source checkout (`git clone --no-local --no-hardlinks`), remove its `origin` remote, and do **all subsequent preparation in that clone**. Never alter the original repository until a final patch has passed review. Inspect entrypoints, tests, input provenance, numerical/gradient/state semantics, representative shapes/ranks and the actual runtime. Author `perf/workload.json` plus the necessary application benchmark, output exporter and independent correctness adapter. Establish workload weights from observed usage or documented requirements; never invent scientific tolerances or pass off the implementation under optimization as its own independent oracle. Validate the contract and exercise the baseline, then **commit the harness/contract in the preparation clone before freezing the prepared base SHA**. If a required semantic requirement genuinely cannot be inferred, ask only for that decision; do not silently relax validation. Read [contract authoring](references/contract-authoring.md), [methodology](references/methodology.md) and [verification](references/verification.md). Memory is secondary unless capacity or an operational constraint is binding.
2. **Diagnose before optimizing.** Gather short representative traces with the appropriate profiler. Analyze directly with `prof-tools diagnose` and, for unrecognized schemas, `prof-tools inspect`. Distinguish observed duration from dependency-critical exposed time. Never infer causal savings from summed kernel durations. Read [diagnosis](references/diagnosis.md), plus exactly one of [CPU](references/cpu.md), [NVIDIA](references/cuda.md) and [ROCm](references/rocm.md). Distributed work also needs [distributed](references/distributed.md).
3. **Generate the opportunity map yourself, from code and evidence.** Screen all seven families (algebra, dataflow, scheduling, memory, libraries, kernels and distributed). Read the baseline timings from the frozen workload; record a mechanism and cheap falsification test for each candidate. Never fabricate exposed latency or predicted savings. Write the machine-readable opportunity specification to the campaign's external artifact directory (not into the frozen source checkout), validate it, then invoke `prof-tools campaign start --repo <prepared-clone> --base <prepared-sha> --opportunities <generated-path> --worktrees <new-campaign-directory> --labcoat-repo <persistent-external-labcoat-repo> --out <outside-repo>/campaign.json`. The command creates an **independent bare Git repository** for experimental refs; no experimental Git objects enter the original or preparation repositories. The user does not prepare an `opportunities.json`. Read [contract authoring](references/contract-authoring.md) and [search and consolidation](references/search-and-consolidation.md).
4. **Explore with Labcoat (authorized by this invocation).** Explicitly load and follow the installed Labcoat `SKILL.md` plus the relevant references. Labcoat is a manually invoked skill and may have `disable-model-invocation: true`: this does not revoke authorization given by the explicit `prof-tools` request. When the runtime supports native skill invocation, invoke Labcoat so its session-scoped hooks register; otherwise load its file directly and run Labcoat's annotation and validation scripts at each note transition and before delivery. Do **not** claim the human-feedback hooks are active merely because you read the file. For Labcoat in an external notes repository, run checks against that repository instead of assuming the source checkout contains `notes/`. Search prior evidence using bounded `find.py --brief`, create compact notes with `note.py`, and use `validate.py` for integrity. Read Labcoat `footguns.md` and `orchestration.md` only when relevant. Search history in the **separate Labcoat Git repository**, preregister each hypothesis in an ACTIVE note in a distinct Labcoat commit, and isolate each code-changing worker in its own campaign Git worktree and artifact namespace. Never commit note symlinks or experiment branches to the source repository. Run cheap tests before implementing expensive specializations. Keep alternative families viable; backtrack on weak end-to-end value, correctness failures or complexity.
5. **Evaluate each candidate with one command.** From the project checkout run `prof-tools evaluate --outdir <unique-artifact-dir>` (defaults to the agent-authored, committed `perf/workload.json`; use `--spec` only for an existing alternative contract). This runs independent correctness checks before unprofiled paired measurements across the weighted distribution, verifies timed output identities, checks per-case regressions and memory limits, and writes `evaluation.json`. It may return `BLOCKED`; record failure evidence in Labcoat. A kernel microbenchmark alone is never an acceptance test.
6. **Consolidate.** In a clean integration worktree from the **prepared base**, reconstruct the winning ideas into one coherent design. Do not stack exploratory branches or preserve redundant APIs, flags, dispatch paths, abstractions or performance scaffolding. Retain a small conceptual diff, not necessarily the fewest lines. Require an independent architecture reviewer with fresh context.
7. **Revalidate the exact final commit and finalize inside the isolated campaign repository.** Re-run `prof-tools evaluate` from the committed final checkout using the **original frozen workload contract**, then `prof-tools finalize --repo . --base <sha> --evaluation <evaluation.json> --design-review <review.json> --out final.json`. Independent reviewer checks ten semantic dimensions, every changed file, public API before/after and a credible simpler alternative. `finalize` checks evidence and source revisions, but does not decide KEEP/REVERT; Labcoat does. After approval, deliver only the clean consolidated patch to the original source. Preserve the separate campaign Git database while Labcoat notes reference its commits; never push experimental refs upstream.

## Bounded run entrypoint

Invoke this workflow as `/optimize` (or `$optimize` in Codex). The CLI remains `prof-tools`.

After preparing the campaign as described above, start a bounded run with:

```bash
prof-tools campaign run --campaign /path/to/campaign.json \
  --objective "Improve representative end-to-end throughput while preserving semantics" \
  --time-budget-minutes 120 --max-evaluations 8 --reserve-minutes 15
```

This runs one foreground Codex worker at a time and reserves the final evaluation for integration. Resume a paused run with `prof-tools campaign run --campaign /path/to/campaign.json --resume`. The runner does not integrate or independently review the final change; use the reserved time for those steps.

## Zero-configuration user entrypoint

The user can say: **“Use prof-tools to optimize training throughput for this repository, preserve numerical behavior, track experiments with Labcoat, and deliver a clean final diff.”** They do **not** create `perf/workload.json`, `opportunities.json`, adapter scripts, a Labcoat plan, or worktrees. These are artifacts **you**, the agent, create following [contract authoring](references/contract-authoring.md). If a trusted oracle or a material scientific/operational requirement is unknown, disclose the uncertainty and seek that one decision rather than manufacture certainty. The CLI is a deterministic executor/validator, not an LLM that fabricates contracts; do not claim it generates either file automatically.

## Five CLI capabilities

- `diagnose`: programmatic profiler interpretation; no trace viewer needed for supported evidence.
- `campaign start`: one opportunity screen and worktree preparation, not multiple public planning stages.
- `evaluate`: a single correctness + weighted performance + memory decision artifact.
- `finalize`: verify exactly the consolidated commit and independent design review.
- `inspect`: advanced read-only environment/hardware/schema/normalized-event inspection. Lower-level analyzers remain importable Python functions, not competing CLI workflows.

## Strict safety and evidence boundaries

- Never call profiling, kernel replay, sampled counters, or GPU activity sums a final performance measurement. Final measurements are unprofiled.
- Establish the exact executed source revision, workload identity and independent oracle. `PASS` applies only to tested semantics; missing gradient, stochastic, distributed, or sanitizer coverage must be disclosed.
- Never claim a CUDA Graph node is an independent host launch, use unsynchronized rank clocks to infer skew, or assume collective duration equals exposed cost.
- Do not change GPU clocks, partitions, privileged perf permissions or other users' processes without explicit authorization.
- The independent reviewer cannot simply endorse the implementer's story. Missing evidence must fail closed. Experimental history belongs in Labcoat and Git.
