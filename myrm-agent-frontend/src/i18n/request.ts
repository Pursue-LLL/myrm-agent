import { getRequestConfig } from 'next-intl/server';

import type { Locale } from './config';
import { getLocale } from './index';
import { loadShellMessages } from './load-messages';

export default getRequestConfig(async () => {
  const locale = (await getLocale()) as Locale;
  const messages = await loadShellMessages(locale);

  return {
    locale,
    messages,
  };
});
