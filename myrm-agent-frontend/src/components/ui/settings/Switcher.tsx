'use client';
import { useTheme } from 'next-themes';
import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

type Theme = 'dark' | 'light' | 'system';

const ThemeSwitcher = ({ className }: { className?: string }) => {
  const [mounted, setMounted] = useState(false);
  const t = useTranslations('settings');

  const { theme, setTheme } = useTheme();

  const isTheme = useCallback((t: Theme) => t === theme, [theme]);

  const handleThemeSwitch = (theme: Theme) => {
    setTheme(theme);
  };

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isTheme('system')) {
      const preferDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');

      const detectThemeChange = (event: MediaQueryListEvent) => {
        const theme: Theme = event.matches ? 'dark' : 'light';
        setTheme(theme);
      };

      preferDarkScheme.addEventListener('change', detectThemeChange);

      return () => {
        preferDarkScheme.removeEventListener('change', detectThemeChange);
      };
    }
  }, [isTheme, setTheme, theme]);

  // Avoid Hydration Mismatch
  if (!mounted) {
    return null;
  }

  return (
    <div className={cn('flex flex-row space-x-2', className)}>
      <button
        onClick={() => handleThemeSwitch('light')}
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
        onClick={() => handleThemeSwitch('dark')}
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
        onClick={() => handleThemeSwitch('system')}
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
