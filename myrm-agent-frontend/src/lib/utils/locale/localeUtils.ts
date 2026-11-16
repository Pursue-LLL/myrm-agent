/**
 * [INPUT]
 * - @/i18n/config (POS: 支持 locale 列表与 defaultLocale)
 *
 * [OUTPUT]
 * - NEXT_LOCALE_COOKIE_NAME: next-intl locale cookie 名称常量
 * - getClientLocale(): 客户端从 document.cookie 读取当前 locale
 * - normalizeLocaleForBackend(): 前端 locale → 后端格式映射（应用不再提供的语言映射为 undefined）
 * - resolveBackendLocale(): 后端回复语言 — 已保存偏好仍受支持时用偏好，否则用界面语言 cookie
 * - parseLocaleQueryParam(): 营销 ?locale= 参数解析
 * - urlWithoutLocaleParam(): 剥离 locale 参数的 URL 克隆
 * - negotiateLocale(): RFC 7231 Accept-Language 协商最佳匹配 locale
 *
 * [POS]
 * Locale 工具集。供 middleware 自动检测、营销接力、客户端读取和后端格式归一化。
 */
import { type Locale, locales } from '@/i18n/config';

/** next-intl locale cookie — shared by middleware relay and `i18n/index.ts`. */
export const NEXT_LOCALE_COOKIE_NAME = 'NEXT_LOCALE';

/**
 * Get current user locale from cookie
 * This works in client components
 */
export function getClientLocale(): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  // Read NEXT_LOCALE cookie (set by next-intl)
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === NEXT_LOCALE_COOKIE_NAME) {
      return value;
    }
  }

  return null;
}

/** Parse `?locale=` from marketing-site CTAs into a supported App locale. */
export function parseLocaleQueryParam(value: string | null): Locale | null {
  if (!value) {
    return null;
  }
  return (locales as readonly string[]).includes(value) ? (value as Locale) : null;
}

/** The App locale a stored value stands for: a supported locale itself, or the one a regional tag (zh-TW) belongs to. */
function toAppLocale(value: string | null | undefined): Locale | null {
  if (!value) {
    return null;
  }
  return parseLocaleQueryParam(value) ?? parseLocaleQueryParam(value.split(/[-_]/)[0].toLowerCase());
}

/**
 * Normalize locale to backend format
 * Frontend uses: 'zh', 'en'
 * Backend expects: 'zh-CN', 'en'. A value the App does not offer (e.g. a language saved before it was retired)
 * maps to undefined, so the caller falls through to its next source instead of relaying it.
 */
export function normalizeLocaleForBackend(value: string | null | undefined): string | undefined {
  const locale = toAppLocale(value);
  if (!locale) {
    return undefined;
  }
  return locale === 'zh' ? 'zh-CN' : locale;
}

/** The locale the backend answers in: the saved preference while the App still offers it, else the interface language. */
export function resolveBackendLocale(saved: string | null | undefined, cookie: string | null): string | undefined {
  return normalizeLocaleForBackend(saved) ?? normalizeLocaleForBackend(cookie);
}

/** Clone URL without `locale` search param (preserves redirect, token, utm, etc.). */
export function urlWithoutLocaleParam(url: URL): URL {
  const next = new URL(url.toString());
  next.searchParams.delete('locale');
  return next;
}

/**
 * Negotiate the best matching locale from an HTTP `Accept-Language` header.
 *
 * Parses quality-factor syntax per RFC 7231 §5.3.5, e.g.
 *   "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
 * and returns the highest-priority match among `supported`.
 *
 * Falls back to `'en'` (international default) when no match is found,
 * rather than the app-internal `defaultLocale` ('zh').
 */
export function negotiateLocale(
  acceptLanguage: string | null | undefined,
  supported: readonly string[] = locales,
): Locale {
  if (!acceptLanguage) {
    return 'en' as Locale;
  }

  const entries = acceptLanguage
    .split(',')
    .map((part) => {
      const [tag, ...params] = part.trim().split(';');
      const qParam = params.find((p) => p.trim().startsWith('q='));
      const q = qParam ? parseFloat(qParam.trim().slice(2)) : 1.0;
      return { tag: tag.trim().toLowerCase(), q: Number.isFinite(q) ? q : 0 };
    })
    .sort((a, b) => b.q - a.q);

  for (const { tag } of entries) {
    if (tag === '*') {
      continue;
    }

    const exact = supported.find((s) => s.toLowerCase() === tag);
    if (exact) {
      return exact as Locale;
    }

    const prefix = tag.split('-')[0];
    const prefixMatch = supported.find((s) => s.toLowerCase() === prefix);
    if (prefixMatch) {
      return prefixMatch as Locale;
    }

    const regionMatch = supported.find((s) => s.toLowerCase().startsWith(prefix + '-'));
    if (regionMatch) {
      return regionMatch as Locale;
    }
  }

  return 'en' as Locale;
}
