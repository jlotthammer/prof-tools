# Diagnostic decision tree

| Measured symptom | Next evidence | Likely mechanism to test, **not** a conclusion |
|---|---|---|
| Low throughput, long GPU gaps | CPU and GPU timeline; data acquisition and kernel launch timestamps | Host dispatch, data loader, blocking CPU-GPU dependencies, insufficient work |
| Large number of sub-20µs kernels | Nsight Systems / ROCprofv3 kernel counts per step, GPU gaps, event-level latency | Unfused operators, graph capture fragmentation, Python dispatch, needless intermediate ops |
| High GPU busy %, poor throughput | NCU / ROCm Compute Profiler on contributing kernels, arithmetic intensity, layout, algorithmic FLOPs | Memory stalls, weak tensor core utilization, wasted work, bad shapes, excessive communication |
| Slow H2D/D2H or memcpy APIs | Async transfer and dependency timeline; page-locked host memory, number/size of transfers | Copies, pageable memory, hidden synchronization, data staging |
| High allocator calls / changing peak memory | allocation trace, graph/compile state, liveness | Dynamic tensors, fragmentation, redundant intermediates, checkpoint trades |
| DDP/FSDP scaling collapse | matched per-rank traces and topology; overlapping windows | Network, collectives, rank skew, synchronization, scheduling |
| One shape disproportionately slow | generated kernel identity, shapes/strides, compiler specialization count | Dispatch fallback, poor occupancy, recompilation, padding cost |
| Strong run-to-run variation | clocks/temp/power, warmup, compilation and data distributions | Thermal/power throttling, shared GPU, JIT, GC, background tasks |

**Attribution discipline.** GPU utilization (including `nvidia-smi` or `amd-smi` averages) means activity, not useful work. Profiler kernel totals are *summed durations* and can double-count overlapping kernels; per-iteration latency is elapsed time on the critical path. CPU NVTX range duration is not automatically GPU execution duration. Profiler queue time is not simply idle GPU time. Hardware counter profilers sometimes serializes or replays kernels, changing concurrency/cache behavior. Distinguish diagnosis from demonstrated cause with controlled interventions.

**Instrumentation.** Use NVTX spans at stable, limited granularity. PyTorch `torch.profiler.profile(schedule=...)` gives operator stacks/shapes/trace but adds overhead. For steady-state nsys capture, optionally insert `torch.cuda.cudart().cudaProfilerStart()` after warmup and `cudaProfilerStop()` after the target steps (verify API presence in the installed PyTorch); all ranks that need capture should participate. Do not time benchmark runs with broad profiler annotations switched on.

**Escalation order.** Unprofiled metric → lightweight PyTorch/`nsys` trace → nsys stats/SQLite for per-step attribution → targeted `ncu` → isolated kernel tuning → unprofiled macro validation. Stop escalating once the available evidence answers the question.
