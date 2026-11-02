# Python profiling choices, limitations and stable commands

| Question | Preferred approach | Caveat |
|---|---|---|
| Slow Python service with unknown cause | py-spy wall-sampling + per-thread inspection | idle filtering, ptrace/attach limits, sampling uncertainty |
| Exact Python function call counts | cProfile → `prof-tools diagnose --cpu-profile` | deterministic instrumentation overhead; no native detail |
| Pure-Python line bottleneck | Scalene CPU sampling | per-line cost estimation, check tool version |
| Asynchronous request stalls | Pyinstrument or CPython 3.15 async-aware sampler | logical task time ≠ CPU execution time |
| Does the GIL block parallelism? | py-spy GIL option, or CPython 3.15 `--mode=gil` | excluding native frames is not a total runtime share |
| Python vs C/C++ extension time | py-spy `--native`; Linux perf + `python -X perf` | debug symbols; native support varies by OS |
| Does a hot list/dict operation allocate excessively? | `tracemalloc` for Python allocations; Memray for native allocations | memory allocation ≠ residency; global RSS may remain high |
| Tiny function benchmark | `pyperf` and controlled affinity | microbenchmark can miss surrounding allocation/cache behavior |

## Multi-process and ML workloads
- Profile a representative data loader rank and worker as well as parent. Record prefetch depth, batches/sec and stalls at GPU dispatch; include GPU profiling if kernels are material.
- Numerical libraries have their own thread pools. Check `threadpoolctl.threadpool_info()` where available and record `OMP_NUM_THREADS`, MKL/BLAS limits rather than assuming Python's GIL controls those kernels.
- Profiles sampled at the process scope cannot prove *user-request latency* attribution without request/phase timing.
- Free-threading: `sys._is_gil_enabled()` when available, Python build and extension compatibility must all be verified. Importing an unsupported extension may re-enable a GIL.

## Official upstream references
- https://github.com/benfred/py-spy
- https://docs.python.org/3/library/profile.html
- https://docs.python.org/3/library/profiling.sampling.html (3.15+)
- https://pyinstrument.readthedocs.io/en/latest/
- https://github.com/plasma-umass/scalene
- https://pyperf.readthedocs.io/en/latest/
- https://docs.python.org/3/howto/free-threading-python.html
