import { describe, it, expect } from 'vitest';
import {
  calculateHexLightness,
  compareWithPrebakedBaseline,
  evaluateLayerDirection,
  evaluateThemeInvariantSuite,
  parseHexToRgb,
} from '../themeLayerInvariantEngine';
import { PrebakedThemeBaseline } from '../themeLayerInvariantTypes';

describe('themeLayerInvariantEngine', () => {
  it('正确解析 3 位与 6 位十六进制颜色为 RGB 三元组', () => {
    expect(parseHexToRgb('#fff')).toEqual([255, 255, 255]);
    expect(parseHexToRgb('#000000')).toEqual([0, 0, 0]);
    expect(parseHexToRgb('#6366f1')).toEqual([99, 102, 241]);
    expect(parseHexToRgb('invalid')).toEqual([0, 0, 0]);
  });

  it('根据标准相对亮度公式准确计算明度百分比', () => {
    expect(calculateHexLightness('#ffffff')).toBe(100);
    expect(calculateHexLightness('#000000')).toBe(0);
    const grayLightness = calculateHexLightness('#e7e7e8');
    expect(grayLightness).toBeGreaterThan(80);
    expect(grayLightness).toBeLessThan(100);
  });

  it('浅色模式下：卡面明度低于画布底色时判定违规并给出凹陷发灰警告', () => {
    // 错误版本：画布纯白 (100)，卡面调暗为 #e7e7e8 (约 90.7)
    const buggyEvaluation = evaluateLayerDirection(
      'light',
      '#ffffff',
      '#e7e7e8'
    );
    expect(buggyEvaluation.isInvariantSatisfied).toBe(false);
    expect(buggyEvaluation.violationReason).toContain('凹陷/禁用感');

    // 正确版本：卡面纯白 (100)，画布纯白 (100)
    const cleanEvaluation = evaluateLayerDirection(
      'light',
      '#ffffff',
      '#ffffff'
    );
    expect(cleanEvaluation.isInvariantSatisfied).toBe(true);
    expect(cleanEvaluation.violationReason).toBeUndefined();
  });

  it('深色模式下：卡面明度必须高于画布底色才能形成有效视觉抬升', () => {
    // 正确深色：底色 #09090b，卡面 #18181b
    const correctDark = evaluateLayerDirection(
      'dark',
      '#09090b',
      '#18181b'
    );
    expect(correctDark.isInvariantSatisfied).toBe(true);
    expect(correctDark.deltaLightness).toBeGreaterThan(0);

    // 错误深色：卡面比底色更暗
    const buggyDark = evaluateLayerDirection(
      'dark',
      '#18181b',
      '#09090b'
    );
    expect(buggyDark.isInvariantSatisfied).toBe(false);
    expect(buggyDark.violationReason).toContain('深色阴影失效');
  });

  it('双主题同帧套件评估：只有浅色与深色均满足不变量时才判定 allPassed 为 true', () => {
    const perfectReport = evaluateThemeInvariantSuite(
      '#ffffff',
      '#ffffff',
      '#09090b',
      '#18181b'
    );
    expect(perfectReport.allPassed).toBe(true);

    const flawedReport = evaluateThemeInvariantSuite(
      '#ffffff',
      '#e7e7e8', // 浅色违规
      '#09090b',
      '#18181b'
    );
    expect(flawedReport.allPassed).toBe(false);
  });

  it('与旧版预烘基线比对能够精准侦测出层级方向反转回归', () => {
    const flawedReport = evaluateThemeInvariantSuite(
      '#ffffff',
      '#e7e7e8',
      '#09090b',
      '#18181b'
    );

    const cleanBaseline: PrebakedThemeBaseline = {
      baselineVersion: 'v0.9.0-clean',
      capturedAt: Date.now(),
      lightMode: {
        canvasHex: '#ffffff',
        cardHex: '#ffffff',
        isCorrect: true,
      },
      darkMode: {
        canvasHex: '#09090b',
        cardHex: '#18181b',
        isCorrect: true,
      },
    };

    const comparison = compareWithPrebakedBaseline(flawedReport, cleanBaseline);
    expect(comparison.hasRegression).toBe(true);
    expect(comparison.details[0]).toContain('浅色主题发生反直觉回归');
  });
});
