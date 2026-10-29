"""Pure-function tests for the hardware calculator: KV-cache VRAM, hardware rung and tokens/s estimate.

[POS]
tests/api/integrations/hardware/test_calculator.py

[INPUT]
- app.api.integrations.hardware.calculator: calculate_kv_cache_vram_gb, derive_hardware_rung, estimate_tok_per_sec

[OUTPUT]
- Pins the numeric contract the cookbook recommendations are built on, including the guards for zero, negative and unknown inputs
"""

from app.api.integrations.hardware.calculator import (
    calculate_kv_cache_vram_gb,
    derive_hardware_rung,
)
from app.api.integrations.hardware.calculator import (
    estimate_tok_per_sec as _estimate_tok_per_sec,
)

# --- calculate_kv_cache_vram_gb / derive_hardware_rung ---


def test_calculate_kv_cache_vram_gb():
    # 32 layers, 8 kv_heads, 128 head_dim, 65536 ctx, fp16 (2.0 B)
    # 2 * 32 * 8 * 128 * 65536 * 2.0 = 8,589,934,592 Bytes = 8.00 GB
    val_fp16 = calculate_kv_cache_vram_gb(32, 8, 128, 65536, 2.0)
    assert val_fp16 == 8.0

    # Q8 (1.0 B) -> 4.00 GB
    val_q8 = calculate_kv_cache_vram_gb(32, 8, 128, 65536, 1.0)
    assert val_q8 == 4.0

    # Q4 (0.5 B) -> 2.00 GB
    val_q4 = calculate_kv_cache_vram_gb(32, 8, 128, 65536, 0.5)
    assert val_q4 == 2.0

    # Edge cases
    assert calculate_kv_cache_vram_gb(0, 8, 128) == 0.0
    assert calculate_kv_cache_vram_gb(32, 0, 128) == 0.0
    assert calculate_kv_cache_vram_gb(32, 8, 0) == 0.0
    assert calculate_kv_cache_vram_gb(32, 8, 128, context_length=-10) == 0.0


def test_derive_hardware_rung():
    assert derive_hardware_rung(8.0)[0] == 1
    assert derive_hardware_rung(9.9)[0] == 1
    assert derive_hardware_rung(10.0)[0] == 2
    assert derive_hardware_rung(16.0)[0] == 2
    assert derive_hardware_rung(19.9)[0] == 2
    assert derive_hardware_rung(20.0)[0] == 3
    assert derive_hardware_rung(24.0)[0] == 3
    assert derive_hardware_rung(39.9)[0] == 3
    assert derive_hardware_rung(40.0)[0] == 4
    assert derive_hardware_rung(64.0)[0] == 4
    assert derive_hardware_rung(79.9)[0] == 4
    assert derive_hardware_rung(80.0)[0] == 5
    assert derive_hardware_rung(128.0)[0] == 5


# --- _estimate_tok_per_sec ---


def test_estimate_tok_per_sec_apple_m2_pro_8b():
    # M2 Pro: 200 GBps, Q4_K_M 8B, apple vendor_factor=0.82, efficiency=0.55
    # raw = 200e9 / (8e9 * 0.5625) = 44.44
    # tok/s = 44.44 * 0.55 * 0.82 = 20.04 -> round = 20
    result = _estimate_tok_per_sec(200.0, 8.0, "apple")
    assert result == 20


def test_estimate_tok_per_sec_rtx4090_8b():
    # RTX 4090: 1008 GBps, nvidia vendor_factor=1.0
    # raw = 1008e9 / (8e9 * 0.5625) = 224
    # tok/s = 224 * 0.55 * 1.0 = 123.2 -> round = 123
    result = _estimate_tok_per_sec(1008.0, 8.0, "nvidia")
    assert result == 123


def test_estimate_tok_per_sec_m1_8b():
    # M1: 68.25 GBps, apple vendor_factor=0.82
    # raw = 68.25e9 / (8e9 * 0.5625) = 15.166
    # tok/s = 15.166 * 0.55 * 0.82 = 6.84 -> round = 7 (above min 1)
    result = _estimate_tok_per_sec(68.25, 8.0, "apple")
    assert result == 7


def test_estimate_tok_per_sec_none_bandwidth():
    result = _estimate_tok_per_sec(None, 8.0, "nvidia")
    assert result is None


def test_estimate_tok_per_sec_zero_params():
    result = _estimate_tok_per_sec(200.0, 0.0, "apple")
    assert result is None


def test_estimate_tok_per_sec_zero_bandwidth():
    result = _estimate_tok_per_sec(0.0, 8.0, "nvidia")
    assert result is None


def test_estimate_tok_per_sec_unknown_vendor():
    # Unknown vendor_factor=0.60
    result = _estimate_tok_per_sec(200.0, 8.0, "unknown")
    assert result is not None
    assert result >= 1


def test_estimate_tok_per_sec_minimum_is_1():
    # Very small bandwidth + very large model -> should floor to 1
    result = _estimate_tok_per_sec(0.001, 70.0, "apple")
    assert result == 1


def test_estimate_tok_per_sec_moe_active_params():
    """MoE models (e.g. DeepSeek R1 32B) use active_params_b for TPS, not total params_b.

    DeepSeek R1 32B is a MoE model with ~7B active weights per token on RTX 4090
    (1008 GBps, nvidia vendor_factor=1.0).

    Using params_b=32 (wrong):
        raw = 1008e9 / (32e9 * 0.5625) = 56.0
        tok/s = 56 * 0.55 * 1.0 = 30.8 -> 31  (red badge, misleads user)

    Using active_params_b=7 (correct):
        raw = 1008e9 / (7e9 * 0.5625) = 256.0
        tok/s = 256 * 0.55 * 1.0 = 140.8 -> 141  (green badge, accurate)
    """
    wrong_tps = _estimate_tok_per_sec(1008.0, 32.0, "nvidia")
    assert wrong_tps == 31

    correct_tps = _estimate_tok_per_sec(1008.0, 32.0, "nvidia", active_params_b=7.0)
    assert correct_tps == 141

    # active_params_b result must be significantly higher than total-params result
    assert correct_tps > wrong_tps * 3  # type: ignore[operator]


def test_estimate_tok_per_sec_active_params_ignored_when_zero_or_none():
    """active_params_b=0 or None should fall back to params_b."""
    result_none = _estimate_tok_per_sec(200.0, 8.0, "apple", active_params_b=None)
    result_zero = _estimate_tok_per_sec(200.0, 8.0, "apple", active_params_b=0.0)
    result_baseline = _estimate_tok_per_sec(200.0, 8.0, "apple")
    assert result_none == result_baseline
    assert result_zero == result_baseline


def test_estimate_tok_per_sec_negative_active_params_falls_back():
    """Negative active_params_b should fall back to params_b, not produce negative TPS."""
    result = _estimate_tok_per_sec(200.0, 8.0, "apple", active_params_b=-5.0)
    baseline = _estimate_tok_per_sec(200.0, 8.0, "apple")
    assert result == baseline


def test_estimate_tok_per_sec_negative_bandwidth_returns_none():
    assert _estimate_tok_per_sec(-100.0, 8.0, "nvidia") is None


def test_estimate_tok_per_sec_negative_params_returns_none():
    assert _estimate_tok_per_sec(200.0, -3.0, "nvidia") is None
