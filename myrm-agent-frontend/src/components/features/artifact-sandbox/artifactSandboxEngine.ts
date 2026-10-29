/**
 * artifactSandboxEngine.ts
 * 通用办公工件沙盒运行、CSS Inliner 内联转化排版与金融沙盘因果推演纯函数引擎
 */

import type {
  FinancialSandplayMetrics,
  FinancialShockScenario,
  InlinerAssetItem,
  NewsletterTheme,
  ThemeStyleDefinition,
} from './artifactSandboxTypes';

export const THEME_DEFINITIONS: Record<NewsletterTheme, ThemeStyleDefinition> = {
  mint_breeze: {
    id: 'mint_breeze',
    name: '薄荷清新',
    description: '清新绿色高亮、精致双色卡片、优雅引用边框',
    accentColor: '#10b981',
    containerStyle: {
      padding: '24px',
      backgroundColor: '#f0fdf4',
      color: '#064e3b',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      lineHeight: '1.75',
    },
    h1Style: {
      fontSize: '22px',
      fontWeight: '700',
      color: '#065f46',
      borderBottom: '2px solid #a7f3d0',
      paddingBottom: '8px',
      marginBottom: '16px',
    },
    h2Style: {
      fontSize: '18px',
      fontWeight: '600',
      color: '#047857',
      marginTop: '20px',
      marginBottom: '12px',
    },
    pStyle: {
      fontSize: '15px',
      lineHeight: '1.8',
      marginBottom: '14px',
      color: '#134e4a',
    },
    quoteStyle: {
      borderLeft: '4px solid #10b981',
      paddingLeft: '14px',
      backgroundColor: '#e6fcf5',
      margin: '16px 0',
      fontStyle: 'italic',
      color: '#047857',
    },
    codeBlockStyle: {
      backgroundColor: '#064e3b',
      color: '#a7f3d0',
      padding: '12px',
      borderRadius: '8px',
      fontSize: '13px',
      fontFamily: 'Menlo, Monaco, Consolas, monospace',
      overflowX: 'auto',
    },
    tableStyle: {
      width: '100%',
      borderCollapse: 'collapse',
      margin: '16px 0',
      border: '1px solid #a7f3d0',
    },
  },
  executive_noir: {
    id: 'executive_noir',
    name: '极简商务',
    description: '深灰低调奢华、高对比度黑白、严谨细边框',
    accentColor: '#334155',
    containerStyle: {
      padding: '24px',
      backgroundColor: '#ffffff',
      color: '#1e293b',
      fontFamily: 'Georgia, "Times New Roman", serif',
      lineHeight: '1.8',
    },
    h1Style: {
      fontSize: '24px',
      fontWeight: '800',
      color: '#0f172a',
      letterSpacing: '-0.5px',
      borderBottom: '2px solid #0f172a',
      paddingBottom: '10px',
      marginBottom: '18px',
    },
    h2Style: {
      fontSize: '19px',
      fontWeight: '700',
      color: '#334155',
      marginTop: '22px',
      marginBottom: '12px',
    },
    pStyle: {
      fontSize: '15px',
      lineHeight: '1.85',
      marginBottom: '16px',
      color: '#334155',
    },
    quoteStyle: {
      borderLeft: '4px solid #475569',
      paddingLeft: '16px',
      backgroundColor: '#f8fafc',
      margin: '18px 0',
      color: '#64748b',
    },
    codeBlockStyle: {
      backgroundColor: '#0f172a',
      color: '#f8fafc',
      padding: '14px',
      borderRadius: '4px',
      fontSize: '13px',
      fontFamily: 'Consolas, monospace',
    },
    tableStyle: {
      width: '100%',
      borderCollapse: 'collapse',
      margin: '18px 0',
      border: '1px solid #cbd5e1',
    },
  },
  cyber_blue: {
    id: 'cyber_blue',
    name: '未来科技',
    description: '深蓝霓虹高亮、终端代码风、极客科幻感',
    accentColor: '#3b82f6',
    containerStyle: {
      padding: '24px',
      backgroundColor: '#0f172a',
      color: '#e2e8f0',
      fontFamily: 'Inter, -apple-system, sans-serif',
      lineHeight: '1.75',
    },
    h1Style: {
      fontSize: '22px',
      fontWeight: '700',
      color: '#60a5fa',
      borderBottom: '2px solid #2563eb',
      paddingBottom: '8px',
      marginBottom: '16px',
    },
    h2Style: {
      fontSize: '18px',
      fontWeight: '600',
      color: '#93c5fd',
      marginTop: '20px',
      marginBottom: '12px',
    },
    pStyle: {
      fontSize: '14px',
      lineHeight: '1.8',
      marginBottom: '14px',
      color: '#cbd5e1',
    },
    quoteStyle: {
      borderLeft: '4px solid #3b82f6',
      paddingLeft: '14px',
      backgroundColor: '#1e293b',
      margin: '16px 0',
      color: '#93c5fd',
    },
    codeBlockStyle: {
      backgroundColor: '#020617',
      color: '#38bdf8',
      padding: '14px',
      borderRadius: '8px',
      border: '1px solid #1e3a8a',
      fontSize: '13px',
      fontFamily: 'monospace',
    },
    tableStyle: {
      width: '100%',
      borderCollapse: 'collapse',
      margin: '16px 0',
      border: '1px solid #1e3a8a',
    },
  },
  retro_amber: {
    id: 'retro_amber',
    name: '复古文艺',
    description: '暖琥珀色调、温润纸质阅读感、古典排版',
    accentColor: '#d97706',
    containerStyle: {
      padding: '24px',
      backgroundColor: '#fffbeb',
      color: '#78350f',
      fontFamily: '"Songti SC", "Noto Serif CJK SC", serif',
      lineHeight: '1.85',
    },
    h1Style: {
      fontSize: '23px',
      fontWeight: '700',
      color: '#92400e',
      borderBottom: '2px solid #fde68a',
      paddingBottom: '8px',
      marginBottom: '16px',
    },
    h2Style: {
      fontSize: '18px',
      fontWeight: '600',
      color: '#b45309',
      marginTop: '20px',
      marginBottom: '12px',
    },
    pStyle: {
      fontSize: '15px',
      lineHeight: '1.9',
      marginBottom: '16px',
      color: '#92400e',
    },
    quoteStyle: {
      borderLeft: '4px solid #d97706',
      paddingLeft: '14px',
      backgroundColor: '#fef3c7',
      margin: '16px 0',
      color: '#b45309',
    },
    codeBlockStyle: {
      backgroundColor: '#451a03',
      color: '#fef3c7',
      padding: '12px',
      borderRadius: '6px',
      fontSize: '13px',
      fontFamily: 'monospace',
    },
    tableStyle: {
      width: '100%',
      borderCollapse: 'collapse',
      margin: '16px 0',
      border: '1px solid #fde68a',
    },
  },
};

