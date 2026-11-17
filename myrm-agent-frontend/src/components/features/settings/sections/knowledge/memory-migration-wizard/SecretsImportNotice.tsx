import type { SecretSkipReason, SecretsImportResponse } from '@/services/migrationDiscovery';

import type { TranslationFn } from './wizardShared';

/**
 * What the opt-in key import did, on the wizard's result step: how many keys it brought and, by variable name,
 * the ones it left alone and what to do about each group. Values never reach the page.
 */
export function SecretsImportNotice({ result, t }: { result: SecretsImportResponse | null; t: TranslationFn }) {
  if (!result) {
    return null;
  }

  const namesLeftAlone = (reason: SecretSkipReason) =>
    result.skipped_keys
      .filter((key) => key.reason === reason)
      .map((key) => key.name)
      .join(', ');
  const needsEndpoint = namesLeftAlone('needs_endpoint');
  const unsupported = namesLeftAlone('unsupported');

  return (
    <>
      {result.imported_keys.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {t('secretsImportSuccess', { count: result.imported_keys.length })}
        </p>
      )}
      {needsEndpoint && (
        <p className="break-words text-sm text-amber-600 dark:text-amber-400">
          {t('result.secretsNeedEndpoint', { names: needsEndpoint })}
        </p>
      )}
      {unsupported && (
        <p className="break-words text-sm text-amber-600 dark:text-amber-400">
          {t('result.secretsUnsupported', { names: unsupported })}
        </p>
      )}
    </>
  );
}
