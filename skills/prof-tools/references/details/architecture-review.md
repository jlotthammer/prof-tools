# Independent semantic architecture review

## Mission

Determine whether the **consolidated implementation** is the simplest maintainable design that preserves required behavior and delivers experimentally established application-level value. An optimization can benchmark faster and still be a poor design. Review the architecture, not just style, line count, or green tests.

The reviewer is **independent and read-only**. Do not implement changes, alter verification or benchmark code, edit Labcoat records, or decide KEEP/REVERT. The Labcoat coordinator makes that decision. The reviewer returns a substantive, falsifiable assessment of the original-to-final source change.

## Inputs and review boundary

- Project's architecture/API guidance (`AGENTS.md`, `CLAUDE.md`, interface conventions).
- Exact **original pre-optimization base commit** and **final consolidated commit**; inspect the whole diff, not only the implementation agent's summary.
- Public APIs and representative **call sites before and after**; imported modules, registration/dispatch, and configuration paths.
- Relevant test infrastructure, independent correctness oracles, invariant checks, and unprofiled **application-level** benchmark evidence for the exact final commit.
- Labcoat's retained hypotheses and negative results, consulted as evidence—not a justification to retain exploratory code or its history in source comments.
- Memory capacity constraints and representative workload shapes/ranks, if relevant.

If crucial input is unavailable or an assertion is unverified, record a `FAIL` for the affected dimension. Do not silently fill gaps from the implementer's narrative.

## Ten semantic dimensions (all required)

### 1. `semantic_preservation`

Reconstruct the observable contract before and after: return values, shape/stride/layout, dtype, numerical tolerances, gradients, optimizer/model state, aliasing/mutation, error handling, randomness and reproducibility, concurrency, synchronization, resource lifetime, and distributed behavior. Which contracts genuinely changed by design? Identify independent reference or invariant evidence, and name untested operating regimes. Passing tests is bounded evidence, **not mathematical equivalence**. An undocumented contract change is a failure, not a speedup.

### 2. `conceptual_economy`

For **every** new class, module, layer of indirection, configuration option, cache, mutable state, specialization, dependency, and new public concept, ask: why must it exist? Prefer removal of redundant concepts to reorganization into additional helpers. Challenge speculative extensibility, defensive wrappers and architecture that only exists because experimentation took a complicated path. Do not demand a trivial implementation when an essential algorithm is complicated.

### 3. `coherent_public_api`

Compare old and new APIs, their consumers and compatibility requirements **within the actual project**, not hypothetical callers. One coherent interface should express the operation. Seek split or duplicated APIs, new mandatory caller knowledge, boolean-mode overloads, ambiguous defaults, generic untyped fields where domain-specific names would clarify, and independent entrypoints that should converge. Public contract and implementation must agree. Explicitly explain any intentional breaking change; do not preserve compatibility mechanisms without a real requirement.

### 4. `dataflow_and_ownership`

Trace data creation, transformation, copying, mutation, allocation, caching, synchronization, and release from caller to result. Who owns each buffer and invariant? Which operation changes state? Are device/host or process/rank boundaries clear? Does the design expose unavoidable constraints at the right layer rather than burying synchronization, aliasing, or invalidation in helpers? Watch for circular dependencies, implicit global state, double conversion, stale caches and lifetime hazards.

### 5. `optimization_necessity`

For each complexity-inducing optimization, identify the mechanism by which it reduces **exposed application cost** and cite the measured effect and representative input distribution. Do not accept a kernel-only speedup, theoretical peak, summed CUDA kernel time, or profiler replay duration as application benefit. Check per-shape/rank regressions, secondary costs, and uncertainty. **Memory is a secondary objective** unless an explicit capacity, OOM, batch feasibility, paging or operational requirement makes it binding; note any memory regressions even if the primary metric improves. More complexity requires commensurate, evidenced value; never invent arbitrary speedup thresholds.

### 6. `simpler_alternatives`

