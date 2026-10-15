import { describe, it, expect } from 'vitest';
import {
  applyRefinementInstruction,
  synthesizeWeeklyDigest,
} from '../weeklyDigestSynthesizerEngine';
import { INITIAL_CHANNEL_FOOTPRINTS } from '../footprintAggregatorData';
import { ChannelFootprintItem } from '../weeklyDigestTypes';

describe('weeklyDigestSynthesizerEngine pure functions', () => {
  it('synthesizes executive format weekly digest by default', () => {
    const digest = synthesizeWeeklyDigest(INITIAL_CHANNEL_FOOTPRINTS, {
      weekIdentifier: '2026-W36',
      stylePreset: 'executive',
    });

    expect(digest.weekIdentifier).toBe('2026-W36');
    expect(digest.stylePreset).toBe('executive');
    expect(digest.accomplishments.length).toBeGreaterThan(0);
    expect(digest.keyDecisions.length).toBeGreaterThan(0);
    expect(digest.codeLearnings.length).toBeGreaterThan(0);
    expect(digest.pendingRisks.length).toBeGreaterThan(0);
    expect(digest.nextSteps.length).toBeGreaterThan(0);

    expect(digest.markdownContent).toContain('高管审阅版');
    expect(digest.markdownContent).toContain('本周核心业务与产品成果');
    expect(digest.markdownContent).toContain('重大技术与方案决策');
  });

  it('synthesizes technical format weekly digest correctly', () => {
    const digest = synthesizeWeeklyDigest(INITIAL_CHANNEL_FOOTPRINTS, {
      weekIdentifier: '2026-W36',
      stylePreset: 'technical',
    });

    expect(digest.stylePreset).toBe('technical');
    expect(digest.markdownContent).toContain('研发工作周报与技术复盘');
    expect(digest.markdownContent).toContain('核心功能交付与代码评审');
    expect(digest.markdownContent).toContain('架构设计与 RFC 关键决策');
  });

  it('synthesizes bullet format weekly digest concisely', () => {
    const digest = synthesizeWeeklyDigest(INITIAL_CHANNEL_FOOTPRINTS, {
      weekIdentifier: '2026-W36',
      stylePreset: 'bullet',
    });

    expect(digest.stylePreset).toBe('bullet');
    expect(digest.markdownContent).toContain('# 工作简报 · 2026-W36');
    expect(digest.markdownContent).toContain('## 核心产出');
    expect(digest.markdownContent).toContain('## 决策与思考');
    expect(digest.markdownContent).toContain('## 风险与下一步');
  });

  it('excludes footprints that have includedInDigest set to false', () => {
    const items: ChannelFootprintItem[] = INITIAL_CHANNEL_FOOTPRINTS.map(
      (item, idx) => ({
        ...item,
        includedInDigest: idx === 0, // only the first item
      })
    );

    const digest = synthesizeWeeklyDigest(items);
    expect(digest.accomplishments.length).toBe(1);
    expect(digest.keyDecisions.length).toBe(0);
  });

  it('applies natural language refinement instructions accurately', () => {
    const baseDigest = synthesizeWeeklyDigest(INITIAL_CHANNEL_FOOTPRINTS, {
      stylePreset: 'executive',
    });

    // Refine to bullet style
    const refinedToBullet = applyRefinementInstruction(
      baseDigest,
      '把内容改成极简速览格式'
    );
    expect(refinedToBullet.stylePreset).toBe('bullet');
    expect(refinedToBullet.markdownContent).toContain('工作简报');
    expect(refinedToBullet.markdownContent).toContain('微调指令: 把内容改成极简速览格式');

    // Refine to technical style
    const refinedToTech = applyRefinementInstruction(
      refinedToBullet,
      '展开技术细节和架构决策'
    );
    expect(refinedToTech.stylePreset).toBe('technical');
    expect(refinedToTech.markdownContent).toContain('研发工作周报与技术复盘');

    // Refine to executive style
    const refinedToExec = applyRefinementInstruction(
      refinedToTech,
      '突出高管层业务收益'
    );
    expect(refinedToExec.stylePreset).toBe('executive');
    expect(refinedToExec.markdownContent).toContain('高管审阅版');
  });
});
