# Kernel-level evidence

## First test the optimization ceiling

From an unprofiled end-to-end trace estimate the fraction of *exposed critical path* that could be removed. Amdahl's bound with an exposed fraction `f` and component speedup `s` is `1 / ((1-f) + f/s)`; do **not** use summed overlapping GPU kernel durations as `f`. Check whether the kernel is actually on that path, and whether replacing it changes launch patterns or dependencies.

## Nsight Compute interpretation

- `SpeedOfLight` provides compute and memory throughputs relative to peak sustained ceilings, not a definitive compute/memory diagnosis alone.
- Add `ComputeWorkloadAnalysis` for math pipelines and tensor-core instructions; `MemoryWorkloadAnalysis` for global/shared/L2/DRAM behavior, sectors and coalescing; `LaunchStats` and `Occupancy` for register/shared-memory and block limits; `WarpStateStats`/`SchedulerStats` for stalls and eligible warps; `SourceCounters` selectively for source/SASS correlation.
- Low achieved occupancy can be benign if latency is hidden or execution is bandwidth-limited. High occupancy doesn't prove useful work. Check memory coalescing, bank conflicts, instruction mix, register spills, barriers, async copy staging, launch grid and tensor-core tile compatibility.
- Basic roofline: work/DRAM bytes establishes arithmetic intensity at DRAM. For hierarchical roofline, choose the appropriate L1/L2/DRAM traffic and peaks; do not mix cache-level bytes with DRAM bandwidth.
- NCU kernel replay can reset caches and serialize launches. For kernels whose performance depends on streams, graphs, inter-kernel cooperation or cache state, use carefully scoped range/application replay or rely on unprofiled CUDA-event end-to-end measurements. Review official tool compatibility for hardware/driver versions.

## Kernel change checklist

1. Define precise op semantics and reference implementation.
2. Verify strided/noncontiguous shapes, masks and out-of-bounds tails.
3. Fix dtype and accumulation precision, gradient correctness and RNG assumptions.
4. Select simplest maintainable implementation; compare with built-in fused/cuBLAS/Inductor alternatives.
5. Test multiple tilings on actual target hardware. Track compilation, registers, shared memory and achieved latency, not just a theoretical FLOPs target.
6. Report full-model latency and throughput, beyond microbenchmark results.
