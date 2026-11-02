# CPU hardware counters, compiler signals, C++ and Rust references

## Frame pointers and debuginfo

Use optimized binaries with *usable* symbols. A debug `-O0` build is not equivalent to production `-O2/-O3`; use `RelWithDebInfo` or release builds with `-g` and frame pointers when convenient. Shared libraries can be stripped in deployed environments; separate symbols/debuginfo packages may be required. `perf report` missing `[unknown]` frames is a limitation, not evidence the time vanishes. Inlining and symbol folding may combine functions.

## Counter interpretation

| Counter family | Meaning / trap |
|---|---|
| `cycles`, `instructions`, IPC | context only; measure actual frequency; IPC can rise from doing more useless instructions |
| branches / branch misses | normalize per branch or per input; high misses aren't always dominant stall cause |
| LLC/cache misses | exact PMU event may mean L1, LLC, load, fill or cache request; compare exact `perf list` spec |
| task-clock, context-switches, migrations | process scheduling, work distribution and potential loss of affinity; event counts are not causes without timeline |
| stalled cycles / top-down metrics | architecture-specific and sometimes unavailable; never label generic counters as accurate memory-bound diagnosis |
| page faults, DTLB/ITLB | page placement, allocator churn, huge pages or access locality; minor faults differ from major I/O faults |
| memory bandwidth | needs PMU/uncore events per socket, often privileged; theoretical DRAM peak is not observed bandwidth |
| `perf stat` scaling | counters may be multiplexed when too many events are measured; collect smaller groups and note `time enabled/running` |

## Architecture-neutral optimization hypotheses

- Remove algorithmic work and redundant conversions before intrinsics. Avoid dynamic dispatch and allocator hot paths only where profile shows them.
- Hoist loop-invariant work, improve predictable branches, contiguous data layout and batch size; validate cache footprint. SIMD/autovectorization needs layout, alignment and fast-path checks (`-Rpass=loop-vectorize`, compiler optimization reports or disassembly).
- Minimize false sharing when hot threads write adjacent cache lines; balance thread teams against quota and memory traffic. Use contention metrics, worker scaling and thread-level sampling.
- Test huge pages/NUMA binding/memory first touch as isolated changes. Environment changes often improve one process while hurting shared-node neighbors; record changes with user authorization.
- Cross-language: pybind11/PyO3 overhead, Cython and FFI boundary copies are frequently the bottleneck, not the actual scalar kernel.

## C++ and Rust build hygiene

C++: compile realistic optimized builds with debug symbols, enable sanitizers in **separate correctness** jobs, consider LTO/PGO only after a full workload profile and with reproducible build flags. Verify ABI, floating-point semantics, exception boundaries and thread safety. Rust: build `--release` with `RUSTFLAGS='-C force-frame-pointers=yes -C debuginfo=2'`, use `cargo flamegraph` if available, and consider `cargo bench`/Criterion/Divan for isolated hot functions. A cargo bench profile and production profile are not interchangeable (different allocations, linking, dependency features). If Python imports a Rust extension, symbols must be enabled in the Python-loaded shared library too.

## Reference sources

- CPython perf profiling: https://docs.python.org/3/howto/perf_profiling.html
- Linux perf tool security: https://docs.kernel.org/admin-guide/perf-security.html
- Cargo flamegraph: https://github.com/flamegraph-rs/flamegraph
- Rust profiling: https://nnethercote.github.io/perf-book/profiling.html
- Linux perf tools: https://perf.wiki.kernel.org/index.php/Main_Page
