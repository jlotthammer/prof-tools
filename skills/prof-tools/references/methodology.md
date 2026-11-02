# Measurement and optimization methodology

Define a primary application-level metric and workload distribution before tuning. The canonical `workload.json` has `schema_version`, `metric`, `pairs`, `warmup`, `max_case_regression`, `workloads` with positive weights summing to one, explicit workload identity, baseline/candidate argv and independent reference-output verification commands, plus numerical `atol`/`rtol`. Optional `memory_metric` and `memory_limit_bytes` are constraints, not a second primary objective. See `examples/sequence-window-case/suite.json` in the toolkit.

Use unprofiled, independent process A/B trials, paired randomized order, warmup and reported uncertainty. Separate compilation from steady state, process init from step timing, and kernel microbenchmarks from application results. Beware asynchronous launches, graph replay, compilation cache, clocks, thermal drift, background contention, CUDA/HIP launch overhead, incorrect shapes/strides, and output shortcuts. Real end-to-end improvements must survive on the actual weighted operating distribution and all required shapes/ranks.

Read specialist reference details only when relevant:
- [Benchmark design](details/benchmark-design.md)
- [CPU experiment design](details/cpu-experiment-design.md)
- [Measurement triage](details/triage.md)
- [Optimization patterns](details/optimization-patterns.md)
- [CPU memory diagnosis](details/cpu-memory.md)

Machine hardware claims must be marked *vendor peak*, *derived*, or *measured*. See [hardware formulas/porting](hardware/method-and-porting.md), [H100 SXM5](hardware/h100-sxm5.md) and [MI300A](hardware/mi300a.md). Pin exact SKU, toolchain, partition mode, runtime and topology.
