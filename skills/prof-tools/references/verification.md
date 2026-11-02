For agent-owned workload contract construction and freeze rules, read [contract authoring](contract-authoring.md).

# Correctness and application acceptance

Use one project-owned workload contract, not several intermediate experiment specifications. `prof-tools evaluate --spec workload.json --outdir <unique-dir>` invokes the independent reference/candidate output comparators, unprofiled paired benchmark and application acceptance assessment; `evaluation.json` includes the complete correctness, performance and assessment evidence. The project must provide independent reference outputs, stable input identity, shape/dtype/tensor keys, and explicit tolerances. Timed runs must reproduce the verified output digest and input ID.

Full correctness depends on the work: add project-defined gradient checks, optimizer state/trajectory, mutation/alias, stochastic distributions, boundary/odd shapes, race/sanitizer checks, concurrency, and distributed tests. A test suite passing without such applicable coverage does not establish correctness for those semantics. These checks are project-owned and should run as part of its normal test workflow; the evaluation runner cannot infer unstated invariants. Source revision in final correctness/benchmark reports must match the final committed integration tree.

Memory is secondary unless a specified capacity threshold is binding. Never accept a 10,000× speedup from an incorrect algorithm, a skipped code path, stale compiled code, lower precision without authorization, or cached outputs substituted for required computation.

Details: `prof_tools.verify.run_verification` and `prof_tools.torch_checks` are the reusable verification primitives. See also [Labcoat footguns](https://github.com/jlotthammer/labcoat/blob/main/skills/labcoat/references/footguns.md).
