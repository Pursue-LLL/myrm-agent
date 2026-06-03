'use client';
import { ThemeProvider, useTheme } from 'next-themes';
import { useEffect } from 'react';

const SKIN_STORAGE_KEY = 'myrm-skin';

const ThemeColorMeta = () => {
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      const color = resolvedTheme === 'dark' ? '#0a0a0a' : '#fdfdfb';
      metaThemeColor.setAttribute('content', color);
    }
  }, [resolvedTheme]);

  useEffect(() => {
    const skin = localStorage.getItem(SKIN_STORAGE_KEY);
    if (skin && skin !== 'default') {
      document.documentElement.setAttribute('data-skin', skin);
    }
  }, []);

  return null;
};

const ThemeProviderComponent = ({ children }: { children: React.ReactNode }) => {
  return (
    <ThemeProvider attribute="class" enableSystem={false} defaultTheme="light">
      <ThemeColorMeta />
      {children}
    </ThemeProvider>
  );
};

export default ThemeProviderComponent;
