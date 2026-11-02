# Optimization candidates, only after measured attribution

| Signal | Candidate experiments | Risk and falsification |
|---|---|---|
| Host-side gaps between small launches | `torch.compile`, CUDA Graph replay (if supported and safe for the backend) for static regions, fuse redundant view/cast/pointwise chains, move repeated CPU decisions outside step | Graph breaks, dynamic shape explosion, capture restrictions, altered RNG/state or extra GPU memory; reject if no macro throughput gain |
| Repeated device synchronization | Avoid `.item()`/`.cpu()` inside hot paths, defer logging, replace scalar CPU branch with a tensor selection where semantics allow | GPU control flow/stream ordering changes, lifetime of async D2H buffers, correctness |
| Data loader not ready on critical path | Persistent workers, prefetching, pinned host memory and async host→GPU on appropriate stream, shift augmentation to CPU/GPU as measured | Host RAM use, worker contention, pinned-memory cost, unintended nondeterminism |
| Excessive allocation/intermediates | Reuse buffers, fuse operations, hoist invariant calculations, adjust tensor lifetimes | Aliasing, graph capture lifetime, shape variability, backward correctness |
| Memory-limited kernels | Data layout/coalescing, reduce DRAM round trips, fuse adjacent ops when beneficial, tile shared-memory reuse, use cache efficiently | Register pressure, spills, lower occupancy; fusion can regress |
| Tensor core underuse | Fix layouts/dim alignment, compare library GEMM and attention kernels, precision mode and fused epilogues | Numerical precision, padding waste and shape-specific dispatch; always validate quality |
| Low grid parallelism | Remap work to CTAs/warps, parallelize independent reductions, warp-specialize where supported | Reduction reordering, temporary buffers, sync overhead |
| FSDP/DP bottleneck | Overlap collectives with backward, tune bucket/split/prefetch, revise sharding for topology | Increased memory, cross-rank correctness, exposed rather than total communication |
| Dynamic-size inference/diffusion | Reuse shape-family plans, avoid recompilation/autotuning in hot loop, reduce host device scalar handoffs | Cached shape mismatch, stale buffers, altered sampling trajectory |

Prioritize by expected saved end-to-end milliseconds, implementation complexity, and correctness risk. A targeted experiment at one shape must also be tested on nearby and worst-case shapes. Catalogue accepted and rejected cases with evidence, device generation and compiler version.
