'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { setLocale } from '@/i18n';
import { useLocale } from 'next-intl';
import { type Locale } from '@/i18n/config';
import { persistLocaleToPersonalSettings } from '@/lib/locale-personal-sync';

/**
 * 语言切换组件
 */
const LanguageSwitcher = () => {
  const t = useTranslations('settings');
  const locale = useLocale();

  /**
   * 处理语言切换
   * @param newLocale - 目标语言
   */
  const handleLanguageChange = async (newLocale: Locale) => {
    setLocale(newLocale);
    await persistLocaleToPersonalSettings(newLocale);
  };

  return (
    <div className="flex flex-row space-x-2">
      <button
        onClick={() => handleLanguageChange('zh')}
        className={cn(
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          locale === 'zh'
            ? 'bg-primary text-white'
            : 'bg-secondary hover:bg-muted dark:hover:bg-muted text-black/70 dark:text-white/70',
        )}
      >
        {t('languageOptions.chinese')}
      </button>
      <button
        onClick={() => handleLanguageChange('en')}
        className={cn(
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          locale === 'en'
            ? 'bg-primary text-white'
            : 'bg-secondary hover:bg-muted dark:hover:bg-muted text-black/70 dark:text-white/70',
        )}
      >
        {t('languageOptions.english')}
      </button>
    </div>
  );
};

export default LanguageSwitcher;
