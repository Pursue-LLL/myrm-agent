import { useCallback } from 'react';
import { useTranslations } from 'next-intl';

/** Localises the English validation outcomes that `useRetrievalStore` records after an apply. */
export function useApplyMessage(): (message: string | undefined) => string | undefined {
  const t = useTranslations('settings.retrieval');

  return useCallback(
    (message) => {
      if (!message) {
        return undefined;
      }

      if (message === 'Missing required fields') {
        return t('validationMessages.missingRequiredFields');
      }
      if (message === 'Network error') {
        return t('validationMessages.networkError');
      }
      if (message === 'Validation failed') {
        return t('validationMessages.validationFailed');
      }

      // Validation successful (dimension: 1024)
      const dimensionMatch = message.match(/Validation successful \(dimension: (\d+)\)/);
      if (dimensionMatch) {
        return t('validationMessages.successWithDimension', { dimension: dimensionMatch[1] });
      }

      // Validation successful (returned 1 result / 2 results)
      const resultsMatch = message.match(/Validation successful \(returned (\d+) results?\)/);
      if (resultsMatch) {
        return t('validationMessages.successWithResults', { count: parseInt(resultsMatch[1], 10) });
      }

      // Validation failed: <reason from the service>
      const failedMatch = message.match(/Validation failed: (.+)/);
      if (failedMatch) {
        return t('validationMessages.failedWithError', { error: failedMatch[1] });
      }

      return message;
    },
    [t],
  );
}
