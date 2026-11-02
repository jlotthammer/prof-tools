"""Non-invasive environment inventory. Never requests admin rights or changes clocks."""
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


TOOLS = ("nvidia-smi", "nsys", "ncu", "nvcc", "amd-smi", "rocm-smi", "rocminfo", "rocprofv3", "rocprof-compute", "rocpd", "hipcc", "rocprof-sys-sample", "srun")


def run_info(argv, timeout=5):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return {"exit_code": result.returncode, "output": (result.stdout + result.stderr)[:7000]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def inventory():
    tools = {name: shutil.which(name) for name in TOOLS}
    result = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(), "system": platform.platform(), "python": sys.version.split()[0],
        "tools": tools,
        "nvidia": run_info(["nvidia-smi", "--query-gpu=name,uuid,driver_version,memory.total,compute_cap,power.limit", "--format=csv,noheader"]) if tools["nvidia-smi"] else None,
        "amd": run_info(["amd-smi", "list"]) if tools["amd-smi"] else None,
        "rocm": run_info(["rocminfo"]) if tools["rocminfo"] else None,
        "git": run_info(["git", "rev-parse", "HEAD"]),
        "git_status": run_info(["git", "status", "--porcelain=v1"]),
        "visibility": {k: os.environ.get(k) for k in ("CUDA_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "GPU_DEVICE_ORDINAL", "SLURM_JOB_ID", "SLURM_JOB_NUM_NODES", "WORLD_SIZE") if k in os.environ},
    }
    from .cpu import cpu_inventory
    result["cpu"] = cpu_inventory()
    try:
        import torch
        result["pytorch"] = {"version": torch.__version__, "cuda_build": torch.version.cuda, "hip_build": torch.version.hip, "gpu_available": torch.cuda.is_available()}
        if torch.cuda.is_available():
            result["pytorch"]["devices"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    except ImportError:
        result["pytorch"] = None
    return result
