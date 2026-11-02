"""Example: scope deterministic Python call profiling to a hot region.

Usage:
    from cpu_profile_region import profile_region
    with profile_region("perf_runs/region.pstats"):
        do_steady_state_work()

The resulting .pstats uses pickle internally. Treat it as trusted input only.
Profiles perturb execution; benchmark the unchanged production path separately.
"""
import cProfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def profile_region(output):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        yield
    finally:
        profiler.disable()
        profiler.dump_stats(str(path))
