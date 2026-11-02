# Automated trace diagnosis: validated evidence contract

Run `prof-tools diagnose --trace short.sqlite --marker train_step --out diagnosis.json` to obtain a consistent report. Add `--torch-trace torch.json` for explicit PyTorch/Kineto CPU→GPU flow evidence; `--counter-file ncu.csv --counter-manifest capture.json` for hardware counters; or `--ranks-manifest ranks.json` for distributed analysis.

## Counter capture contract

One JSON capture manifest **per profiling run** is mandatory, with exactly these fields: `vendor`, `architecture`, `profiler`, `profiler_version`, `command`, `replay_mode`, `workload_id`, `device_id`, `conditions` (object). Example:

```json
{"vendor":"nvidia","architecture":"sm_90a","profiler":"ncu","profiler_version":"2026.1","command":"ncu --csv --page raw ...","replay_mode":"kernel replay","workload_id":"gemm-bf16-m128-n128-k2048","device_id":"GPU-...","conditions":{"precision":"bf16","shapes":[128,128,2048],"clocks":"unlocked","profiling_passes":"as reported"}}
```

Do not invent capture values. Use `ncu --csv --page raw --print-units base -- ...` or `ncu --import file.ncu-rep --page raw --csv` (confirm installed flag syntax), then `prof-tools diagnose --counter-file ncu.csv --counter-manifest capture.json`. For ROCm, run `rocprof-compute analyze -p <workload> --output-format csv` or `--output-format db`. A ROCm analysis *directory* is parsed using recognizable long-format metric/value/unit columns; unsupported per-view CSV layouts are listed, not silently guessed. A `.db` must provide `--table <table_or_view> --column-map <json>` obtained by inspecting the schema. `--column-map` maps abstract fields `metric`, `value`, `unit`, optional `kernel`, `dispatch`, `device` onto actual column names. This is an explicit adapter, not a promise of arbitrary report format compatibility.

For controlled counter comparison call `prof_tools.counters.compare_counter_reports("old.csv", "new.csv", "old.json", "new.json")` from Python. Mismatch in architecture, capture mode, conditions or workload is a hard error. Comparing dispatch IDs relies on validating identical launch indexing manually: a matching row key is *not* proof of identical kernel work.

## PyTorch / source attribution

`prof_tools.torch_trace.analyze_torch_trace --file torch_trace.json`: reads the exported Chrome JSON event timeline, recognizes CPU and GPU activity categories, and joins only explicit Chrome flow endpoints with matching PID and thread. CPU ranges may nest; shortest enclosing recorded CPU range is returned as an observed association. Correlation **is not source-code ownership** if the trace omitted relevant runtime events. Preserve `record_shapes=True` and `with_stack=True` only when overhead is acceptable. Use `torch.profiler` scheduled capture for a bounded steady-state step, not the paired benchmark.

## Distributed traces

`prof-tools diagnose --ranks-manifest ranks.json` expects a list of `ranks` with `rank` and `trace` path, optional common `clock_domain`, `clock_offset_ns`, `alignment_error_ns`, optional `step_marker`, optional `collectives` entries with `rank`, `sequence_id`, `kind`, `start_ns`, `end_ns`. **All ranks** need a common clock-domain identifier and calibrated offsets/error bounds to calculate cross-rank start skew. A collective must carry a reliable sequence ID from application/framework instrumentation. Matching occurrences by name or position can silently conflate independent collectives. Compute/communication overlap is temporal intersection, not proof of hidden latency. Independent per-rank step-marker durations can be compared without clock alignment.

## Explicit dependency evidence

`prof_tools.dependencies.analyze_dependency_graph --file dag.json` expects `nodes` with `id`, `duration_ns` and `edges` with `from`, `to`, `evidence`. It checks cycles, computes a longest weighted path, and refuses missing evidence. No CUDA event, graph node or collective dependencies are fabricated merely because timestamps overlap. Until the graph is complete and every edge verified, the result is *not* a certified global critical path or exposed communication cost.

## Automatic findings

Findings are observations or investigation hypotheses, not optimization claims. Read `severity`, `confidence`, `evidence`, and `next_experiment`. An observed empty GPU timeline can arise from CPU input stalls, compilation, missing domains or profiler gaps; a launch-to-start delay can arise from GPU queue depth or dependencies; a sync API may overlap productive work. Profiled timing is never the acceptance benchmark. For each proposed patch, use `prof-tools evaluate` on unchanged independent processes with correctness validation and a recorded experiment manifest.

## Known boundaries

- Specific vendor counter values are preserved **verbatim**, not converted or treated as interchangeable on CUDA and ROCm; there is no universal metric name/metric formula layer.
- Real Nsight Systems and `rocpd` version fixtures must validate every schema mapping before claiming on-hardware support.
- The rank manifest describes an independently calibrated clock-domain mapping; the toolkit does **not** perform NTP/PTP alignment or NCCL/RCCL sequence-ID capture automatically.
- The explicit DAG analyzer calculates the longest *weighted* path of the supplied DAG; it does not discover the complete execution graph.
- Long traces are loaded in memory. Keep captures short; SQL pushdown/streaming is future work.
