/**
 * [POS]
 * Locale domain facade. Explicit re-export list is the compiler-enforced
 * public surface: adding an export inside the package without listing it
 * here leaves it package-private (typecheck breaks consumer imports instead
 * of silently leaking symbols).
 */
export { localizeReactNode, selectLocalizedText } from './localeText';
export {
  getClientLocale,
  negotiateLocale,
  NEXT_LOCALE_COOKIE_NAME,
  normalizeLocaleForBackend,
  parseLocaleQueryParam,
  urlWithoutLocaleParam,
} from './localeUtils';
