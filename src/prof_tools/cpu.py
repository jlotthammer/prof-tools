"""Read-only CPU environment, trusted pstats, and text collapsed stack summaries.

All outputs are observations, not benchmark results. Profile files may be
large or maliciously malformed: analyze files from trusted sources only.
cProfile uses marshal, not pickle, for pstats serialization. Deterministic
instrumentation has observer overhead and is not an A/B benchmark.
No third-party dependencies.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import platform
import pstats
import shutil
import sys
import sysconfig

CPU_TOOLS = (
    "perf", "py-spy", "scalene", "pyinstrument", "memray", "lscpu",
    "numactl", "taskset", "pidstat", "strace", "bpftrace", "samply",
    "flamegraph", "cargo-flamegraph", "cargo", "rustc", "gcc", "clang",
    "g++", "clang++", "hyperfine", "valgrind", "heaptrack", "turbostat",
)
CPU_ENV_VARS = (
    "OMP_NUM_THREADS", "OMP_PROC_BIND", "OMP_PLACES", "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS", "POLARS_MAX_THREADS", "RAYON_NUM_THREADS",
    "PYTHON_GIL", "PYTHON_CPU_COUNT", "PYTHONPERFSUPPORT",
    "SLURM_CPUS_PER_TASK", "SLURM_JOB_CPUS_PER_NODE", "SLURM_CPU_BIND",
)


def _read_sys(path: str, limit: int = 300) -> str | None:
    try:
        return Path(path).read_text().strip()[:limit]
    except (OSError, UnicodeError):
        return None


def _cpu_name() -> str | None:
    cpuinfo = _read_sys("/proc/cpuinfo", 300_000)
    if cpuinfo:
        for line in cpuinfo.splitlines():
            if line.startswith(("model name", "Hardware", "Processor")) and ":" in line:
                return line.split(":", 1)[1].strip()
    return platform.processor() or None


def cpu_inventory() -> dict:
    """Capture user-visible process constraints without invoking privileged tools."""
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    cpu_max = _read_sys("/sys/fs/cgroup/cpu.max")
    quota_cores = None
    if cpu_max:
        tokens = cpu_max.split()
        if len(tokens) == 2 and tokens[0] != "max":
            try:
                quota, period = map(int, tokens)
                if period > 0:
                    quota_cores = quota / period
            except ValueError:
                pass
    gil_fn = getattr(sys, "_is_gil_enabled", None)
    try:
        gil_enabled = gil_fn() if gil_fn else None
    except (RuntimeError, TypeError):
        gil_enabled = None
    governors = set()
    try:
        paths = Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor")
        for path in paths:
            val = _read_sys(str(path))
            if val:
                governors.add(val)
    except OSError:
        pass
    return {
        "architecture": platform.machine(),
        "cpu_name": _cpu_name(),
        "logical_cpus_reported": os.cpu_count(),
        "affinity_cpus": affinity,
        "affinity_cpu_count": len(affinity) if affinity is not None else None,
        "cgroup_v2_cpu_max": cpu_max,
        "cgroup_v2_cpu_quota_cores": quota_cores,
        "cgroup_v2_cpuset_effective": _read_sys("/sys/fs/cgroup/cpuset.cpus.effective"),
        "cgroup_v2_memory_max": _read_sys("/sys/fs/cgroup/memory.max"),
        "numa_nodes_online": _read_sys("/sys/devices/system/node/online"),
        "transparent_hugepages": _read_sys("/sys/kernel/mm/transparent_hugepage/enabled"),
        "cpu_governors": sorted(governors),
        "linux_perf_event_paranoid": _read_sys("/proc/sys/kernel/perf_event_paranoid"),
        "linux_ptrace_scope": _read_sys("/proc/sys/kernel/yama/ptrace_scope"),
        "python_version": sys.version.split()[0],
        "python_gil_enabled": gil_enabled,
        "python_configured_no_gil": sysconfig.get_config_var("Py_GIL_DISABLED"),
        "python_frame_pointer_flags": {
            "CFLAGS": sysconfig.get_config_var("CFLAGS"),
            "PY_CFLAGS": sysconfig.get_config_var("PY_CFLAGS"),
        },
        "threading_env": {k: os.environ[k] for k in CPU_ENV_VARS if k in os.environ},
        "tools": {name: shutil.which(name) for name in CPU_TOOLS},
        "notes": [
            "Affinity and CPU quota are different constraints: quota can throttle while CPUs remain schedulable.",
            "Do not compare host CPU utilization percentages across different quota/affinity domains.",
            "Some perf and process-attach profilers require kernel permissions; no settings are changed.",
        ],
    }


def cprofile_summary(path: str | Path, top: int = 25, sort: str = "cumulative") -> dict:
    """Summarize a trusted .pstats file (marshal serialization, not pickle)."""
    if top < 1:
        raise ValueError("top must be >= 1")
    if sort not in {"self", "cumulative", "calls"}:
        raise ValueError("sort must be self, cumulative, or calls")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    stats = pstats.Stats(str(source))
    items = []
    for key, value in stats.stats.items():
        filename, lineno, function = key
        primitive_calls, total_calls, self_time, cumulative_time, _callers = value
        items.append({
            "filename": str(filename),
            "line": int(lineno),
            "function": str(function),
            "primitive_calls": int(primitive_calls),
            "total_calls": int(total_calls),
            "self_time_s": float(self_time),
            "cumulative_time_s": float(cumulative_time),
        })
    key = {"self": "self_time_s", "cumulative": "cumulative_time_s", "calls": "total_calls"}[sort]
    items.sort(key=lambda x: (-x[key], -x["self_time_s"], x["filename"], x["line"], x["function"]))
    return {
        "file": str(source.resolve()),
        "format": "cProfile/pstats deterministic function-call profile",
        "sort": sort,
        "function_count": len(items),
        "total_primitive_calls": int(stats.prim_calls),
        "total_function_calls": int(stats.total_calls),
        "sum_self_time_s": float(stats.total_tt),
        "functions": items[:top],
        "caveats": [
            "Function cumulative times overlap across caller/callee chains; never sum them.",
            "cProfile pstats files use marshal; accept only trusted input files because malformed data can exhaust resources.",
            "cProfile instruments Python call boundaries and perturbs runtime. These are NOT unprofiled measurements.",
            "Native library time is usually charged to a Python boundary; drill into C/C++ with sampling/perf.",
            "Thread/process coverage depends on where cProfile was enabled; it is not automatically whole-job.",
        ],
    }


def collapsed_stacks_summary(path: str | Path, top: int = 25) -> dict:
    """Summarize trusted *text* flamegraph/collapsed stack input, without execution.

    Standard format is `root;child;leaf WEIGHT`, e.g. py-spy raw output,
    stackcollapse-perf.pl output or other folded stack producers. WEIGHT
    represents whatever the source profiler sampled, NOT necessarily CPU time.
    Inclusive weights are counted once per stack frame, including recursion;
    total_weight is the sum of leaf sample weights, not the sum of inclusives.
    """
    if top < 1:
        raise ValueError("top must be >= 1")
    source = Path(path)
    inclusive: dict[str, float] = {}
    exclusive: dict[str, float] = {}
    samples = 0
    total = 0.0
    for lineno, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            path_part, count_part = raw.rsplit(maxsplit=1)
            weight = float(count_part)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"malformed collapsed stack on line {lineno}") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"invalid sample weight on line {lineno}")
        frames = [frame.strip() for frame in path_part.split(";")]
        if not all(frames):
            raise ValueError(f"empty stack frame on line {lineno}")
        total += weight
        samples += 1
        for frame in set(frames):
            inclusive[frame] = inclusive.get(frame, 0.0) + weight
        leaf = frames[-1]
        exclusive[leaf] = exclusive.get(leaf, 0.0) + weight
    if not samples:
        raise ValueError("no collapsed stacks found")
    ordered = sorted(inclusive, key=lambda k: (-exclusive.get(k, 0.0), -inclusive[k], k))
    return {
        "file": str(source.resolve()),
        "format": "folded/collapsed stacks root;child;leaf weight",
        "nonempty_stack_lines": samples,
        "total_leaf_weight": total,
        "frames": [
            {"frame": name, "exclusive_weight": exclusive.get(name, 0.0),
             "inclusive_weight": inclusive[name],
             "exclusive_fraction": exclusive.get(name, 0.0) / total,
             "inclusive_fraction": inclusive[name] / total}
            for name in ordered[:top]
        ],
        "caveats": [
            "Weights are source-defined (e.g. sampled CPU stacks vs wall-clock); never label as seconds without provenance.",
            "Inclusive weights overlap on caller/callee chains; never sum them.",
            "Recursive frames count once per stack for inclusive attribution; method is not a call-count profiler.",
            "Thread/process/subprocess/idle and native-frame coverage depend on the upstream sampler.",
        ],
    }
