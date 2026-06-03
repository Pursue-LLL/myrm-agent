import { describe, it, expect, beforeEach } from 'vitest';
import { buildMermaidConfig, MERMAID_FONT_FAMILY, type MermaidChartProps, type LegendItem } from '../mermaid-theme';

describe('buildMermaidConfig', () => {
  beforeEach(() => {
    document.documentElement.style.cssText = '';
  });

  it('returns base theme with startOnLoad disabled', () => {
    const config = buildMermaidConfig(false);
    expect(config.startOnLoad).toBe(false);
    expect(config.theme).toBe('base');
    expect(config.securityLevel).toBe('loose');
    expect(config.fontFamily).toBe(MERMAID_FONT_FAMILY);
    expect(config.fontSize).toBe(14);
  });

  it('uses fallback values when CSS variables are not set', () => {
    const lightConfig = buildMermaidConfig(false);
    expect(lightConfig.themeVariables.darkMode).toBe(false);
    expect(lightConfig.themeVariables.primaryBorderColor).toBe('#588e95');
    expect(lightConfig.themeVariables.textColor).toBe('#0a0a0a');
    expect(lightConfig.themeVariables.background).toBe('#fdfdfb');

    const darkConfig = buildMermaidConfig(true);
    expect(darkConfig.themeVariables.darkMode).toBe(true);
    expect(darkConfig.themeVariables.primaryBorderColor).toBe('#2993e9');
    expect(darkConfig.themeVariables.textColor).toBe('#fbfbf8');
    expect(darkConfig.themeVariables.background).toBe('#0a0a0a');
  });

  it('reads values from CSS variables when available', () => {
    document.documentElement.style.setProperty('--primary', '#ff0000');
    document.documentElement.style.setProperty('--foreground', '#111111');
    document.documentElement.style.setProperty('--background', '#eeeeee');

    const config = buildMermaidConfig(false);
    expect(config.themeVariables.primaryBorderColor).toBe('#ff0000');
    expect(config.themeVariables.textColor).toBe('#111111');
    expect(config.themeVariables.background).toBe('#eeeeee');
    expect(config.themeVariables.lineColor).toBe('#ff0000');
  });

  it('includes consistent font family in themeVariables', () => {
    const config = buildMermaidConfig(false);
    expect(config.themeVariables.fontFamily).toBe(MERMAID_FONT_FAMILY);
  });

  it('sets appropriate secondary/tertiary colors for dark mode', () => {
    const darkConfig = buildMermaidConfig(true);
    expect(darkConfig.themeVariables.secondaryColor).toBe('#1a1a2e');
    expect(darkConfig.themeVariables.tertiaryColor).toBe('#0d1117');

    const lightConfig = buildMermaidConfig(false);
    expect(lightConfig.themeVariables.secondaryColor).toBe('#e8f4f5');
    expect(lightConfig.themeVariables.tertiaryColor).toBe('#f0f9fa');
  });
});

describe('buildMermaidConfig — full CSS variable override', () => {
  beforeEach(() => {
    document.documentElement.style.cssText = '';
  });

  it('reads --secondary, --border, --muted-foreground from CSS variables', () => {
    document.documentElement.style.setProperty('--secondary', '#aabbcc');
    document.documentElement.style.setProperty('--border', '#112233');
    document.documentElement.style.setProperty('--muted-foreground', '#778899');

    const config = buildMermaidConfig(false);
    expect(config.themeVariables.primaryColor).toBe('#aabbcc');
    expect(config.themeVariables.secondaryBorderColor).toBe('#112233');
    expect(config.themeVariables.tertiaryBorderColor).toBe('#112233');
    expect(config.themeVariables.tertiaryTextColor).toBe('#778899');
  });

  it('overrides all six CSS variables simultaneously', () => {
    document.documentElement.style.setProperty('--primary', '#aa0000');
    document.documentElement.style.setProperty('--foreground', '#bb0000');
    document.documentElement.style.setProperty('--background', '#cc0000');
    document.documentElement.style.setProperty('--secondary', '#dd0000');
    document.documentElement.style.setProperty('--border', '#ee0000');
    document.documentElement.style.setProperty('--muted-foreground', '#ff0000');

    const config = buildMermaidConfig(true);
    expect(config.themeVariables.primaryBorderColor).toBe('#aa0000');
    expect(config.themeVariables.primaryTextColor).toBe('#bb0000');
    expect(config.themeVariables.background).toBe('#cc0000');
    expect(config.themeVariables.primaryColor).toBe('#dd0000');
    expect(config.themeVariables.secondaryBorderColor).toBe('#ee0000');
    expect(config.themeVariables.tertiaryTextColor).toBe('#ff0000');
    expect(config.themeVariables.lineColor).toBe('#aa0000');
    expect(config.themeVariables.noteBorderColor).toBe('#aa0000');
    expect(config.themeVariables.noteTextColor).toBe('#bb0000');
    expect(config.themeVariables.textColor).toBe('#bb0000');
    expect(config.themeVariables.secondaryTextColor).toBe('#bb0000');
  });
});