Independently search for a credible simpler route: the original implementation, a standard/vendor library, an algebraic simplification, better compiler usage, a smaller dataflow change, or an existing project abstraction. Analyze at least one concrete option and its tradeoff; the original base is a valid comparator. Explain whether it is adopted, rejected on evidence, or merits a new experiment. The reviewer need not demand a rewrite based on speculation, but must not merely compare the winner against the messiest exploratory branches.

### 7. `scope_discipline`

Account for why each changed module, dependency and interface is needed for the retained behavior or optimization. Challenge unrelated refactors, extra supported modes, compatibility shims, or infrastructure added only for an intermediate benchmark. The ideal is a small **conceptual** diff: more lines can be justified when they eliminate a poor abstraction. Do not reward terse code that hides complexity, or impose line-count ceilings.

### 8. `exploration_residue_removed`

Reject abandoned kernels, `old/new/v2` codepaths, obsolete flags, duplicate implementations, commented alternatives, debug-only instrumentation, temporary benchmark hooks and historical source comments. Preserve experiment history in **Labcoat and Git**, not by leaving production code bifurcated. A fallback required for an actually supported workload is not residue; cite its contract and coverage.

### 9. `maintainable_tests`

Prefer tests of behavior and invariants over snapshots of internal implementation choices. Check correct oracle independence, boundary/strided/odd shapes, dtypes, error paths, aliasing/state changes, gradients, stochastic distributions, concurrency, distributed ranks and memory safety when applicable. Ensure tests are deterministic where feasible, can be run by a maintainer, and verify the optimized dispatch is actually executed. A test that only reuses the candidate's algorithm is not independent evidence.

### 10. `diff_accountability`

Inspect the complete diff from the original base and give every changed path a **purpose** and **necessity**. Review deleted and renamed files, changed imports, public exports, dependency metadata and configuration as well as primary implementation files. Verify that the final architecture is understandable without reading Labcoat or the optimization branch. No change should exist solely to memorialize how the answer was found.

## Review procedure

1. Read original and final source in context. Reconstruct public API and full relevant dataflow, including failure paths and resource ownership.
2. Identify essential **algorithmic changes** versus accidental experimental structure.
3. Audit every new concept and changed file, tracing effects on callers and tests.
4. Attempt to explain the performance gain from application dataflow, not profiler hotspot rankings alone.
5. Compare with at least one credible simpler alternative, and write its tradeoff without confirmation bias.
6. Populate **all ten** dimensions independently with a unique, concrete evidence statement and at least one **tracked source-file location** (a file path, not a URL or an untracked artifact). Include symbol names in the prose where useful. `FAIL` means repair or additional evidence is required; never return `PASS` for an unexamined dimension.
7. Populate the exact base-to-final `changed_files` list with a purpose and necessity for each path. Describe the public API before, after, and the real compatibility implications. Populate `simpler_alternatives` with a considered option and disposition.
8. Return the JSON artifact described by `examples/design-review.sample.json`, plus any plain-language findings. Never invent evidence, commit IDs, file paths, perf results or checks that were not executed.
9. If changes are required, hand findings to the integrator for a **new committed** implementation. Re-run applicable correctness and unprofiled application benchmarks on that final code; re-review the new commit. A validated exploratory branch is not a final integration certificate.

## Evidence contract and executable gate

`prof-tools finalize` checks:

- clean committed final tree descending from the declared original base, diff whitespace, and exact final commit in correctness and performance evidence;
- exactly these ten dimensions, each `PASS` with **distinct reasoning** and source-file locations verifiable in the base or final Git tree;
- exactly the diff's changed files accounted for, each with purpose and necessity;
- explicit `public_api.before`, `public_api.after`, `public_api.compatibility`;
- at least one explicitly evaluated `simpler_alternatives` entry containing option, tradeoff, evidence and disposition;
- existing correctness/application benchmark acceptance rules, including binding memory constraints.

The gate **cannot** prove an agent was independent, that it really read the cited code, that evidence text is honest, or that the design is elegant. It does not score line count or require a numeric complexity threshold. The reviewer must make those judgments; the Labcoat coordinator owns the integration decision. A `READY_FOR_LABCOAT_INTEGRATION` result means the specified **attestations and machine-checkable evidence** are complete, not that design quality has been proved.
