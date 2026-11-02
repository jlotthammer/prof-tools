# Hardware modeling, measurement and cross-vendor porting

**Scope:** NVIDIA H100 SXM5 vs AMD Instinct MI300A, not generic Hopper vs CDNA3. Sources, provisional facts and verification steps live in the two sibling SKU files. Vendor peak, derived estimate and measurement are separate categories; never call a modeled peak a measured result.

## Units and reproducibility
- KB/KiB-like on-chip capacities in these references use 1 KiB = 1024 B; vendor TB/s and TFLOP/s use decimal 10^12. Vendor `GB` capacity wording is retained; query physical memory before fitting allocations.
- Dense means no structured sparsity. H100's public product page reports tensor performance **with sparsity**; divide by two for dense TF32/BF16/FP16/FP8. AMD's MI300A datasheet publishes both dense and sparse peaks.
- Peaks assume specific clocks and algorithms. `achieved_FLOP/s / peak_FLOP/s` is only meaningful with a documented FLOP accounting and matching math mode. Report measured clock, datatype, matrix layout and any sparsity.
- The same program compiled for `sm_90` rather than `sm_90a`, or for `gfx942:xnack+` instead of `:xnack-`, may execute different instructions. Record compiled artifacts and ISA when diagnosing a missing fast path.

## Capacity, throughput and limiting mechanism
1. Capacity: memory footprint (parameters, optimizer, activations, temp buffers, fragmentation, graph pools) vs allocatable HBM; wave/register/shared-memory residency per unit.
2. Throughput: ideal arithmetic intensity AI = operations / bytes crossing the memory boundary being analyzed. Do not use HBM traffic for an L2-limited kernel, and do not infer actual traffic just from tensor dimensions.
3. Mechanism: latency, occupancy, instruction issue, dependences, cache capacity, launch and inter-rank waits.
4. Numerics: reduction order, FP8 encodings, accumulation and loss scaling, determinism.
5. Placement: SM/cluster vs XCD/CU, multi-device fabric, CPU/GPU memory ownership and page placement.

### Formulas: ideals only
- HBM ridge point: `dense peak TFLOP/s / peak HBM TB/s` FLOP per HBM byte. Different for each dtype, precision mode and device.
- GEMM `C[M,N] = A[M,K] @ B[K,N]`: with `b` bytes per A/B/C element and a single A/B read and C write, `AI_ideal = 2MNK / (b(MK+KN+MN))`. For square BF16, `AI=n/3`. A larger FP32 result changes output traffic, and real spills, reloading, cache reuse, epilogues and attention change actual AI.
- Output tile operand reuse across a K slice: `AI = 2 BM BN / (b(BM+BN))`, **excluding** the output write and any reloads. Tiled GEMM stage bytes: `(BM+BN)*BK*b`; subtract scratchpad needed for output/synchronization before computing viable buffering stages.
- For BF16 GEMV-like decode without reuse, one weight serves approximately `batch` FLOP/weight byte. KV-cache, activation reads and weight sharing change the crossover.
- Wave quantization: if `T` independent CTAs/workgroups are evenly scheduled onto `U` units without residency overlap, waves = `ceil(T/U)`, whole-job fill = `T/(U*waves)`; last-wave fill = `((T-1)%U+1)/U`. This is an *idealized one-block-per-unit approximation*, not a scheduler prediction. Persistent grids, block residency, tile duration variance and placement alter actual occupancy.
- Amdahl bound on end-to-end speedup: `1/[(1-f)+f/s]` for a nonoverlapping fraction `f` accelerated by `s`. For overlapped kernels, `f` must be the *exposed critical-path fraction*, not total dispatch time.
- Communication lower bound: bytes / **measured effective** fabric bandwidth plus startup/synchronization; quoted bidirectional aggregate links are NOT one-way application throughput.

## Concept map
| Mechanism | H100 SXM5 | MI300A |
|---|---|---|
| Compiler | CUDA/PTX `sm_90a` for Hopper-specific WGMMA | HIP/LLVM AMDGPU `gfx942`, optional XNACK target variants |
| Compute unit | 132 SMs | 228 CUs in six XCDs when SPX |
| Execution subgroup | warp of 32, warpgroup of 128 for WGMMA | wavefront of 64, wave issues MFMA |
| Register file | 256 KiB per SM | about 512 KiB vector register capacity per CU, including accumulation registers |
| Scratchpad | 256 KiB combined L1/shared, up to 227 KiB per block | 64 KiB LDS per CU |
| Matrix operation | warpgroup `wgmma`, legacy `mma.sync` | wavefront `v_mfma_*` |
| Bulk async memory | TMA / `cp.async`, clusters / DSMEM | software pipelining, `buffer_load ... lds`; no direct Hopper TMA/DSMIM counterpart |
| L2/cache | 50 MB L2 | 4 MB/XCD L2 and 256 MB memory-side Infinity Cache |
| HBM | 80 GB, 3.35 TB/s nominal peak | 128 GB, 5.3 TB/s nominal peak, shared CPU/GPU |
| FP8 | OCP E4M3/E5M2 | gfx942 FNUZ E4M3/E5M2 (not bit-compatible) |
| Multi GPU | NVLink + PCIe, NCCL | Infinity Fabric + PCIe, RCCL |

## Example density thresholds (ideal, not achieved)
| Type | H100 SXM5 ridge (FLOP/B) | MI300A ridge (FLOP/B) |
|---|---:|---:|
| FP64 matrix | 20.0 | 23.1 |
| TF32 matrix | 147.7 | 92.5 |
| BF16/FP16 matrix | 295.3 | 185.0 |
| FP8 matrix | 590.7 | 370.0 |

H100's higher BF16 ridge reflects more peak FLOP per unit HBM bandwidth; MI300A's lower ridge does not itself imply a faster GEMM. For FP64 matrix workloads, MI300A offers 122.6 vs H100's 67 TFLOP/s nominal and higher HBM bandwidth, but residency and software may dominate.

## CUDA → HIP port review
- Audit warp size 32 assumptions, shuffle widths and 64-bit ballot masks; never assume transitive portability of PTX SIMD idioms.
- Redesign tiles and producer/consumer pipelines instead of halving `num_stages`: 227 KiB H100 block scratchpad vs 64 KiB LDS; MI300A has much more register storage per CU.
- Replace TMA/WGMMA/cluster tricks with MFMA/VGPR/LDS scheduling; do not claim feature parity.
- Convert OCP FP8 to FNUZ numerically with correct scales; reject raw reinterpretation.
- On MI300A, test CPU/GPU shared allocations and XNACK explicitly; don't assume that removing `hipMemcpy` is faster without a page-placement and cache-coherence experiment.
- For XCD-locality swizzle, measure actual XCD scheduling and cache benefits. A theoretical one-workgroup round robin is not a contractual physical-placement API.
- Verify barrier and atomic scopes for inter-workgroup and cross-XCD algorithms against the active HIP memory model.
- Reprofile at every stage; previous bottleneck classifications do not carry across architectures.

## Shared verification commands
`prof-tools inspect --kind hardware --sku h100-sxm5 --dtype bf16 --gemm 1024 1024 1024`
`prof-tools inspect --kind hardware --sku mi300a --dtype bf16 --tiles 229`

These calculations only provide hypotheses. Use `prof-tools inspect --kind environment`, then the vendor profiler, then an unprofiled benchmark.
