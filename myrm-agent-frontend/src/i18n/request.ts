import { getRequestConfig } from 'next-intl/server';

import type { Locale } from './config';
import { getLocale } from './index';
import { loadShellMessages } from './load-messages';
import { getDefaultTimezone } from './timezone';

export default getRequestConfig(async () => {
  const locale = (await getLocale()) as Locale;
  const messages = await loadShellMessages(locale);

  return {
    locale,
    messages,
    timeZone: getDefaultTimezone(),
  };
});
