export type Locale = (typeof locales)[number];

export const locales = ['zh', 'en', 'ja', 'ko', 'de', 'zh-TW'] as const;
export const defaultLocale: Locale = 'zh';
