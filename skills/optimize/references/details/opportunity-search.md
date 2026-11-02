# Opportunity map, search breadth and memory policy

## First-principles model

Start at the user-valued application operation (full request, training step or real epoch). Understand all transformations, peak live data, device movements, kernel launches, CPU processing and rank completion. Ask what work can be eliminated *before* asking how to make it faster. Compute a possible saving only for work with defensible **exposed serial duration**. Collective kernel duration is not exposed communication time; stream overlap is not a causal dependency; event-time correlation alone is not a critical-path certificate.

`prof-tools campaign start --repo . --base <sha> --opportunities opportunities.json --worktrees ../worktrees --out campaign.json` validates a representative weighted shape/population manifest, screens seven optimization families, and selects up to three candidate branches with distinct mechanisms. A candidate's conditional bound uses `exposed_ms * (1 - 1/speedup_ceiling)` per workload and population weighting. This is **not** a claimed attainable gain: dynamic bottleneck migration, overlap changes, cache effects and algorithm changes may invalidate the simple bound. Unknown exposure is explicitly returned as unknown, never replaced with cumulative GPU time.

Screen every family with a concrete reason, even when ruled out:
- **algebra:** eliminate/aggregate operations, exploit identities, change computational complexity while preserving required semantics;
- **dataflow:** remove intermediary materializations, recompute vs store, representation, persistent state;
- **scheduling:** pipeline, overlap, barriers, host dispatch, load balance;
- **memory:** layout, residency, cache, transfer, allocation, capacity and locality;
- **library:** vendor primitives, compiler-generated code, frameworks and dispatch;
- **kernel:** fusion, vectorization, instruction path, tiling, register/SMEM/LDS occupancy;
- **distributed:** partitioning, collective volume, rendezvous, straggler and exposed communication.

## Branching procedure

Each selected candidate has a hypothesis, mechanism, falsification test, cost, uncertainty and workload applicability. Spawn diverse **exploratory** Labcoat branches, ideally on isolated Git worktrees. Search promising branches using minimal cheap evidence first. Keep at least one non-kernel direction under consideration if it plausibly attacks a different class of cost. Branch decisions are recorded as Labcoat outcomes, not in an `prof-tools` database. Confirm the selected final implementation on independent data/workload traces after choosing the approach. When a candidate stalls, return to sibling branches instead of continuing a greedy local search.

## Memory policy

Performance is primary unless the actual workload has a binding peak memory constraint (OOM, allocator fragmentation, paging, memory reservation limit, batch-size feasibility or a stated deployment requirement). Report peak memory for comparisons when possible. In a nonbinding regime, smaller memory is a useful secondary benefit but does not justify considerable structural complexity by itself. If binding, a candidate with unknown predicted memory remains **unverified** until measured; a predicted violation must not be presented as feasible. Capacity can be a feasibility gate before any timing comparison. Do not make up a fixed maximum permitted memory increase; use actual project and hardware constraints. Use paired **measured** peak-memory values for final acceptance, not model predictions.

A complete sample is at `examples/opportunities.sample.json` in the source ZIP (examples are not copied by the skill installer). Regenerate using actual metrics. Do not confuse the screening report with a Labcoat experiment note.
