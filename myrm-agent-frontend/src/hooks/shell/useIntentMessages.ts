/**
 * [INPUT]
 * - next-intl::useTranslations (POS: i18n message access)
 * - `@/lib/intent-dispatcher`::IntentMessages (POS: user-facing copy contract of the UIP dispatcher)
 *
 * [OUTPUT]
 * - useIntentMessages: localized IntentMessages bound to the active UI locale
 *
 * [POS]
 * Supplies deep-link entry points (Tauri listener, web /intent page) with the copy the dispatcher shows.
 */

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import type { IntentMessages } from '@/lib/intent-dispatcher';

export function useIntentMessages(): IntentMessages {
  const t = useTranslations('intentDispatcher');
  const tServer = useTranslations('settings.system.serverConnection');
  return useMemo(
    () => ({
      invalidLink: t('invalidLink'),
      oauthSuccess: t('oauthSuccess'),
      oauthFailed: t('oauthFailed'),
      cloudProfileName: tServer('cloudProfileName'),
    }),
    [t, tServer],
  );
}
