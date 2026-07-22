'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { setLocale } from '@/i18n';
import { useLocale } from 'next-intl';
import { type Locale, locales } from '@/i18n/config';
import { persistLocaleToPersonalSettings } from '@/lib/locale-personal-sync';

const localeKeyMap: Record<Locale, string> = {
  zh: 'chinese',
  'zh-TW': 'chineseTraditional',
  en: 'english',
  ja: 'japanese',
  ko: 'korean',
  de: 'german',
};

const LanguageSwitcher = () => {
  const t = useTranslations('settings');
  const locale = useLocale();

  const handleLanguageChange = async (newLocale: Locale) => {
    setLocale(newLocale);
    await persistLocaleToPersonalSettings(newLocale);
  };

  return (
    <div className="flex flex-row flex-wrap gap-2">
      {locales.map((loc) => (
        <button
          key={loc}
          onClick={() => handleLanguageChange(loc)}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            locale === loc
              ? 'bg-primary text-white'
              : 'bg-secondary hover:bg-muted dark:hover:bg-muted text-black/70 dark:text-white/70',
          )}
        >
          {t(`languageOptions.${localeKeyMap[loc]}`)}
        </button>
      ))}
    </div>
  );
};

export default LanguageSwitcher;
