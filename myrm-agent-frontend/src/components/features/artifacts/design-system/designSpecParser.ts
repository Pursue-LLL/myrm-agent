import type {
  DesignColorTokens,
  DesignGeometryTokens,
  DesignSystemSpec,
  DesignSystemTokens,
  DesignTypographyTokens,
} from './designSpecTypes';

export const APPLE_CLEAN_SPEC: DesignSystemSpec = {
  specId: 'spec_apple_clean',
  name: 'Apple Clean (极简科技美学)',
  version: '2.4.0',
  description: '高留白、无干扰排版、柔和微弥散阴影与精致视差层级',
  author: 'Myrmidon Design Lab',
  tokens: {
    colors: {
      primary: '#0071e3',
      primaryHover: '#0077ed',
      surface: '#ffffff',
      background: '#f5f5f7',
      textPrimary: '#1d1d1f',
      textMuted: '#86868b',
      border: '#d2d2d7',
      accent: '#2997ff',
    },
    typography: {
      fontFamilySans: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif',
      fontFamilyMono: 'SF Mono, Menlo, monospace',
      headingScale: '1.25',
      bodyLeading: '1.5',
    },
    geometry: {
      borderRadius: '16px',
      containerPadding: '32px',
      shadowLevel: '0 8px 30px rgba(0, 0, 0, 0.06)',
    },
  },
  rawMarkdown: `# Apple Clean Design System

## Palette
- Primary: #0071e3
- Primary Hover: #0077ed
- Surface: #ffffff
- Background: #f5f5f7
- Text Primary: #1d1d1f
- Text Muted: #86868b
- Border: #d2d2d7
- Accent: #2997ff

## Typography
- Font Family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif
- Monospace: SF Mono, Menlo, monospace
- Heading Scale: 1.25

## Geometry
- Border Radius: 16px
- Padding: 32px
- Shadow: 0 8px 30px rgba(0, 0, 0, 0.06)
`,
};

export const MINIMAL_B2B_SPEC: DesignSystemSpec = {
  specId: 'spec_minimal_b2b',
  name: 'Minimal B2B (沉稳企业级 Slate)',
  version: '3.1.0',
  description: '工业级深蓝灰调、高对比度数据层级与严谨栅格排版，适合 SaaS 与管理中台',
  author: 'Refero Enterprise Design',
  tokens: {
    colors: {
      primary: '#4f46e5',
      primaryHover: '#4338ca',
      surface: '#0f172a',
      background: '#020617',
      textPrimary: '#f8fafc',
      textMuted: '#94a3b8',
      border: '#1e293b',
      accent: '#10b981',
    },
    typography: {
      fontFamilySans: 'Inter, system-ui, -apple-system, sans-serif',
      fontFamilyMono: 'JetBrains Mono, Menlo, monospace',
      headingScale: '1.2',
      bodyLeading: '1.45',
    },
    geometry: {
      borderRadius: '8px',
      containerPadding: '24px',
      shadowLevel: '0 4px 16px rgba(0, 0, 0, 0.3)',
    },
  },
  rawMarkdown: `# Minimal B2B Design System

## Palette
- Primary: #4f46e5
- Primary Hover: #4338ca
- Surface: #0f172a
- Background: #020617
- Text Primary: #f8fafc
- Text Muted: #94a3b8
- Border: #1e293b
- Accent: #10b981

## Typography
- Font Family: Inter, system-ui, sans-serif
- Monospace: JetBrains Mono, monospace
- Heading Scale: 1.2

## Geometry
- Border Radius: 8px
- Padding: 24px
- Shadow: 0 4px 16px rgba(0, 0, 0, 0.3)
`,
};