describe('buildMermaidConfig — note styling', () => {
  beforeEach(() => {
    document.documentElement.style.cssText = '';
  });

  it('uses dark note background in dark mode', () => {
    const config = buildMermaidConfig(true);
    expect(config.themeVariables.noteBkgColor).toBe('#1a1a2e');
  });

  it('uses light note background in light mode', () => {
    const config = buildMermaidConfig(false);
    expect(config.themeVariables.noteBkgColor).toBe('#fff9e6');
  });

  it('maps noteBorderColor to --primary', () => {
    document.documentElement.style.setProperty('--primary', '#123456');
    const config = buildMermaidConfig(false);
    expect(config.themeVariables.noteBorderColor).toBe('#123456');
  });

  it('maps noteTextColor to --foreground', () => {
    document.documentElement.style.setProperty('--foreground', '#abcdef');
    const config = buildMermaidConfig(false);
    expect(config.themeVariables.noteTextColor).toBe('#abcdef');
  });
});

describe('buildMermaidConfig — fontSize consistency', () => {
  it('config.fontSize is number 14, themeVariables.fontSize is string "14px"', () => {
    const config = buildMermaidConfig(false);
    expect(config.fontSize).toBe(14);
    expect(typeof config.fontSize).toBe('number');
    expect(config.themeVariables.fontSize).toBe('14px');
    expect(typeof config.themeVariables.fontSize).toBe('string');
  });
});

describe('buildMermaidConfig — primaryColor maps to --secondary', () => {
  beforeEach(() => {
    document.documentElement.style.cssText = '';
  });

  it('primaryColor uses --secondary CSS variable (node fill color)', () => {
    document.documentElement.style.setProperty('--secondary', '#custom_sec');
    const config = buildMermaidConfig(false);
    expect(config.themeVariables.primaryColor).toBe('#custom_sec');
  });

  it('primaryColor falls back to dark secondary when no CSS var', () => {
    const dark = buildMermaidConfig(true);
    expect(dark.themeVariables.primaryColor).toBe('#111111');
    const light = buildMermaidConfig(false);
    expect(light.themeVariables.primaryColor).toBe('#f6f6f1');
  });
});

describe('MERMAID_FONT_FAMILY', () => {
  it('includes system UI font stack keywords', () => {
    expect(MERMAID_FONT_FAMILY).toContain('ui-sans-serif');
    expect(MERMAID_FONT_FAMILY).toContain('system-ui');
    expect(MERMAID_FONT_FAMILY).toContain('sans-serif');
  });

  it('includes cross-platform fallback fonts', () => {
    expect(MERMAID_FONT_FAMILY).toContain('Segoe UI');
    expect(MERMAID_FONT_FAMILY).toContain('Roboto');
    expect(MERMAID_FONT_FAMILY).toContain('Noto Sans');
  });
});

describe('type exports', () => {
  it('MermaidChartProps accepts chart and optional id', () => {
    const props: MermaidChartProps = { chart: 'graph TD; A-->B' };
    expect(props.chart).toBe('graph TD; A-->B');
    expect(props.id).toBeUndefined();

    const propsWithId: MermaidChartProps = { chart: 'graph LR; X-->Y', id: 'test-id' };
    expect(propsWithId.id).toBe('test-id');
  });

  it('LegendItem requires className and label, color is optional', () => {
    const item: LegendItem = { className: 'cls-a', label: 'Node A' };
    expect(item.color).toBeUndefined();

    const itemWithColor: LegendItem = { className: 'cls-b', label: 'Node B', color: '#ff0' };
    expect(itemWithColor.color).toBe('#ff0');
  });
});
