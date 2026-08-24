"""
[INPUT]
- hardware.py (POS: 硬件推荐纯计算逻辑分离)

[OUTPUT]
- _estimate_tok_per_sec
- calculate_kv_cache_vram_gb
- derive_hardware_rung

[POS]
硬件指标与 KV Cache 显存测算纯函数工具模块。
"""

from __future__ import annotations

# Bytes per weight for Q4_K_M quantization (dominant Ollama default format).
_Q4_K_M_BYTES_PER_WEIGHT: float = 0.5625

# Empirical efficiency: real-world throughput vs. theoretical peak bandwidth.
_EFFICIENCY: float = 0.55

# Vendor-specific calibration from community benchmark data.
_VENDOR_FACTOR: dict[str, float] = {
    "apple": 0.82,
    "nvidia": 1.00,
    "amd": 0.78,
    "intel": 0.65,
    "unknown": 0.60,
}

# Numeric priority for each fit level used in multi-key recommendation sort.
_FIT_PRIORITY: dict[str, int] = {"perfect": 3, "good": 2, "fair": 1, "poor": 0}


def estimate_tok_per_sec(
    bandwidth_gbps: float | None,
    params_b: float,
    vendor: str,
    active_params_b: float | None = None,
) -> int | None:
    """Estimate inference throughput (tokens/s) for a Q4_K_M quantized LLM."""
    if bandwidth_gbps is None or bandwidth_gbps <= 0 or params_b <= 0:
        return None
    effective_b = (
        active_params_b if (active_params_b and active_params_b > 0) else params_b
    )
    raw = (bandwidth_gbps * 1e9) / (effective_b * 1e9 * _Q4_K_M_BYTES_PER_WEIGHT)
    vendor_factor = _VENDOR_FACTOR.get(vendor, _VENDOR_FACTOR["unknown"])
    return max(1, round(raw * _EFFICIENCY * vendor_factor))


def calculate_kv_cache_vram_gb(
    num_layers: int,
    kv_heads: int,
    head_dim: int,
    context_length: int = 65536,
    bytes_per_elem: float = 2.0,
) -> float:
    """Calculate VRAM consumed by KV Cache for a given context length in GB."""
    if num_layers <= 0 or kv_heads <= 0 or head_dim <= 0 or context_length <= 0:
        return 0.0
    raw_bytes = 2 * num_layers * kv_heads * head_dim * context_length * bytes_per_elem
    return round(raw_bytes / (1024**3), 2)


def derive_hardware_rung(available_vram_gb: float) -> tuple[int, str]:
    """Map available VRAM to a Reference Ladder Rung (1 to 5)."""
    if available_vram_gb < 10.0:
        return 1, "Entry (< 10GB)"
    if available_vram_gb < 20.0:
        return 2, "Mainstream (10-20GB)"
    if available_vram_gb < 40.0:
        return 3, "High-end (20-40GB)"
    if available_vram_gb < 80.0:
        return 4, "Workstation (40-80GB)"
    return 5, "Flagship (80GB+)"
