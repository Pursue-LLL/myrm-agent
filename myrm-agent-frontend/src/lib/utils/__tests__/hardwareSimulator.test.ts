import { describe, expect, it } from 'vitest';
import { HARDWARE_RUNGS, calculateKvCacheVramGb, getRungByVram } from '../hardwareSimulator';

describe('hardwareSimulator utilities', () => {
  it('should define 5 hardware rungs with valid ranges and models', () => {
    expect(HARDWARE_RUNGS).toHaveLength(5);
    expect(HARDWARE_RUNGS[0].rung).toBe(1);
    expect(HARDWARE_RUNGS[4].rung).toBe(5);
  });

  it('should correctly calculate 64k KV cache VRAM footprint', () => {
    // 32 layers, 8 kv_heads, 128 head_dim, 65536 ctx, fp16 (2.0 B)
    // 2 * 32 * 8 * 128 * 65536 * 2.0 / (1024^3) = 8.00 GB
    const fp16Gb = calculateKvCacheVramGb(32, 8, 128, 65536, 2.0);
    expect(fp16Gb).toBe(8.0);

    // Q8 (1.0 B) -> 4.00 GB
    const q8Gb = calculateKvCacheVramGb(32, 8, 128, 65536, 1.0);
    expect(q8Gb).toBe(4.0);

    // Q4 (0.5 B) -> 2.00 GB
    const q4Gb = calculateKvCacheVramGb(32, 8, 128, 65536, 0.5);
    expect(q4Gb).toBe(2.0);

    // Edge cases
    expect(calculateKvCacheVramGb(0, 8, 128)).toBe(0);
    expect(calculateKvCacheVramGb(32, 0, 128)).toBe(0);
    expect(calculateKvCacheVramGb(32, 8, 0)).toBe(0);
    expect(calculateKvCacheVramGb(32, 8, 128, -100)).toBe(0);
  });

  it('should map available VRAM to the appropriate Reference Ladder rung', () => {
    expect(getRungByVram(6).rung).toBe(1);
    expect(getRungByVram(9.9).rung).toBe(1);
    expect(getRungByVram(10.0).rung).toBe(2);
    expect(getRungByVram(16).rung).toBe(2);
    expect(getRungByVram(19.9).rung).toBe(2);
    expect(getRungByVram(20.0).rung).toBe(3);
    expect(getRungByVram(24).rung).toBe(3);
    expect(getRungByVram(39.9).rung).toBe(3);
    expect(getRungByVram(40.0).rung).toBe(4);
    expect(getRungByVram(64).rung).toBe(4);
    expect(getRungByVram(79.9).rung).toBe(4);
    expect(getRungByVram(80.0).rung).toBe(5);
    expect(getRungByVram(128).rung).toBe(5);
  });
});
