# CPU profiling: Python, C++, Rust

Classify **Python interpreter work**, native extension/BLAS time, OS scheduling and waiting, NUMA/cache/memory effects, and CPU↔GPU submission separately. Use wall time and actual CPU time; determine whether the code holds/releases the GIL before proposing threading. CPU tools do not require CUDA/ROCm.

## Profiling and programmatic analysis

- Capture Python CPU call profiles with `python -m cProfile -o profile.pstats module.py`, or use `py-spy record --format raw -o profile.folded -- python app.py` for sampled stacks. Use `prof-tools diagnose --cpu-profile profile.pstats --cpu-format pstats` or `--cpu-format folded`; read-only summaries are available in `prof_tools.cpu` and comparison algorithms in `prof_tools.cpu_compare`.
- For Python native attribution consider py-spy native stack support, Linux `perf`, Scalene (Python/native and memory), pyinstrument, Memray, and Python sampling where supported. Check profiler permissions, symbols and Python version; avoid trusting sampled percentages as exact exposed cost.
- For C++ and Rust use optimized builds with symbols/frame pointers, `perf record/stat`, flamegraphs, heaptrack/valgrind where applicable, `cargo flamegraph`, and native benchmark tests. Inspect compiler vectorization, cache misses, branch behavior, CPU affinity, NUMA pinning, huge pages and thread oversubscription.
- For CPU/GPU APU co-design, separate latency handoff from bandwidth consumption; do not assume zero-copy makes CPU high-bandwidth loops competitive with GPU kernels. In MI300A verify XNACK, allocation kind and huge-page behavior.

## Specialist reference material

- [Python diagnostics](details/python-diagnostics.md)
- [Python profilers](details/python-profilers.md)
- [Native counters](details/cpu-native-counters.md)
- [Native workflow](details/cpu-native-workflow.md)
- [CPU systems analysis](details/cpu-systems.md)
- [CPU decision tree](details/cpu-decision-tree.md)
