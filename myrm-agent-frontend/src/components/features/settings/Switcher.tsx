'use client';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

const ThemeSwitcher = ({ className }: { className?: string }) => {
  const [mounted, setMounted] = useState(false);
  const t = useTranslations('settings');

  const { theme, setTheme } = useTheme();

  useEffect(() => {
    setMounted(true);
  }, []);

  // Avoid Hydration Mismatch
  if (!mounted) {
    return null;
  }

  return (
    <div className={cn('flex flex-row space-x-2', className)}>
      <button
        onClick={() => setTheme('light')}
        className={cn(
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          theme === 'light'
            ? 'bg-primary text-white'
            : 'bg-secondary hover:bg-muted dark:hover:bg-muted text-black/70 dark:text-white/70',
        )}
      >
        {t('themeOptions.light')}
      </button>
      <button
        onClick={() => setTheme('dark')}
        className={cn(
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          theme === 'dark'
            ? 'bg-primary text-white'
            : 'bg-secondary hover:bg-muted dark:hover:bg-muted text-black/70 dark:text-white/70',
        )}
      >
        {t('themeOptions.dark')}
      </button>
      <button
        onClick={() => setTheme('system')}
        className={cn(
          'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
          theme === 'system'
            ? 'bg-primary text-white'
            : 'bg-secondary hover:bg-muted dark:hover:bg-muted text-black/70 dark:text-white/70',
        )}
      >
        {t('themeOptions.system')}
      </button>
    </div>
  );
};

export default ThemeSwitcher;
