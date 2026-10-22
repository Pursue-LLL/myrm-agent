/**
 * Bidirectional RTL & Typography Shield Types
 * 全球化双向文本自动隔离排版、CSS 逻辑属性与 Windows 复杂多语系字体防御类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 规范定义书写方向状态机、双向文本分段与字体回退模型；
 * 3. 行数严格受控在 200 行以内。
 */

export type TextDirection = 'ltr' | 'rtl' | 'auto';

export interface BidiSegment {
  text: string;
  isRtl: boolean;
  isCodeOrVariable: boolean;
}

export interface BidiDetectionResult {
  dominantDirection: 'ltr' | 'rtl';
  rtlRatio: number;
  containsRtl: boolean;
  segments: BidiSegment[];
}

export interface TypographyShieldConfig {
  enableWindowsFontFallback: boolean;
  fontFamilyStack: string;
  preserveMixedPunctuation: boolean;
}

export interface BidiShieldPresetExample {
  id: string;
  title: string;
  description: string;
  sampleText: string;
  expectedDirection: 'ltr' | 'rtl';
}
