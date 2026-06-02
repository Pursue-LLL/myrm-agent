export const MERMAID_FONT_FAMILY =
  'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif';

export interface MermaidChartProps {
  chart: string;
  id?: string;
}

export interface LegendItem {
  className: string;
  label: string;
  color?: string;
}

function getCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function buildMermaidThemeVariables(isDark: boolean) {
  const primary = getCssVar('--primary') || (isDark ? '#2993e9' : '#588e95');
  const foreground = getCssVar('--foreground') || (isDark ? '#fbfbf8' : '#0a0a0a');
  const background = getCssVar('--background') || (isDark ? '#0a0a0a' : '#fdfdfb');
  const secondary = getCssVar('--secondary') || (isDark ? '#111111' : '#f6f6f1');
  const border = getCssVar('--border') || (isDark ? '#1c1c1c' : '#f0f0ec');
  const muted = getCssVar('--muted-foreground') || (isDark ? '#f2f2ed' : '#1c1c1c');

  return {
    darkMode: isDark,
    primaryColor: secondary,
    primaryTextColor: foreground,
    primaryBorderColor: primary,
    secondaryColor: isDark ? '#1a1a2e' : '#e8f4f5',
    secondaryTextColor: foreground,
    secondaryBorderColor: border,
    tertiaryColor: isDark ? '#0d1117' : '#f0f9fa',
    tertiaryTextColor: muted,
    tertiaryBorderColor: border,
    background,
    textColor: foreground,
    lineColor: primary,
    fontFamily: MERMAID_FONT_FAMILY,
    fontSize: '14px',
    noteBkgColor: isDark ? '#1a1a2e' : '#fff9e6',
    noteTextColor: foreground,
    noteBorderColor: primary,
  };
}

export function buildMermaidConfig(isDark: boolean) {
  return {
    startOnLoad: false,
    theme: 'base' as const,
    securityLevel: 'loose' as const,
    fontFamily: MERMAID_FONT_FAMILY,
    fontSize: 14,
    themeVariables: buildMermaidThemeVariables(isDark),
  };
}
