import { describe, it, expect } from 'vitest';
import {
  applyTextMutationToHtml,
  buildElementSelector,
  buildZeroTokenCommitReport,
  mapFontSizeToCss,
  mergeStyleObjectToCssString,
} from '../wysiwygEditorEngine';
import { MutationDiffSummary } from '../wysiwygEditorTypes';

describe('wysiwygEditorEngine', () => {
  it('正确映射字体大小阶梯为 CSS 规则', () => {
    expect(mapFontSizeToCss('sm')).toBe('12px');
    expect(mapFontSizeToCss('base')).toBe('14px');
    expect(mapFontSizeToCss('lg')).toBe('18px');
    expect(mapFontSizeToCss('xl')).toBe('24px');
  });

  it('优先使用 id 生成选择器，其次使用非 wysiwyg 类名，最后回退为标签名', () => {
    expect(
      buildElementSelector({ tagName: 'DIV', id: 'main-header' })
    ).toBe('#main-header');

    expect(
      buildElementSelector({
        tagName: 'H2',
        className: 'wysiwyg-active title-node hero',
      })
    ).toBe('h2.title-node');

    expect(
      buildElementSelector({ tagName: 'SECTION' })
    ).toBe('section');
  });

  it('准确在 HTML 源码中执行文本精准微调替换', () => {
    const rawHtml =
      '<div class="box"><h1>原始标题文本</h1><p>正文内容</p></div>';
    const replaced = applyTextMutationToHtml(
      rawHtml,
      '原始标题文本',
      '全新所见即所得修改标题'
    );

    expect(replaced).toContain('全新所见即所得修改标题');
    expect(replaced).not.toContain('原始标题文本');
    expect(replaced).toContain('<p>正文内容</p>');
  });

  it('在旧文本为空或相同文本时直接保持原有 HTML 不变', () => {
    const rawHtml = '<p>内容</p>';
    expect(applyTextMutationToHtml(rawHtml, '', '新')).toBe(rawHtml);
    expect(applyTextMutationToHtml(rawHtml, '内容', '内容')).toBe(rawHtml);
  });

  it('正确合并样式补丁为紧凑标准的 CSS 字符串', () => {
    const initialStyle = 'color: #fff; font-size: 14px';
    const merged = mergeStyleObjectToCssString(initialStyle, {
      color: '#6366f1',
      backgroundColor: '#18181b',
      borderRadius: '8px',
    });

    expect(merged).toContain('color: #6366f1');
    expect(merged).toContain('background-color: #18181b');
    expect(merged).toContain('border-radius: 8px');
    expect(merged).toContain('font-size: 14px');
  });

  it('构建零 Token 保存报告，包含估算节省 Token、低耗时与上下文对账提示', () => {
    const mutations: MutationDiffSummary[] = [
      {
        id: 'm1',
        timestamp: Date.now(),
        selector: 'h2.title',
        changeType: 'text',
        originalValue: '旧标题',
        newValue: '新标题',
      },
    ];

    const report = buildZeroTokenCommitReport(mutations, 2, 7000);

    expect(report.version).toBe(2);
    expect(report.mutationCount).toBe(1);
    expect(report.latencyMs).toBeLessThan(50);
    expect(report.tokenSavedCount).toBeGreaterThanOrEqual(1200);
    expect(report.contextIngressPrompt).toContain('h2.title');
    expect(report.contextIngressPrompt).toContain('新标题');
    expect(report.contextIngressPrompt).toContain('0 Token');
  });
});
