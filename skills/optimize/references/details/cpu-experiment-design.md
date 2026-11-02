# CPU benchmarking and optimization protocol

Use `prof-tools evaluate` for CPU, NVIDIA, and AMD workloads; it has no GPU dependencies. All child workloads must emit exactly one `PROF_TOOLS_RESULT=` line.

## Workload identity

Every baseline/candidate process emits **exactly one** result line:

```text
PROF_TOOLS_RESULT={"metrics":{"elapsed_ms":18.2,"items_per_s":9000},"workload":{"dataset":"v1","rows":30000,"threads":4,"python":"3.13","mode":"cpu"}}
```

Record effective CPU set, cgroup quota, governor, frequency range, NUMA locality, Python implementation (CPython/PyPy/free-threaded), native BLAS versions and pool sizes, environment, input distribution, compiler flags, cache cold/hot state, process count and memory budget. The workload identity must be identical: do not place candidate variant ID inside `workload`. Keep correctness checksum or digest in a separate field and independently assert it matches. The benchmark runner's workload match is a guardrail, **not a semantic-equivalence proof**.

## Protocol

Run `prof-tools evaluate --spec workload.json --outdir perf_runs/evaluation` for the canonical weighted application benchmark; use `prof_tools.benchmark.run_trials` only for supplementary experiments.

Runner warmup means preliminary independent **process** invocations; each benchmark program must still warm its own JIT/caches and internally time the correct fixed work. It randomizes paired order to limit drift and reports paired bootstrap geometric speedup with a CI, per-child exact logs and manifest. Avoid profiling commands and deterministic instrumented timings in the child; benchmark-only verdict is never final ACCEPT.

### More accurate CPU microbenchmarks

For sub-millisecond independent functions use `pyperf` or `hyperfine` when already available and configured; for Python's short snippets use `timeit` for *diagnosis*, not as the only application-level evidence. `pyperf` can calibrate iterations and report distribution, but modern CPU frequency/boost and system noise still matter. For C++/Rust library functions, Google Benchmark / Criterion / Divan are useful for an isolated kernel after application-level hotspot evidence. Control allocation/setup inside vs outside the timed region according to true intended work, explicitly name the timing policy. For tiny kernels, overhead of Python call dispatch or thread pool startup often dominates.

### Correctness and reliability gates

- Identical logical work/inputs: representative payload distribution, tails/edge cases and full success/failure behavior, not only equal output checksum in one seed.
- Check float rounding and deterministic reduction order; `-ffast-math` or SIMD vectorization can change answers. Check native extensions for undefined behavior and data races.
- For async/concurrent changes, verify absence of deadlocks, throughput under backpressure, cancellation, leak, error propagation, memory peak and data races.
- Throughput and tail latency are different objectives; a lower mean request time can still be a p99 regression. For streaming, record open loop vs closed loop request generation, queueing time and saturation knee.
- A single CPU process may auto-scale `OMP_NUM_THREADS` or worker count from `os.cpu_count()` despite cgroup quota. Pin explicit configuration or run a separate controlled thread sweep.
- For comparisons across different machines, CPUs or kernel/container images, treat observed speedups as separate experimental conditions; don't pool to one universal CI.
