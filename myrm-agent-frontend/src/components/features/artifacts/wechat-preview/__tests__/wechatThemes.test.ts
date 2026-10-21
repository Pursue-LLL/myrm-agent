import { describe, it, expect } from 'vitest';
import {
  WECHAT_THEMES,
  getWechatTheme,
  compileWechatInlineHtml,
} from '../wechatThemes';
import type { WechatThemeId } from '../wechatPreviewTypes';

describe('wechatThemes & compileWechatInlineHtml', () => {
  it('provides all 4 core WeChat themes with valid block styles', () => {
    const themeIds: WechatThemeId[] = ['classic', 'tech', 'enterprise', 'humanist'];
    for (const id of themeIds) {
      const theme = WECHAT_THEMES[id];
      expect(theme).toBeDefined();
      expect(theme.id).toBe(id);
      expect(theme.primaryColor).toBeTruthy();
      expect(theme.fontFamily).toBeTruthy();
      expect(theme.styles.h1).toContain('font-size:');
      expect(theme.styles.p).toContain('line-height:');
    }
  });

  it('falls back to classic theme when unknown theme id is requested', () => {
    const fallbackTheme = getWechatTheme('unknown_theme' as WechatThemeId);
    expect(fallbackTheme.id).toBe('classic');
  });

  it('handles empty or blank content gracefully', () => {
    const emptyResult = compileWechatInlineHtml('');
    expect(emptyResult).toContain('暂无排版内容');

    const whitespaceResult = compileWechatInlineHtml('   ');
    expect(whitespaceResult).toContain('暂无排版内容');
  });

  it('compiles Markdown headings and injects inline styles', () => {
    const markdown = '# 大标题\n## 二级标题\n### 三级标题';
    const compiled = compileWechatInlineHtml(markdown, 'tech');

    expect(compiled).toContain('<h1 style="');
    expect(compiled).toContain('<h2 style="');
    expect(compiled).toContain('<h3 style="');
    expect(compiled).toContain('大标题</h1>');
    expect(compiled).toContain('二级标题</h2>');
    expect(compiled).toContain('font-family:');
  });

  it('compiles blockquote, strong, and links correctly', () => {
    const markdown = '> 这是一段引言\n**重要结论**\n[点击链接](https://example.com)';
    const compiled = compileWechatInlineHtml(markdown, 'humanist');

    expect(compiled).toContain('<blockquote style="');
    expect(compiled).toContain('<strong style="');
    expect(compiled).toContain('<a href="https://example.com" style="');
    expect(compiled).toContain('重要结论</strong>');
  });

  it('scales px font-sizes proportionally when compact or spacious scale is specified', () => {
    const markdown = '# 标杆设计';
    const normalHtml = compileWechatInlineHtml(markdown, 'classic', 'normal');
    const compactHtml = compileWechatInlineHtml(markdown, 'classic', 'compact');
    const spaciousHtml = compileWechatInlineHtml(markdown, 'classic', 'spacious');

    // Classic h1 has base font-size 22px
    // compact (0.9x): Math.round(22 * 0.9) = 20px
    // spacious (1.1x): Math.round(22 * 1.1) = 24px
    expect(normalHtml).toContain('font-size: 22px;');
    expect(compactHtml).toContain('font-size: 20px;');
    expect(spaciousHtml).toContain('font-size: 24px;');
  });

  it('merges inline styles onto existing HTML tags preserving preexisting styles', () => {
    const existingHtml = '<p style="color: red;">原有红字段落</p>';
    const compiled = compileWechatInlineHtml(existingHtml, 'enterprise');

    expect(compiled).toContain('<p style="color: red;');
    expect(compiled).toContain('line-height:');
    expect(compiled).toContain('原有红字段落</p>');
  });
});
