import { describe, it, expect } from 'vitest';
import {
  analyzeFiveElements,
  assembleRefinedPrompt,
  generateInitial3Directions,
  QUICK_OPTIONS_MAP,
} from '../fiveElementLinterEngine';

describe('fiveElementLinterEngine', () => {
  it('correctly handles empty or non-design input with 0% completeness', () => {
    const spec = analyzeFiveElements('今天天气真好');
    expect(spec.completenessScore).toBe(0);
    expect(spec.what.isDetected).toBe(false);
    expect(spec.audience.isDetected).toBe(false);
    expect(spec.style.isDetected).toBe(false);
    expect(spec.content.isDetected).toBe(false);
    expect(spec.format.isDetected).toBe(false);
  });

  it('detects partial design intent and computes correct score', () => {
    const spec = analyzeFiveElements('帮我做一张海报');
    expect(spec.what.isDetected).toBe(true);
    expect(spec.what.value).toBe('海报');
    expect(spec.audience.isDetected).toBe(false);
    // 5个要素中命中了 1 个 -> 20%
    expect(spec.completenessScore).toBe(20);
  });

  it('detects all five elements and achieves 100% completeness', () => {
    const prompt =
      '做一张咖啡店周年庆宣传海报，面向年轻白领，温暖复古风格，文案包含第二杯半价特惠，A3竖版印刷规格';
    const spec = analyzeFiveElements(prompt);

    expect(spec.what.isDetected).toBe(true);
    expect(spec.audience.isDetected).toBe(true);
    expect(spec.style.isDetected).toBe(true);
    expect(spec.content.isDetected).toBe(true);
    expect(spec.format.isDetected).toBe(true);
    expect(spec.completenessScore).toBe(100);
  });

  it('assembles a professional refined commercial prompt from spec', () => {
    const spec = analyzeFiveElements('帮我做一张海报');
    spec.audience.value = '年轻白领';
    spec.style.value = '极简科技留白';
    spec.content.value = '第二杯半价';
    spec.format.value = '手机端全屏 (9:16)';

    const refined = assembleRefinedPrompt(spec, '帮我做一张海报');
    expect(refined).toContain('请设计制作一份专业的【海报】');
    expect(refined).toContain('目标受众为年轻白领');
    expect(refined).toContain('采用极简科技留白视觉风格');
    expect(refined).toContain('核心文案包含「第二杯半价」');
    expect(refined).toContain('规格尺寸为手机端全屏 (9:16)');
  });

  it('generates 3 distinct initial directions with preview layers and unique styles', () => {
    const spec = analyzeFiveElements('做一张咖啡海报，极简科技风格');
    const directions = generateInitial3Directions(spec);

    expect(directions.length).toBe(3);
    expect(directions[0].layoutStructure).toBe('minimal');
    expect(directions[1].layoutStructure).toBe('bold-visual');
    expect(directions[2].layoutStructure).toBe('structured-card');

    for (const dir of directions) {
      expect(dir.previewLayers.length).toBeGreaterThan(0);
      expect(dir.primaryColor).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it('provides quick options map for all five element keys', () => {
    expect(QUICK_OPTIONS_MAP.what.length).toBeGreaterThan(0);
    expect(QUICK_OPTIONS_MAP.audience.length).toBeGreaterThan(0);
    expect(QUICK_OPTIONS_MAP.style.length).toBeGreaterThan(0);
    expect(QUICK_OPTIONS_MAP.content.length).toBeGreaterThan(0);
    expect(QUICK_OPTIONS_MAP.format.length).toBeGreaterThan(0);
  });
});
