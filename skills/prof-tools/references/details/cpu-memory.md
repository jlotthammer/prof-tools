# CPU memory attribution, allocations, cache and ownership

## Distinguish measurements

- **Python managed allocations**: `tracemalloc` traces many CPython allocator events; Python memory tracker is *not* overall resident memory and generally cannot see raw C/C++ heap, GPU HBM or large native arrays (unless explicitly integrated).
- **Native process allocations**: Memray (`memray run ...`, inspect `memray --help` for exact version) captures Python and native allocation paths, threads and reference ownership. Symbolization depends on installed native debug info. Profiling allocators can change timing/behavior.
- **RSS**: process-resident physical pages, counts shared pages in each process. Across worker processes summing RSS overstates unique memory. **PSS** accounts proportionally for shared memory via `/proc/PID/smaps_rollup` when accessible. **USS** is uniquely owned resident memory. Monitor cgroup `memory.current` when limits apply.
- **Virtual memory (VMS)**: address space reservations are not necessarily physical; not a substitute for RSS.
- **Memory bandwidth and cache misses**: hardware counter observations only. `perf` event names, PMU interpretation, cache levels and attribution can vary by CPU; check `perf list` and event scaling. A high LLC miss rate alone doesn't prove bandwidth saturation.

## Typical regressions

1. Repeated conversions `list ↔ numpy.ndarray ↔ torch.Tensor`, small Python objects, repeated byte encoding/decoding, unnecessary `.copy()` or Rust `.clone()`, C++ materialization and Pydantic serialization.
2. Implicit tensor/device synchronization (`.item()`, blocking transfer, `.numpy()` on GPU tensors), Python allocation in steady-state training steps.
3. Multiprocessing memory multiplication (fork vs spawn, copy-on-write broken by writes, caching huge dataset per worker), shared-memory file descriptor exhaustion, queue payload serialization.
4. Host and GPU contending for shared memory/fabric on MI300A; even a zero-copy pointer can be slower due to access patterns, page faults and coherence. Benchmark data ownership.
5. NUMA remote traffic and allocator first-touch; compact/transparent huge pages can change TLB cost but should be tested with permissions and correctness constraints.

## Evidence steps

- Sample process-level RSS/PSS and peak cgroup memory during real workload; report worker counts and start method.
- For Python allocation hotspot use `tracemalloc` scoped snapshots with a stable program phase; snapshots create overhead.
- For native allocations use Memray with native stack option when supported; inspect memory lifetime rather than only allocated byte totals.
- Tie allocation reductions to an unprofiled independent-process wall-time/throughput improvement, plus memory peak guardrail. Beware of trading memory for additional CPU or synchronization work.

## Confidentiality

Memory profiler reports and call stacks may contain file paths, class/function names and portions of inputs. Store locally in a user-approved directory. Do not share private traces or instrument unrelated processes.
