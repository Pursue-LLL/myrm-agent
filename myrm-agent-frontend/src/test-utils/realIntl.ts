/**
 * [INPUT]
 * - locales/{en,zh}.json (POS: 真实语言包)
 * - next-intl::createTranslator (POS: 真实的 ICU 翻译器)
 *
 * [OUTPUT]
 * - createRealIntlMock: 以真实语言包构造 next-intl 的 mock，供 `vi.mock('next-intl', ...)` 的工厂使用
 *
 * [POS]
 * 前端测试共享的真实翻译层。全局 mock 把 `t(key)` 当恒等函数、忽略插值参数，验证不了「文案里带了什么」；
 * 需要断言最终展示给用户的句子时用这里。
 */
import { vi } from 'vitest';
import type { AbstractIntlMessages } from 'next-intl';

export type MockLocale = 'en' | 'zh';

/**
 * 翻译器按（语言, 命名空间）缓存，引用稳定——与真实 next-intl 一致，也满足 setup.ts 对 useTranslations 稳定引用的要求。
 * `currentLocale` 每次调用 useTranslations 时求值，测试可在用例间切换语言。
 */
export async function createRealIntlMock(currentLocale: () => MockLocale) {
  const actual = await vi.importActual<typeof import('next-intl')>('next-intl');
  const bundles: Record<MockLocale, AbstractIntlMessages> = {
    en: (await import('../../locales/en.json')).default,
    zh: (await import('../../locales/zh.json')).default,
  };
  const translators = new Map<string, unknown>();

  return {
    useLocale: currentLocale,
    useTranslations: (namespace?: string) => {
      const locale = currentLocale();
      const key = `${locale}:${namespace ?? ''}`;
      if (!translators.has(key)) {
        translators.set(key, actual.createTranslator({ locale, messages: bundles[locale], namespace }));
      }
      return translators.get(key);
    },
  };
}
