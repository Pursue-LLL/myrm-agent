/**
 * Bidi Shield Zustand Store
 * 全球化双向文本排版防护、CSS 逻辑属性映射与 Windows 字体防御状态调度器
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯净状态流转，预置丰富阿语/希伯来语/代码混合对比用例。
 */

import { create } from 'zustand';
import {
  detectTextDirection,
} from './bidiDetectorEngine';
import {
  BidiDetectionResult,
  BidiShieldPresetExample,
  TextDirection,
} from './bidiShieldTypes';

interface BidiShieldState {
  direction: TextDirection;
  activeLocale: string;
  isWindowsTypographyShieldActive: boolean;
  autoDetectTextDirection: boolean;
  customInputText: string;
  samplePresets: BidiShieldPresetExample[];

  // Actions
  setDirection: (dir: TextDirection) => void;
  setActiveLocale: (locale: string) => void;
  toggleWindowsTypographyShield: () => void;
  setAutoDetectTextDirection: (auto: boolean) => void;
  setCustomInputText: (text: string) => void;
  loadPreset: (presetId: string) => void;
  getCurrentDetection: () => BidiDetectionResult;
  resetToDefault: () => void;
}

const DEFAULT_SAMPLE_PRESETS: BidiShieldPresetExample[] = [
  {
    id: 'preset-ar-code',
    title: '阿拉伯语混合 Python 变量与数字',
    description: '对标 Hermes 评论区中东用户反馈：阿语中插入变量名时标点乱跳与反向错位',
    sampleText: 'يرجى مراجعة المتغير `user_token` والتأكد من القيمة 2026-10-15 في الدالة `calculate_hash()` بشكل دقيق.',
    expectedDirection: 'rtl',
  },
  {
    id: 'preset-he-url',
    title: '希伯来语混合 HTTPS 端点与端口',
    description: '希伯来文本中混杂多段英文字段与 IP 端口地址',
    sampleText: 'השרת המקומי פועל בכתובת https://localhost:8000/api/health ומוכן לקבל חיבורים.',
    expectedDirection: 'rtl',
  },
  {
    id: 'preset-zh-tech',
    title: '中文混合技术术语与逻辑属性',
    description: '常规 LTR 语系混合 CSS 逻辑属性与英文缩写',
    sampleText: '通过全面引入 `padding-inline-start` 与 `<bdi>` 标签，确保 RTL 语系下布局镜像反转。',
    expectedDirection: 'ltr',
  },
];

export const useBidiShieldStore = create<BidiShieldState>((set, get) => ({
  direction: 'auto',
  activeLocale: 'ar',
  isWindowsTypographyShieldActive: true,
  autoDetectTextDirection: true,
  customInputText: DEFAULT_SAMPLE_PRESETS[0].sampleText,
  samplePresets: DEFAULT_SAMPLE_PRESETS,

  setDirection: (dir: TextDirection) => {
    set({ direction: dir });
  },

  setActiveLocale: (locale: string) => {
    const isRtlLocale = ['ar', 'he', 'fa', 'ur'].includes(locale);
    set({
      activeLocale: locale,
      direction: isRtlLocale ? 'rtl' : 'ltr',
    });
  },

  toggleWindowsTypographyShield: () => {
    set((state) => ({
      isWindowsTypographyShieldActive: !state.isWindowsTypographyShieldActive,
    }));
  },

  setAutoDetectTextDirection: (auto: boolean) => {
    set({ autoDetectTextDirection: auto });
  },

  setCustomInputText: (text: string) => {
    set({ customInputText: text });
  },

  loadPreset: (presetId: string) => {
    const target = get().samplePresets.find((p) => p.id === presetId);
    if (target) {
      set({
        customInputText: target.sampleText,
        direction: target.expectedDirection,
      });
    }
  },

  getCurrentDetection: () => {
    const text = get().customInputText;
    return detectTextDirection(text);
  },

  resetToDefault: () => {
    set({
      direction: 'auto',
      activeLocale: 'ar',
      isWindowsTypographyShieldActive: true,
      autoDetectTextDirection: true,
      customInputText: DEFAULT_SAMPLE_PRESETS[0].sampleText,
    });
  },
}));
