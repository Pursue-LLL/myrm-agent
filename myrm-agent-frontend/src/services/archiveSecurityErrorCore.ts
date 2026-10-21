/**
 * [INPUT] skills batch import API error detail payload
 * [OUTPUT] normalized error detail + archive_security i18n key resolution
 * [POS] Pure helpers for stable archive_security error_code handling in frontend.
 */

interface ApiErrorDetailObject {
  message?: unknown;
  error_code?: unknown;
  detail?: unknown;
}

export interface ResolvedApiErrorDetail {
  message: string;
  errorCode: string;
}

export const ARCHIVE_SECURITY_I18N_KEYS = {
  'archive_security.entry_limit_exceeded': 'batchImport.errors.archiveSecurity.entryLimitExceeded',
  'archive_security.total_size_exceeded': 'batchImport.errors.archiveSecurity.totalSizeExceeded',
  'archive_security.compression_ratio_exceeded': 'batchImport.errors.archiveSecurity.compressionRatioExceeded',
  'archive_security.executable_binary_detected': 'batchImport.errors.archiveSecurity.executableBinaryDetected',
} as const;

export type ArchiveSecurityErrorCode = keyof typeof ARCHIVE_SECURITY_I18N_KEYS;

export function resolveApiErrorDetail(detail: unknown, fallbackMessage: string): ResolvedApiErrorDetail {
  if (typeof detail === 'string' && detail.trim().length > 0) {
    return { message: detail, errorCode: '' };
  }

  if (detail !== null && typeof detail === 'object') {
    const payload = detail as ApiErrorDetailObject;
    const message =
      typeof payload.message === 'string' && payload.message.trim().length > 0
        ? payload.message
        : typeof payload.detail === 'string' && payload.detail.trim().length > 0
          ? payload.detail
          : fallbackMessage;
    const errorCode = typeof payload.error_code === 'string' ? payload.error_code : '';
    return { message, errorCode };
  }

  return { message: fallbackMessage, errorCode: '' };
}

export function resolveArchiveSecurityErrorI18nKey(errorCode: string): string | undefined {
  if (!Object.prototype.hasOwnProperty.call(ARCHIVE_SECURITY_I18N_KEYS, errorCode)) {
    return undefined;
  }
  return ARCHIVE_SECURITY_I18N_KEYS[errorCode as ArchiveSecurityErrorCode];
}

export function resolveUserFacingArchiveSecurityError(
  detail: unknown,
  fallbackMessage: string,
  translate: (translationKey: string) => string,
): string {
  const resolved = resolveApiErrorDetail(detail, fallbackMessage);
  const i18nKey = resolveArchiveSecurityErrorI18nKey(resolved.errorCode);
  if (!i18nKey) {
    return resolved.message;
  }
  const translated = translate(i18nKey);
  if (translated === i18nKey) {
    return resolved.message;
  }
  return translated;
}
