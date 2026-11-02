# Experimental controls and statistical claims

## What to measure

- **Training:** optimizer-step wall time, global tokens/residues/sec, effective batch and grad accumulation, optional loss/grad parity, peak allocated/reserved VRAM and time to target loss where applicable. Distinguish microbatch latency from optimizer-step throughput.
- **Inference:** end-to-end latency distribution (p50/p90/p95/p99), throughput at fixed concurrency, cold/steady start and output quality; count requested versus generated tokens/steps correctly. For generative diffusion, compare full denoising trajectory and identical sampler schedule.
- **Kernel:** representative launch configuration and GPU event latency, compile excluded. Measure warmed repeated invocations with preallocated buffers, and use a vendor hardware counter profiler (NCU or ROCm Compute Profiler) to explain *why* rather than infer end-to-end speedups.

## Controls

Log device UUID/driver, CUDA or ROCm/PyTorch/Triton versions, GPU clocks/power state when available, process/container/Slurm context, code commit+dirty hash, compiler/graph flags, determinism policies, shape distributions, data pipeline and seed policy. Run one experiment at a time; do not silently change device or GPU sharing status. Keep the program's actual execution mode. `torch.compile` cold-start time and warmed runtime are separate outcomes. Compile caches may persist between fresh processes; explicitly document cache policy.

For controlled two-condition comparison: (1) validate each variant independently; (2) warm both conditions; (3) alternate A/B and B/A pairs sequentially on the same device (to reduce drift); (4) use paired ratios, resampling whole pairs for confidence intervals; (5) investigate unstable/outlier runs rather than delete without predefined rules. Independent process starts are not independent GPU conditions if cache or thermal state carries over. A bootstrap interval is descriptive, not a cure for systematic bias.

### Correctness

Classify transformations as exact (e.g., eliminating a duplicate copy) or potentially numerical (reduction order, TF32, lower precision, approximate math, nondeterministic atoms, altered sampler). Record tolerances before testing. For training, test gradients, optimizer states and short trajectories as needed; one forward-output comparison is insufficient. A speed improvement that changes the algorithm or training objective requires explicit approval and a separate quality evaluation.

### Hardware estimates

Use hardware- and precision-correct theoretical limits for FLOP utilization and bandwidth. MFU needs a defensible model-FLOP accounting, e.g. activation recomputation and attention terms as appropriate; do not equate ncu's % of hardware peak with MFU. GPU utilization is an activity proxy. Avoid hard-coded universal thresholds like `GPU utilization <80% implies CPU bound`.
