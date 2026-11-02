# Distributed measurement guide

Profile representative **optimizer steps** with the same gradient accumulation and global tokens as production; report both strong-scaling (same global batch) and weak-scaling (same per-GPU batch) only when explicitly distinguished. Attribute node topology and PCIe/NVLink/NVSwitch/interconnect link speed separately. For SHARD and HYBRID_SHARD, account for all-gather, reduce-scatter, overlapping forward/backward prefetch and parameter resharding; do not mistake collectives running concurrently with compute for exposed overhead.

## Method

1. Measure a one-GPU run and one-node multi-GPU run with matched workload policy.
2. Record rank↔GPU placement, collective library and topology, device UUIDs and job scheduler allocation.
3. Add coarse NVTX phase/step ranges and capture short, aligned per-rank traces. Inspect nsys's `nccl_gpu_overlap_trace` / `nccl_gpu_time_util_map` recipes if supported; use `nsys recipe --help` to confirm version.
4. Normalize per-step values, compare rank medians and tails, and find the slowest rank/straggler. Attribute exposed collective time by checking its overlap with the step's critical path, not summing entire NCCL kernel durations.
5. Change exactly one dimension (gradient bucket size, batch, accumulation, prefetch, affinity, network placement or FSDP sharding strategy), then remeasure **without** profilers.

## Warnings

A call to `torch.distributed.barrier` or `torch.cuda.synchronize` inserted for attribution can destroy overlap and distort the run. Avoid when possible. `NCCL_DEBUG=INFO` can produce large overhead/log volume; keep extensive debug logs out of benchmark runs. Not every profiler supports multi-process or network tracing in every container or security configuration. Do not prescribe `sudo` or privilege escalation in shared clusters. Collective speed depends strongly on topology and message size, so avoid generic universal expected speedup percentages.
