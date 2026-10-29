/**
 * artifactSandboxTypes.ts
 * 通用办公工件交互沙盒、公众号富文本多模板美化排版与金融沙盘因果推演套件类型
 */

export type ArtifactSandboxMode =
  | 'html_live'
  | 'rich_newsletter'
  | 'financial_sandplay';

export type NewsletterTheme =
  | 'mint_breeze'
  | 'executive_noir'
  | 'cyber_blue'
  | 'retro_amber';

export interface ThemeStyleDefinition {
  id: NewsletterTheme;
  name: string;
  description: string;
  accentColor: string;
  containerStyle: Record<string, string>;
  h1Style: Record<string, string>;
  h2Style: Record<string, string>;
  pStyle: Record<string, string>;
  quoteStyle: Record<string, string>;
  codeBlockStyle: Record<string, string>;
  tableStyle: Record<string, string>;
}

export interface InlinerAssetItem {
  name: string;
  mimeType: string;
  base64: string;
}

export interface InteractiveArtifactItem {
  id: string;
  title: string;
  mode: ArtifactSandboxMode;
  rawContent: string;
  theme?: NewsletterTheme;
  assets?: InlinerAssetItem[];
  updatedAt: number;
}

export interface FinancialSandplayMetrics {
  upstreamRawMaterialCost: number; // 上游原材料成本指数 (0 - 200)
  midstreamProcessingCapacity: number; // 中游产能利用率 (0 - 100%)
  downstreamEndUserDemand: number; // 下游终端口径需求 (0 - 200)
  projectedProfitMargin: number; // 预期综合净利率 (%)
  systemicRiskIndex: number; // 系统性供应链脆弱度 (0 - 100)
}

export interface FinancialShockScenario {
  id: string;
  name: string;
  description: string;
  impactDeltas: Partial<FinancialSandplayMetrics>;
}

export interface RichCopyResult {
  success: boolean;
  copiedChars: number;
  themeUsed: NewsletterTheme;
  error?: string;
  timestamp: number;
}
