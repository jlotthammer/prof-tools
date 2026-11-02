# Final clean integration — optimize the implementation, not the exploration history

Labcoat records exploration, negative results, parent relationships, branches, source snapshots and decisions. It does **not** require retaining experimental architecture in production code. After identifying sound ideas, create a fresh worktree from the **original pre-optimization base commit**; do not auto-merge/cherry-pick all experimental branches. Reconstruct only the retained insights in the simplest coherent design.

## Integration process

1. List retained ideas and required observable contracts from Labcoat evidence. Describe the essential algorithmic mechanism and minimal target API/dataflow change for each; omit rejected and superseded approaches.
2. Independently examine the **original public API, call sites, dataflow, configuration and tests** before implementation. Prefer one clear path and ownership model. Replace overlapping code rather than add `old/new` variants, mode flags, speculative features or compatibility wrappers unsupported by actual requirements.
3. Choose the smallest **conceptual** diff, not the fewest changed lines. Removing a poor abstraction may require touching more files. Record changed files and why each is necessary.
4. Commit the consolidated implementation and run project-specific correctness tests, invariant/safety checks and unprofiled **representative application** benchmarks on that exact commit. Include applicable shapes, dtypes, ranks and memory feasibility. A test/tolerance change must receive independent scrutiny.
5. Dispatch an **independent, read-only semantic architecture reviewer** (optionally `prof-tools-architecture-reviewer`). **Required reading:** `architecture-review.md`. It requires ten dimensions, an exact changed-file account, before/after public API assessment and at least one concrete simpler alternative. Review architectural necessity and the actual measured benefit, not style, diff line count or implementation narrative.
6. Run `prof-tools finalize --repo /repo --base <sha> --evaluation /artifacts/evaluation.json --design-review /artifacts/review.json --out /artifacts/final.json`.

   It requires a clean committed descendant of the original base, matching final commit in correctness and performance evidence, valid performance/correctness acceptance, and **machine-checkable review completeness**. It checks that cited source paths exist in Git and all changed paths are explained. It **cannot prove** reasoning quality, reviewer independence or elegance.
7. If findings require revisions, change and commit the implementation, then **repeat** applicable correctness, unprofiled application benchmarking and architectural review on the new commit. No old review or perf certificate carries over implicitly.
8. Create a new Labcoat **integration experiment** citing exploratory siblings, correctness/performance artifacts, independent review and the exact final source snapshot. The coordinator decides KEEP/REVERT/PARTIAL. Do not introduce a competing experiment log.

## Independent review expectations

Review semantic preservation, conceptual economy, coherent public API, dataflow/ownership, necessity of added optimization complexity, simpler alternatives, scope discipline, removal of experiment residue, maintainable tests and accountable diff. More complexity can be justified by measured benefit, not a priori percentage thresholds. Memory is secondary unless a binding capacity/operational constraint makes it material. Preserve failed experiments in Labcoat/Git, never as dead production control flow.

A review that cites only “examined code and tests” is insufficient. Every dimension must state **what was examined and what was found**, cite actual tracked source files, and distinguish evidence from inference. Unsupported areas fail review; apparent PASS is not proof of universal equivalence.
