#!/usr/bin/env python3
"""Minimal PyTorch GPU training example for NVIDIA CUDA or AMD ROCm.

This is a smoke test, not a model-performance proxy. For real work, replace
`train_step` with a full representative production training/inference step.
`--profile` adds diagnostic markers and MUST NOT be used for A/B comparisons.
"""
import argparse
from contextlib import contextmanager
import ctypes
import json
import time

import torch


class Marker:
    def __init__(self, enabled):
        self.enabled = enabled
        self.is_rocm = bool(torch.version.hip)
        self.lib = None
        if enabled and self.is_rocm:
            try:
                self.lib = ctypes.CDLL("libroctx64.so")
                self.lib.roctxRangePushA.argtypes = [ctypes.c_char_p]
                self.lib.roctxRangePushA.restype = ctypes.c_int
                self.lib.roctxRangePop.restype = ctypes.c_int
            except OSError:
                self.lib = None
                print("WARNING: ROCTx library unavailable; no ROCTx spans", flush=True)

    @contextmanager
    def range(self, name):
        if self.enabled:
            if self.is_rocm:
                if self.lib:
                    self.lib.roctxRangePushA(name.encode())
            else:
                torch.cuda.nvtx.range_push(name)
        try:
            yield
        finally:
            if self.enabled:
                if self.is_rocm:
                    if self.lib:
                        self.lib.roctxRangePop()
                else:
                    torch.cuda.nvtx.range_pop()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--seq", type=int, default=128)
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--profile", action="store_true", help="diagnostic annotations; never use for A/B")
    args = ap.parse_args()
    if not torch.cuda.is_available():
        ap.error("No CUDA or ROCm GPU visible to PyTorch")
    if min(args.batch, args.seq, args.hidden, args.steps) <= 0 or args.warmup < 0:
        ap.error("Dimensions and steps must be positive; warmup must be nonnegative")

    torch.manual_seed(args.seed)
    model = torch.nn.Sequential(torch.nn.Linear(args.hidden, args.hidden),
                                torch.nn.GELU(), torch.nn.Linear(args.hidden, args.hidden)).to("cuda")
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4)
    x = torch.randn(args.batch, args.seq, args.hidden, device="cuda")
    marker = Marker(args.profile)

    def train_step():
        opt.zero_grad(set_to_none=True)
        with marker.range("forward"):
            loss = model(x).square().mean()
        with marker.range("backward"):
            loss.backward()
        with marker.range("optimizer"):
            opt.step()

    for _ in range(args.warmup):
        train_step()
    torch.cuda.synchronize()
    begin = time.perf_counter()
    for _ in range(args.steps):
        with marker.range("train_step"):
            train_step()
    torch.cuda.synchronize()
    elapsed_s = time.perf_counter() - begin

    identity = {"model": "tiny_mlp_smoke", "batch": args.batch, "seq": args.seq,
                "hidden": args.hidden, "seed": args.seed, "dtype": "fp32", "world_size": 1}
    print("PROF_TOOLS_RESULT=" + json.dumps({"metrics": {
        "step_time_ms": elapsed_s * 1000 / args.steps,
        "tokens_per_s": args.batch * args.seq * args.steps / elapsed_s,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated()},
        "workload": identity}))


if __name__ == "__main__":
    main()
