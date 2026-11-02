# Linux CPU systems attribution and interference

This reference is not a license to attach to other workloads or change shared systems. Always record collection permissions and owner.

## CPU resources and boundaries

- Query cpuset (`os.sched_getaffinity`), per-cgroup `cpu.max`, `cpu.stat`, `cpuset.cpus.effective`, `memory.max`, `memory.current`, NUMA online nodes, CPU governor, SMT, topology, process threads and specific thread affinity. `os.cpu_count()` alone is not a reliable estimate of allocated compute capacity under cgroups.
- `cpu.stat` `nr_throttled` and `throttled_usec` must be differenced across a workload interval; quoting a cumulative count from process startup is not proof that the measured step throttled.
- CPU frequency boost, DVFS and thermal limits affect short trials. Preserve environment and paired trial ordering; don't change governor/clock without authorization.
- Shared-node interference, container memory pressure, page cache churn, kernel schedulers and background system agents require noisy-measurement analysis. A regression that disappears when alone is not proof of faster code.

## Waiting vs execution

- `time.perf_counter()` measures elapsed; `time.process_time()` measures CPU time consumed by the process, possibly across threads. Process CPU time excludes time spent on a GPU. A low ratio suggests waiting/idle; a high ratio >1 indicates multiple CPU cores busy, not >100% utilization bug.
- Profile wait with Python `--idle` samples, syscall tracing only if authorized, I/O telemetry, distributed load-balance and queue occupancy. Validate exact sample clock to avoid mistaking idle frames as expensive CPU work.
- Distributed PyTorch DataLoader producers, NCCL/RCCL launch helpers, memory pin threads and Python multiprocessing create overlapping CPU jobs. Attribute the **unhidden delay on step completion**; raw host spans often overlap each other and GPU kernels.
- For locks, quantify threads waiting, runqueue length, critical section duration and lock owners. Avoid moving to spin locks without evidence and a total CPU usage guardrail.

## NUMA and MI300A

- For x86 dual-socket CPU nodes, compare CPU placement and allocation first touch. When allowed, `numactl --hardware`, `numastat -p $PID`, `lscpu -e` help diagnose socket-local vs remote access.
- On MI300A, 24 Zen 4 CPU cores share physical HBM with CDNA 3 GPU. This changes the PCIe copy model, but doesn't eliminate CPU cache misses, synchronization, memory ownership, paging, queues, locks or heterogeneous bandwidth contention. The GPU reaches HBM at vastly different rates than the CPU. Profile whether additional CPU parallelism speeds **critical-path** preparation rather than merely consuming shared HBM bandwidth.
- Do not use H100 or MI300A GPU peak TFLOPS as CPU peak. CPU software/hardware reference should be generated for the actual CPU architecture when important.

## Linux perf security and permissions

- `/proc/sys/kernel/perf_event_paranoid` governs unprivileged monitoring, and container capabilities may restrict further. `ptrace_scope` limits attaches. Use `prof-tools inspect --kind cpu-environment` to report these; do not change them from the skill. If `perf` fails, capture error and move to child-process Python samplers or deterministic application counters.
- Perf sampling is **not deterministic**; report sample rate, clock, missed events, flags, process/thread scope, call graph success, and whether counters were scaled. `perf record -g` may use frame pointers or DWARF stack unwinding, with different overhead. On macOS use platform-native Instruments or `samply` when available; Windows use Windows Performance Recorder/Analyzer or platform-available sampling; command recipes here assume Linux.
- Minimize trace retention; names, paths, arguments and stack frames can reveal proprietary code/data. Avoid system-wide `perf -a` unless explicitly authorized.
