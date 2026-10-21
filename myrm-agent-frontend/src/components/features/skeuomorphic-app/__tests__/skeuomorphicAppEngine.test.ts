import { describe, it, expect } from 'vitest';
import {
  calculateWheelAngle,
  calculateAngularStepDelta,
  wrapArtifactIndex,
  formatTaskDuration,
  formatTokenUsage,
  getDefaultMockArtifacts,
} from '../skeuomorphicAppEngine';

describe('skeuomorphicAppEngine', () => {
  it('calculateWheelAngle 应正确计算四个象限及中心点的平面极角', () => {
    const cx = 100;
    const cy = 100;

    // 正上方 (0, -50) -> 0°
    expect(calculateWheelAngle(100, 50, cx, cy)).toBeCloseTo(0, 1);

    // 正右方 (50, 0) -> 90°
    expect(calculateWheelAngle(150, 100, cx, cy)).toBeCloseTo(90, 1);

    // 正下方 (0, 50) -> 180°
    expect(calculateWheelAngle(100, 150, cx, cy)).toBeCloseTo(180, 1);

    // 正左方 (-50, 0) -> 270°
    expect(calculateWheelAngle(50, 100, cx, cy)).toBeCloseTo(270, 1);
  });

  it('calculateAngularStepDelta 应计算转盘步进并在跨越 0°/360° 时平滑处理', () => {
    // 顺时针转动 45 度 (阈值 20 度 -> 2 步，剩余 5 度)
    const cwRes = calculateAngularStepDelta(45, 0, 20);
    expect(cwRes.stepDelta).toBe(2);
    expect(cwRes.remainingAngle).toBe(5);

    // 逆时针转动 45 度 -> -2 步
    const ccwRes = calculateAngularStepDelta(0, 45, 20);
    expect(ccwRes.stepDelta).toBe(-2);
    expect(ccwRes.remainingAngle).toBe(-5);

    // 跨越 360° 到 10° (实际转动 +20°)
    const wrapRes = calculateAngularStepDelta(10, 350, 20);
    expect(wrapRes.stepDelta).toBe(1);
    expect(wrapRes.remainingAngle).toBe(0);

    // 未达阈值的微小晃动 -> 0 步
    const microRes = calculateAngularStepDelta(15, 0, 20);
    expect(microRes.stepDelta).toBe(0);
    expect(microRes.remainingAngle).toBe(15);
  });

  it('wrapArtifactIndex 应正确循环回绕正负索引', () => {
    const total = 4;
    expect(wrapArtifactIndex(0, total)).toBe(0);
    expect(wrapArtifactIndex(3, total)).toBe(3);
    expect(wrapArtifactIndex(4, total)).toBe(0);
    expect(wrapArtifactIndex(5, total)).toBe(1);
    expect(wrapArtifactIndex(-1, total)).toBe(3);
    expect(wrapArtifactIndex(-5, total)).toBe(3);
    expect(wrapArtifactIndex(2, 0)).toBe(0);
  });

  it('formatTaskDuration 应按毫秒/秒/分秒格式化', () => {
    expect(formatTaskDuration(450)).toBe('450ms');
    expect(formatTaskDuration(5000)).toBe('5s');
    expect(formatTaskDuration(65000)).toBe('1m 5s');
  });

  it('formatTokenUsage 应正确格式化单次 Token 与千级别 Token', () => {
    expect(formatTokenUsage(800)).toBe('800 T');
    expect(formatTokenUsage(3500)).toBe('3.5k T');
  });

  it('getDefaultMockArtifacts 应提供结构完整的工件初始数据集', () => {
    const artifacts = getDefaultMockArtifacts();
    expect(artifacts.length).toBeGreaterThanOrEqual(4);
    expect(artifacts[0]).toHaveProperty('id');
    expect(artifacts[0]).toHaveProperty('taskTitle');
    expect(artifacts[0]).toHaveProperty('artifactType');
  });
});
