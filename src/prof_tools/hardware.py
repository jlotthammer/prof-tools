"""Reference peaks for *exact* SKUs, not measured throughput."""

DEVICES = {
    "h100-sxm5": {"vendor": "nvidia", "architecture": "sm_90a", "units": 132,
                 "hbm_tbps": 3.35, "hbm_gb": 80,
                 "dense_tflops": {"fp64_tensor": 67.0, "tf32": 494.5, "bf16": 989.5, "fp16": 989.5, "fp8": 1979.0}},
    "mi300a": {"vendor": "amd", "architecture": "gfx942", "units": 228,
               "hbm_tbps": 5.3, "hbm_gb": 128,
               "dense_tflops": {"fp64_tensor": 122.6, "tf32": 490.3, "bf16": 980.6, "fp16": 980.6, "fp8": 1961.2}},
}


def ridge(device, dtype):
    facts = DEVICES[device]
    return facts["dense_tflops"][dtype] / facts["hbm_tbps"]


def gemm_ai(m, n, k, element_bytes=2, output_bytes=None):
    """Idealized min-traffic GEMM, counts reading A/B once + writing C once."""
    if min(m, n, k, element_bytes) <= 0:
        raise ValueError("dimensions and bytes must be positive")
    output_bytes = output_bytes if output_bytes is not None else element_bytes
    return (2 * m * n * k) / (element_bytes * (m*k + k*n) + output_bytes * m*n)


def wave_efficiency(tiles, units):
    if tiles <= 0 or units <= 0:
        raise ValueError("tiles and units must be positive")
    from math import ceil
    waves = ceil(tiles / units)
    return {"waves": waves, "last_wave_fill": ((tiles - 1) % units + 1) / units,
            "overall_fill": tiles / (waves * units)}
