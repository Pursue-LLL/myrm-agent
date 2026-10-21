import { describe, it, expect } from 'vitest';
import {
  SPRING_CURVES,
  MOTION_PERSONALITIES,
  MOTION_STACK_LANES,
  SPATIAL_GRID_SPACINGS,
  validateGpuMotionSafety,
} from '../springPhysicsTokens';

describe('springPhysicsTokens', () => {
  it('defines natural damped spring curves SSOT with valid cubic-bezier', () => {
    expect(SPRING_CURVES.enter).toBeDefined();
    expect(SPRING_CURVES.exit).toBeDefined();
    expect(SPRING_CURVES.spring).toBeDefined();
    expect(SPRING_CURVES.smooth).toBeDefined();

    expect(SPRING_CURVES.enter?.bezier).toContain('cubic-bezier');
    expect(SPRING_CURVES.spring?.dampingRatio).toBeLessThan(1.0); // 弹性过冲
  });

  it('defines 4 brand motion personality archetypes', () => {
    const keys = Object.keys(MOTION_PERSONALITIES);
    expect(keys).toContain('playful');
    expect(keys).toContain('premium');
    expect(keys).toContain('corporate');
    expect(keys).toContain('energetic');

    expect(MOTION_PERSONALITIES.premium.overshootPercent).toBe(0);
    expect(MOTION_PERSONALITIES.playful.overshootPercent).toBeGreaterThan(10);
  });

  it('provides 5-lane motion stack matrix with guardrails', () => {
    const lanes = Object.keys(MOTION_STACK_LANES);
    expect(lanes).toContain('css_spring');
    expect(lanes).toContain('motion_dev');
    expect(lanes).toContain('gsap');
    expect(lanes).toContain('rive');
    expect(lanes).toContain('lottie');

    // 验证 Rive Trap 28 铁律护栏
    expect(
      MOTION_STACK_LANES.rive.guardrails.some((g) => g.includes('Trap 28') || g.includes('只读'))
    ).toBe(true);
  });

  it('validates spatial grid spacings conforming to 4px/8px scale', () => {
    const pixels = SPATIAL_GRID_SPACINGS.map((s) => s.px);
    expect(pixels).toContain(4);
    expect(pixels).toContain(8);
    expect(pixels).toContain(16);
    expect(pixels).toContain(24);
    expect(pixels).toContain(32);
  });

  it('validates GPU motion safety correctly identifying layout thrashing properties', () => {
    const safeProps = validateGpuMotionSafety(['transform', 'opacity', 'filter']);
    expect(safeProps.isSafe).toBe(true);
    expect(safeProps.violations.length).toBe(0);

    const unsafeProps = validateGpuMotionSafety(['width', 'top', 'transform']);
    expect(unsafeProps.isSafe).toBe(false);
    expect(unsafeProps.violations.length).toBe(2);
  });
});
