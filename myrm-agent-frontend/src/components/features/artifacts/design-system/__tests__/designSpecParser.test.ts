import { describe, expect, it } from 'vitest';
import {
  APPLE_CLEAN_SPEC,
  MINIMAL_B2B_SPEC,
  CYBERPUNK_NEON_SPEC,
  PRESET_DESIGN_SPECS,
  parseDesignMarkdown,
  generateCssVariables,
} from '../designSpecParser';

describe('designSpecParser', () => {
  it('预置设计系统规范完整有效', () => {
    expect(PRESET_DESIGN_SPECS.length).toBe(3);
    expect(MINIMAL_B2B_SPEC.tokens.colors.primary).toBe('#4f46e5');
    expect(APPLE_CLEAN_SPEC.tokens.colors.primary).toBe('#0071e3');
    expect(CYBERPUNK_NEON_SPEC.tokens.colors.primary).toBe('#06b6d4');
  });

  it('parseDesignMarkdown 能够从 Markdown 文本中提取令牌', () => {
    const rawMd = `
# Custom Brand Spec
- Primary: #ff5722
- Surface: #1e1e1e
- Border Radius: 12px
- Font Family: Roboto, sans-serif
    `;

    const parsed = parseDesignMarkdown(rawMd, 'spec_custom_01');
    expect(parsed.specId).toBe('spec_custom_01');
    expect(parsed.tokens.colors.primary).toBe('#ff5722');
    expect(parsed.tokens.colors.surface).toBe('#1e1e1e');
    expect(parsed.tokens.geometry.borderRadius).toBe('12px');
    expect(parsed.tokens.typography.fontFamilySans).toBe('Roboto, sans-serif');
  });

  it('generateCssVariables 能够生成标准 :root 级 CSS 变量映射', () => {
    const cssVars = generateCssVariables(MINIMAL_B2B_SPEC.tokens);
    expect(cssVars).toContain('--ds-color-primary: #4f46e5;');
    expect(cssVars).toContain('--ds-color-surface: #0f172a;');
    expect(cssVars).toContain('--ds-radius: 8px;');
  });
});
