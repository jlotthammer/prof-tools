# Python deep-dive: interpreters, GIL, async and common ML bottlenecks

## Initial triage for ordinary Python

1. Start with py-spy sampling. Note whether sampling is on-CPU or wall and `--gil`/`--idle` mode. A single expensive line in Python might actually call 100 ms of native code: use mixed/native sampling before refactoring it.
2. If time is within Python itself, use Scalene's per-line Python fraction or a scoped cProfile to identify call counts and interpreter overhead; compare changing algorithms/representations rather than translating loops to C++ prematurely.
3. If time is native, check thread pool and backend (NumPy BLAS/OpenBLAS/MKL, PyTorch intra/inter-op, tokenizers, compression, Rust bindings) and next invoke native specialist.
4. If time is missing: asynchronous I/O, sleeping, DNS, locks, process queues and GPU waits can dominate wall time but disappear from on-CPU samples. Inspect external waiting separately.

## Frequent patterns

- Row-by-row pandas `.apply`, `.iterrows`, nested Python loops, per-element `torch.Tensor`/NumPy calls; batching and columnar operations are promising but can balloon temporaries and worsen data locality.
- Repeated `torch.from_numpy` → `.to(device)` copies, converting shapes/strides, pinning tiny objects, failed overlap of DataLoader producers and GPU consumers. Don't introduce device synchronization solely for instrumentation.
- `multiprocessing` start costs and worker queues. More workers can degrade throughput with large payload pickle or shared CPU quota; benchmark actual queue behavior under worker count sweeps.
- Python caches can make benchmark data unrealistically favorable. Specify cold/hot cache and user-valued latency; don't benchmark solely tiny repeated objects.
- CPython GIL: threads doing Python bytecode share a GIL in conventional builds, whereas NumPy/BLAS/Rust/C++ calls can release it; use profiler evidence. Python free-threaded builds may have different extension compatibility and contention behavior; query runtime build and actual GIL state.
- `asyncio` task times: distinguish ready-queue delay, time suspended waiting for I/O, slow event-loop callbacks and Python work done while holding the GIL. A wall clock flame graph alone may misattribute awaits.

## Tool variants

- **py-spy**: low-overhead Python stack sampling with native (`--native`), GIL (`--gil`), idle (`--idle`), subprocess (`--subprocesses`) and speedscope/raw outputs. Attach permissions are restrictive by design on shared hosts.
- **Scalene**: python/native/system split, allocation/copy diagnostics, asyncio await attribution in compatible versions. Command shape is `scalene run` in current releases; consult local `scalene run --help` before specifying output flags.
- **cProfile**: deterministic *function call* instrumentation, call counts and self/cumulative time, significant overhead on call-heavy workloads. Use `python -m cProfile -o file.pstats ...`, then `prof-tools diagnose --cpu-profile`. **Do not load an untrusted pstats file**: the `pstats` format is based on Python `marshal`, not pickle, but malformed or very large inputs remain untrusted data.
- **pyinstrument**: call-stack sampling with good application-level presentation; complement py-spy, particularly when running and attaching are constrained. Always check installation.
- **Memray**: allocation and native-extension memory; Linux and macOS, not a generic time profiler.
- **line_profiler**: targeted line-level profiling, often high overhead; appropriate after locating a small Python function.
- **Python stdlib sampling**: evolving rapidly; only use if installed interpreter exposes the relevant module, don't assume it exists on CPython 3.12/3.13/3.14.
- **Linux perf Python symbolization**: `PYTHONPERFSUPPORT=1` and `-X perf` on supported CPython >=3.12. Compiled extensions should use debug symbols/frame pointers. `-X perf_jit` is a distinct later feature and may require `perf inject`.

## Escalation and correctness

When replacing Python with compiled code, keep public API, dtype/overflow, error propagation, thread safety, data alignment, zero-copy lifetime and memory ownership unchanged. Benchmark end-to-end with original real data. Return to pure-Python maintainable code if a small speedup doesn't justify a new native build toolchain or ABI burden.
