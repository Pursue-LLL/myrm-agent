import { describe, expect, it } from 'vitest';
import { FactCheckService } from '../factCheckService';
import { VerifiedFactItem } from '../factCheckTypes';

describe('FactCheckService', () => {
  it('parses placeholders in Chinese bracket format and template format', () => {
    const text = `
      报告显示，模型平均处理耗时为 [待替换占位: 3分42秒]，
      准确率提升达 {{placeholder: 14.8%}}，
      首批上线测试用例数为 [待替换占位：1,250条]。
    `;

    const placeholders = FactCheckService.parsePlaceholders(text);
    expect(placeholders).toHaveLength(3);

    expect(placeholders[0].placeholderKey).toBe('3分42秒');
    expect(placeholders[0].status).toBe('pending');
    expect(placeholders[0].contextSnippet).toContain('平均处理耗时为');

    expect(placeholders[1].placeholderKey).toBe('14.8%');
    expect(placeholders[2].placeholderKey).toBe('1,250条');
  });

  it('replaces a single placeholder and updates placeholder status', () => {
    const text = '跑测时间共计 [待替换占位: 3分42秒]，测试通过。';
    const placeholders = FactCheckService.parsePlaceholders(text);
    expect(placeholders).toHaveLength(1);

    const { updatedContent, updatedPlaceholders } =
      FactCheckService.replacePlaceholder(
        text,
        placeholders[0].id,
        '2分15秒',
        placeholders
      );

    expect(updatedContent).toBe('跑测时间共计 2分15秒，测试通过。');
    expect(updatedPlaceholders[0].status).toBe('replaced');
    expect(updatedPlaceholders[0].replacedValue).toBe('2分15秒');
  });

  it('replaces all placeholders in bulk', () => {
    const text = '耗时 [待替换占位: 10秒]，得分 {{placeholder: 80分}}。';
    const placeholders = FactCheckService.parsePlaceholders(text);
    expect(placeholders).toHaveLength(2);

    const replacements = {
      [placeholders[0].id]: '8.2秒',
      [placeholders[1].id]: '94.5分',
    };

    const { updatedContent, updatedPlaceholders } =
      FactCheckService.replaceAllPlaceholders(text, replacements, placeholders);

    expect(updatedContent).toBe('耗时 8.2秒，得分 94.5分。');
    expect(updatedPlaceholders[0].status).toBe('replaced');
    expect(updatedPlaceholders[1].status).toBe('replaced');
  });

  it('builds comprehensive audit report with verified facts', () => {
    const text = '指标 [待替换占位: 待测]，定价稳定。';
    const verifiedFacts: VerifiedFactItem[] = [
      {
        id: 'vf-1',
        factStatement: 'API 官方调用单价为 0.14 美元/百万 Token',
        verifiedValue: '$0.14 / 1M',
        sourceName: '官方定价文档',
        sourceUrl: 'https://example.com/pricing',
        verifiedAt: '2026-09-02',
      },
    ];

    const report = FactCheckService.auditContent(text, verifiedFacts);
    expect(report.totalPlaceholders).toBe(1);
    expect(report.pendingCount).toBe(1);
    expect(report.hasFabrications).toBe(true);
    expect(report.verifiedFacts).toHaveLength(1);
  });
});
