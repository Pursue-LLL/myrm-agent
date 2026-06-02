export type Locale = (typeof locales)[number];

export const locales = ['zh', 'en', 'ja', 'ko', 'de'] as const;
export const defaultLocale: Locale = 'zh';