export const CYBERPUNK_NEON_SPEC: DesignSystemSpec = {
  specId: 'spec_cyberpunk_neon',
  name: 'Cyberpunk Neon (极客暗黑霓虹)',
  version: '1.8.5',
  description: '纯黑深渊背景搭配高饱和青紫发光边框，适合 AI 交互、代码控制台与音视频应用',
  author: 'Matrix Labs',
  tokens: {
    colors: {
      primary: '#06b6d4',
      primaryHover: '#22d3ee',
      surface: '#090d16',
      background: '#000000',
      textPrimary: '#f1f5f9',
      textMuted: '#64748b',
      border: '#164e63',
      accent: '#ec4899',
    },
    typography: {
      fontFamilySans: 'Fira Code, "SF Mono", monospace',
      fontFamilyMono: 'Fira Code, monospace',
      headingScale: '1.3',
      bodyLeading: '1.6',
    },
    geometry: {
      borderRadius: '4px',
      containerPadding: '20px',
      shadowLevel: '0 0 24px rgba(6, 182, 212, 0.25)',
    },
  },
  rawMarkdown: `# Cyberpunk Neon Design System

## Palette
- Primary: #06b6d4
- Primary Hover: #22d3ee
- Surface: #090d16
- Background: #000000
- Text Primary: #f1f5f9
- Text Muted: #64748b
- Border: #164e63
- Accent: #ec4899

## Typography
- Font Family: Fira Code, monospace
- Monospace: Fira Code, monospace
- Heading Scale: 1.3

## Geometry
- Border Radius: 4px
- Padding: 20px
- Shadow: 0 0 24px rgba(6, 182, 212, 0.25)
`,
};

export const PRESET_DESIGN_SPECS: DesignSystemSpec[] = [
  MINIMAL_B2B_SPEC,
  APPLE_CLEAN_SPEC,
  CYBERPUNK_NEON_SPEC,
];

function extractTokenValue(markdown: string, keyPattern: string, fallback: string): string {
  const regex = new RegExp(`(?:- |\\* )?${keyPattern}:\\s*([^\\n]+)`, 'i');
  const match = markdown.match(regex);
  if (match && match[1]) {
    return match[1].trim();
  }
  return fallback;
}

export function parseDesignMarkdown(rawMarkdown: string, specId = 'custom_spec'): DesignSystemSpec {
  const colors: DesignColorTokens = {
    primary: extractTokenValue(rawMarkdown, 'Primary', '#4f46e5'),
    primaryHover: extractTokenValue(rawMarkdown, 'Primary Hover', '#4338ca'),
    surface: extractTokenValue(rawMarkdown, 'Surface', '#0f172a'),
    background: extractTokenValue(rawMarkdown, 'Background', '#020617'),
    textPrimary: extractTokenValue(rawMarkdown, 'Text Primary', '#f8fafc'),
    textMuted: extractTokenValue(rawMarkdown, 'Text Muted', '#94a3b8'),
    border: extractTokenValue(rawMarkdown, 'Border', '#1e293b'),
    accent: extractTokenValue(rawMarkdown, 'Accent', '#10b981'),
  };

  const typography: DesignTypographyTokens = {
    fontFamilySans: extractTokenValue(rawMarkdown, 'Font Family', 'Inter, system-ui, sans-serif'),
    fontFamilyMono: extractTokenValue(rawMarkdown, 'Monospace', 'monospace'),
    headingScale: extractTokenValue(rawMarkdown, 'Heading Scale', '1.2'),
    bodyLeading: extractTokenValue(rawMarkdown, 'Body Leading', '1.5'),
  };

  const geometry: DesignGeometryTokens = {
    borderRadius: extractTokenValue(rawMarkdown, 'Border Radius', '8px'),
    containerPadding: extractTokenValue(rawMarkdown, 'Padding', '24px'),
    shadowLevel: extractTokenValue(rawMarkdown, 'Shadow', '0 4px 16px rgba(0, 0, 0, 0.2)'),
  };

  return {
    specId,
    name: extractTokenValue(rawMarkdown, 'Title|Name', '自定义 DESIGN.md 规范'),
    version: '1.0.0',
    description: '通过解析 Markdown 设计规范提取的主题令牌',
    author: 'Agent User',
    tokens: { colors, typography, geometry },
    rawMarkdown,
  };
}

export function generateCssVariables(tokens: DesignSystemTokens): string {
  return `
    :root {
      --ds-color-primary: ${tokens.colors.primary};
      --ds-color-primary-hover: ${tokens.colors.primaryHover};
      --ds-color-surface: ${tokens.colors.surface};
      --ds-color-bg: ${tokens.colors.background};
      --ds-color-text-primary: ${tokens.colors.textPrimary};
      --ds-color-text-muted: ${tokens.colors.textMuted};
      --ds-color-border: ${tokens.colors.border};
      --ds-color-accent: ${tokens.colors.accent};
      --ds-font-sans: ${tokens.typography.fontFamilySans};
      --ds-font-mono: ${tokens.typography.fontFamilyMono};
      --ds-radius: ${tokens.geometry.borderRadius};
      --ds-padding: ${tokens.geometry.containerPadding};
      --ds-shadow: ${tokens.geometry.shadowLevel};
    }
  `.trim();
}
