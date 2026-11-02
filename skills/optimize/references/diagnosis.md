# Programmatic trace diagnosis

`prof-tools diagnose` consumes Nsight Systems / ROCm SQLite activity, typed hardware counters with capture manifests, PyTorch Chrome trace explicit flows, per-rank manifests with known clock domains, and user-supplied dependency graphs. It outputs JSON findings with direct observations, confidence/limitations, and suggested falsifying measurements; `--markdown` adds a human handoff. `--cpu-profile` reads `.pstats` or folded stacks and marks hotspot results observational.

Use `prof-tools inspect --kind trace-events --file <db> --out events.jsonl` for a normalized event stream, and `--kind trace-schema` for unknown database versions. Specialized importers remain Python APIs: `prof_tools.trace_diagnostics`, `prof_tools.counters`, `prof_tools.torch_trace`, `prof_tools.distributed`, `prof_tools.dependencies`, `prof_tools.gpu_dependencies`, `prof_tools.cpu` and `prof_tools.cpu_compare`.

Direct observations are NOT proofs of causality. In particular, interval overlaps do not establish exposed communication; match collectives using stable sequence identifiers, and calibrate cross-rank clocks before interpreting global skew. Event-stream dependency graphs require explicit edges and must account for missing events. Hardware counters are architecture-specific, captured with possible replay/serialization, and must be compared only under compatible collection conditions.

- [Automated diagnosis](details/automated-diagnosis.md)
- [SQL/trace analysis](details/programmatic-analysis.md)
