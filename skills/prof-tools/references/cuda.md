# NVIDIA CUDA diagnosis and optimization

Use Nsight Systems for host/GPU timeline and launch/stream/synchronization evidence; use Nsight Compute only for kernels shown to matter to application runtime. Capture steady state using NVTX and optional CUDA profiler start/stop windows. Export Nsight Systems SQLite for `prof-tools diagnose --trace file.sqlite --marker train_step`; `prof-tools inspect --kind trace-schema --file file.sqlite` reveals unknown layouts. `prof_tools.trace_diagnostics` and `prof_tools.counters` expose programmatic diagnosis and typed NCU counter analysis, including explicit collection manifests.

Do not conflate summed kernel durations, CUDA Graph node launch IDs, stream concurrency, host launch-to-start queueing, and exposed step latency. NCU counter replays can serialize execution and alter cache behavior: never use replay timing as acceptance evidence. Analyze occupancy limits, register pressure, spilling, L2/HBM, bank conflicts, vectorization, TMA/WGMMA when applicable, communication overlap and rank stragglers. Compare cuBLAS/cuDNN/CUTLASS/Triton against custom code; profile only before hardware-specific tuning.

H100 SXM5 needs `sm_90a` for WGMMA and `setmaxnreg`; distinguish other H100 SKUs. See [H100 reference](hardware/h100-sxm5.md), [kernel diagnosis](details/cuda-kernels.md), and [distributed tracing](details/cuda-distributed.md).
