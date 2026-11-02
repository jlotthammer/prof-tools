# Distributed execution diagnosis

In DDP/FSDP/TP/pipeline runs, instrument all relevant ranks. Capture rank identity, world size, topology and placement, stable collective sequence IDs, and clock calibration with explicit uncertainties. Observe compute, comm, synchronization and exposed step-level cost separately. Summed NCCL/RCCL durations may be fully hidden or overlap, and a fast rank can still wait for a straggler. Test communication-reduction vs communication-overlap vs algorithm restructuring on an unprofiled representative end-to-end workload. Use native `prof_tools.distributed`, `prof_tools.gpu_dependencies` and `prof_tools.dependencies` for specific analyses, while `prof-tools diagnose --ranks-manifest` produces the standard report.

- [NVIDIA distributed recipes](details/cuda-distributed.md)
- [Hardware porting](hardware/method-and-porting.md)
