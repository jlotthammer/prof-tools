# AMD ROCm diagnosis and optimization

Use ROCprofiler SDK `rocprofv3` for HIP/kernel/memory/call tracing, native `rocpd` SQLite, ROCTx labels, ROCm Systems Profiler where available, and ROCm Compute Profiler for replayed hardware counters. Query database programmatically with `prof-tools diagnose --trace file.db`; inspect version-specific schemas using `prof-tools inspect --kind trace-schema --file file.db`. Use typed vendor-specific counter manifests via `prof_tools.counters` and distinguish runtime queues, XGMI/RCCL communication, partition mode and placement.

For `gfx942` MI300A, account for wave64, 64 KB LDS per CU, per-XCD L2 cache, MFMA, FNUZ FP8, multiple XCDs, unified CPU/GPU physical HBM, and device-scope synchronization. Do not assume the MI300X profile or partition modes apply unchanged to MI300A. Avoid expensive or experimental sampling on shared machines without authorization. Performance measurements must remain unprofiled.

Compare hipBLASLt, Composable Kernel, Triton AMD, AITER and native HIP before custom MFMA tuning. Use [MI300A reference](hardware/mi300a.md) and [cross-vendor formulas](hardware/method-and-porting.md).
