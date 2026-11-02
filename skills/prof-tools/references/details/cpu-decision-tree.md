# CPU bottleneck classification and evidence matrix

This decision matrix is subordinate to `prof-tools`. The primary target is **application-level elapsed time/throughput**. The table names profilers with fundamentally different measured quantities; they should not be used interchangeably.

| Diagnostic question | First observation | Follow-up | What not to infer |
|---|---|---|---|
| Which Python frames consume CPU? | py-spy sampled **on-CPU** profile, version defaults checked | Scalene per-line time, cProfile calls | Inclusive sample fraction ≠ share of elapsed time under thread overlap |
| Why is the process slow when CPU utilization is low? | Wall-clock sample including idle, process CPU seconds vs wall | Off-CPU wait queues, `pidstat`, async timeline, queue lengths | A sleeping Python frame ≠ CPU hotspot |
| Are native libraries responsible? | Scalene Python/native fraction or py-spy `--native` | `perf` mixed stacks, symbolized .so, native microbench | cProfile's Python caller attribution ≠ native function attribution |
| Python GIL or thread pool? | Per-thread throughput vs worker count, `py-spy --gil` and non-GIL samples | CPU utilization per thread, native release-GIL sections, locks | `--gil` filtered samples miss native GIL-free execution |
| Python allocation pressure? | `tracemalloc` scoped snapshots | Memray (native allocations), allocation rate, arena/pooling | RSS ≠ `tracemalloc` allocations; Python objects ≠ all process memory |
| Cache misses/branch mispredicts? | `perf stat` cycles/instructions + events from `perf list` | `perf record` / `annotate`, architecture-specific counters | Generic cache misses may be LLC/PMU model-dependent; misses alone ≠ stall cycles |
| Memory bandwidth/NUMA? | NUMA memory locality, page faults, socket placement | Per-socket BW counters if available, `numastat`, scaling | More bandwidth theoretical ≠ measured BW and is not a CPU roofline |
| Too many workers? | CPU quotas, affinity, OMP/Rayon/BLAS teams, cgroup `cpu.stat` deltas | Sweep workers × OMP threads holding work fixed | More logical CPUs visible ≠ more allowed CPU compute |
| CPU preparation stalls accelerator? | Paired CPU/GPU timeline + host ranges | DataLoader queue empty periods, H2D/page faults, CPU↔GPU sync | Sum of CPU preprocessing time ≠ GPU idle time |

## Quantitative reasoning

- **Wall time**: `time.perf_counter_ns()` around production relevant operation, including necessary waits. Use warm steady-state after realistic import, JIT, filesystem cache and thread-pool startup, but separately measure cold start if that is user-valued.
- **Process CPU time**: combined CPU execution of process threads. A four-thread busy process can consume ~4 CPU seconds per one wall second. Compute `CPU seconds / wall seconds` as *effective cores busy*, not percentage of an arbitrary host core count.
- **On-CPU samples**: collected while threads execute; count estimates on-CPU work distribution, with bias, missing symbols and filtering. For blocked-time investigation a wall-clock/off-CPU sampler is required.
- **Call graph cumulative time**: overlaps across parents and children. Sum only self times for additive decomposition within one profiler's scope; cProfile self time has observer overhead and excludes unprofiled threads/processes.
- **Amdahl**: maximum speedup from eliminating a non-overlapped fraction f of critical path is `1/(1-f)`; for changing a phase by factor s, maximum overall speedup `1/((1-f)+f/s)`. With overlapped producers, estimate *exposed delay* rather than f from raw CPU seconds.
- **Cycle model**: `cycles = effective time × actual clock` for cycles measured in same domain; instructions/cycles (IPC) is context, never a generic optimization objective. Perf virtualized events or multiplexed counters require scaling/validation.
- **Baseline samples**: run independent processes and pair ordering with `prof-tools evaluate`; if profiling changes CPU scheduler frequency or state, run unprofiled benchmarks after profiling, not during it.
