---
name: analyze
description: Read-only semantic performance review of a codebase, with optional profiler traces, benchmark summaries, or CSV data; rank likely algorithm, dataflow, scheduling, memory, library, kernel, and distributed improvements with evidence and validation ideas.
disable-model-invocation: true
---

# Analyze performance opportunities

Use this skill when the user wants recommendations before authorizing code changes or a benchmark campaign. This workflow is read-only: do not edit files, run candidate implementations, or start `prof-tools campaign`.

Inspect the relevant implementation, callers, tests, and workload semantics. When available, use `prof-tools diagnose` for supported trace/profile evidence and `prof-tools inspect` for unfamiliar trace schemas. Read benchmark summaries or CSVs as observations with their measurement conditions; ask what fields mean if the schema is ambiguous.

Relate evidence to source behavior. Screen the relevant opportunity families: algorithm/algebra, dataflow, scheduling, memory, library use, kernels, and distributed execution. Rank recommendations by likely end-to-end value and evidence quality. For each, state:

- the source location and observed evidence supporting the hypothesis;
- the mechanism that could reduce work, movement, synchronization, or exposed critical-path time;
- important semantic risks or missing workload coverage;
- the cheapest experiment that could falsify the idea and what must be measured to confirm it.

Separate observations from inferences. A profile identifies where time was observed; it does not by itself prove that changing that code will improve end-to-end performance. Do not infer savings by summing overlapping kernel durations, present speculative speedups as measurements, or recommend profiler-enabled timing as acceptance evidence. Prefer a short ranked report with uncertainty and the evidence needed to decide.

If the user wants implementation and empirical optimization, stop at the recommendations and offer the explicit `/optimize` workflow; do not silently cross into editing or campaign execution.
