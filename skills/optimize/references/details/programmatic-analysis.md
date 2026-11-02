# Programmatic GPU and CPU trace analysis

**Default: analyze the artifact programmatically; do not open a trace viewer merely to read timing or tabular data.** Collect short steady-state traces and save source files, environment, profiler versions, generated reports and missing-domain caveats.

## Agent workflow

1. `prof-tools inspect --kind trace-schema --file run.sqlite --out schema.json`: discover the actual Nsight/rocpd schema and available columns.
2. `prof-tools diagnose --trace run.sqlite --out report.json`: report kernel/API/copy/memset intervals, cumulative durations, p50/p95/max, per-device union, kernel-copy overlap, NCCL/RCCL-name heuristic overlap, synchronization-API observations and unambiguous correlation-based dispatch delays. Absent domains appear in `missing_domains`.
3. `prof-tools diagnose --trace run.sqlite --marker train_step --out steps.json`: compare host marker durations and intersecting GPU activity over repeated iterations. These ranges are CPU time windows, **not** ownership evidence or synchronized GPU step timings.
4. `prof-tools inspect --kind trace-events --file run.sqlite --event-kind all --out events.jsonl`: export normalized per-event records `{kind,name,start,end,device,stream,correlation,size,category}` to JSON Lines. Use `--event-kind kernel|copy|api|memset` or `--start-ns`, `--end-ns` for specific questions. Output is a new file; existing files are never overwritten.
5. `prof_tools.trace_diagnostics.compare_traces("before.sqlite", "after.sqlite")`: exact-name kernel call-count, p50/p95 and cumulative-duration diffs. This is **not** performance acceptance. Require unprofiled `prof-tools evaluate` and correctness checks.
6. CPU comparisons: `prof_tools.cpu_compare.compare_pstats --format pstats --baseline before.pstats --candidate after.pstats --out cpu-diff.json`, or `--format folded` for frame-weight fractions. Same functions must have matching source filenames and lines; sample counts are not runtime.

## Interpretation and uncertainty

- `duration_sum_ns` may double-count overlapping activity; `kernel_busy_union_ns` does not. Neither equals occupancy, critical path, achieved bandwidth or necessarily elapsed application time.
- `kernel_copy_overlap_ns` and `compute_collective_overlap_ns` are temporal intersections. The collective identifier is a **name heuristic**, not verified communication causality. A collective can be hidden or partially exposed; overlap alone cannot determine exposed time.
- `observed_no_activity_ns` means no **captured** GPU kernel/copy intervals in the selected time range, not necessarily host overhead.
- `synchronization_api_observations` sum host API intervals across threads, which can themselves overlap. They do not prove avoidable stalls.
- `launch_queue_diagnostics` measures API return to kernel start for *unique* matching correlation IDs, with caveats for CUDA graphs and multi-process ID reuse. Missing correlation is not zero queueing.
- Host markers can end before an asynchronous kernel does. For NVTX ownership use correlation-based NVIDIA `nvtx_gpu_proj_trace` / `nvtx_gpu_proj_sum`, not time containment.
- Profiles are perturbed experiments. Never use profile-to-profile deltas as final benchmark evidence.

## Native analysis to invoke instead of reinventing

NVIDIA: `nsys stats -r cuda_gpu_kern_sum,cuda_api_sum,cuda_gpu_mem_time_sum --format csv capture.nsys-rep`; use `nsys analyze`, `nsys recipe` for API synchronizations, kernel pacing, GPU-projected NVTX and NCCL overlap/straggler analysis. Query raw SQLite for additional questions. Use Nsight Compute's supported report interface for hardware counters and replay-sensitive metrics.

ROCm: `rocpd query -i capture.db --query 'SELECT * FROM kernels LIMIT 5'`; if available, `rocpd2summary -i capture.db --format json`; `rocprof-compute analyze -p <profile_directory> --output-format db` creates a separate **counter-analysis SQLite** database, not the execution timeline rocpd database. Inspect that database's schema before creating queries.

CPU: `prof-tools diagnose --cpu-profile file.pstats` / `--cpu-format folded` and `prof_tools.cpu_compare.compare_pstats` provide machine-readable summaries. For perf.data, py-spy speedscope, Memray or Linux PMU data use version-specific native export; direct ingestion is not yet implemented here.

## Not yet implemented

- CUDA Graph/HIP Graph causal dependencies and exact cross-thread GPU critical path.
- Multi-rank clock alignment, rank straggler attribution, or proven exposed collective latency.
- Nsight Compute and ROCm Compute Profiler per-counter semantic normalization, per-PC / ISA instruction analysis.
- Direct Chrome/Perfetto/torch.profiler, perf.data, speedscope, Memray ingestion.
- SQL predicate pushdown and out-of-core streaming for extremely large captures; the current adapter materializes a deliberately **short** trace.
- Verified compatibility against actual H100 and MI300A profiler outputs (synthetic SQL fixtures tested only).

An unsupported field must be reported as **unobserved**, not treated as zero. For very large traces prefer vendor `nsys recipe`, Parquet exports or `rocpd query` filtering rather than materializing all events.

## Sources

- https://docs.nvidia.com/nsight-systems/AnalysisGuide/
- https://docs.nvidia.com/nsight-systems/UserGuide/
- https://docs.nvidia.com/cupti/main/main.html
- https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/how-to/using-rocpd-output-format.html
- https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/how-to/analyze/cli.html