export function recordToStyleString(record: Record<string, string>): string {
  return Object.entries(record)
    .map(([k, v]) => {
      const kebabKey = k.replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`);
      return `${kebabKey}: ${v};`;
    })
    .join(' ');
}

export function compileInlinedHtml(
  rawContent: string,
  theme: NewsletterTheme
): string {
  const def = THEME_DEFINITIONS[theme];
  let html = rawContent;

  const containerStyle = recordToStyleString(def.containerStyle);
  const h1Style = recordToStyleString(def.h1Style);
  const h2Style = recordToStyleString(def.h2Style);
  const pStyle = recordToStyleString(def.pStyle);
  const quoteStyle = recordToStyleString(def.quoteStyle);
  const codeStyle = recordToStyleString(def.codeBlockStyle);
  const tableStyle = recordToStyleString(def.tableStyle);

  // 替换各标签以注入 inline CSS
  html = html.replace(/<h1(\s[^>]*)?>/gi, `<h1 style="${h1Style}">`);
  html = html.replace(/<h2(\s[^>]*)?>/gi, `<h2 style="${h2Style}">`);
  html = html.replace(/<p(\s[^>]*)?>/gi, `<p style="${pStyle}">`);
  html = html.replace(/<blockquote(\s[^>]*)?>/gi, `<blockquote style="${quoteStyle}">`);
  html = html.replace(/<pre(\s[^>]*)?>/gi, `<pre style="${codeStyle}">`);
  html = html.replace(/<table(\s[^>]*)?>/gi, `<table style="${tableStyle}">`);

  return `<div class="rich-newsletter-container" style="${containerStyle}">${html}</div>`;
}

export function buildSafeSandboxIframeSrcDoc(htmlContent: string): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { margin: 0; padding: 16px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    * { box-sizing: border-box; }
  </style>
</head>
<body>
  ${htmlContent}
</body>
</html>`;
}

export function bundleSingleFileOfflineHtml(
  htmlContent: string,
  assets: InlinerAssetItem[]
): string {
  let bundled = htmlContent;
  for (const asset of assets) {
    const dataUri = `data:${asset.mimeType};base64,${asset.base64}`;
    // 替换外链资源引用
    bundled = bundled.split(asset.name).join(dataUri);
  }
  return bundled;
}

export function calculateFinancialSandplay(
  base: FinancialSandplayMetrics,
  shock?: FinancialShockScenario
): FinancialSandplayMetrics {
  const current: FinancialSandplayMetrics = { ...base };

  if (shock !== undefined && shock.impactDeltas !== undefined) {
    if (shock.impactDeltas.upstreamRawMaterialCost !== undefined) {
      current.upstreamRawMaterialCost = Math.max(
        0,
        current.upstreamRawMaterialCost + shock.impactDeltas.upstreamRawMaterialCost
      );
    }
    if (shock.impactDeltas.midstreamProcessingCapacity !== undefined) {
      current.midstreamProcessingCapacity = Math.max(
        0,
        Math.min(
          100,
          current.midstreamProcessingCapacity +
            shock.impactDeltas.midstreamProcessingCapacity
        )
      );
    }
    if (shock.impactDeltas.downstreamEndUserDemand !== undefined) {
      current.downstreamEndUserDemand = Math.max(
        0,
        current.downstreamEndUserDemand + shock.impactDeltas.downstreamEndUserDemand
      );
    }
  }

  // 计算预期净利率
  const profitMargin =
    current.downstreamEndUserDemand * 0.12 +
    current.midstreamProcessingCapacity * 0.15 -
    current.upstreamRawMaterialCost * 0.14;
  current.projectedProfitMargin = Number(profitMargin.toFixed(2));

  // 计算系统性脆弱度风险指数 (0 - 100)
  const rawRisk =
    current.upstreamRawMaterialCost * 0.3 +
    (100 - current.midstreamProcessingCapacity) * 0.35 +
    Math.max(0, 150 - current.downstreamEndUserDemand) * 0.2;
  current.systemicRiskIndex = Math.min(100, Math.max(0, Number(rawRisk.toFixed(1))));

  return current;
}
