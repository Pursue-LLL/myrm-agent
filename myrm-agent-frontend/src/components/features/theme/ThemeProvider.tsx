'use client';
import { ThemeProvider, useTheme } from 'next-themes';
import { useEffect } from 'react';
import { FONT_STORAGE_KEY, type FontId, getFontStack, ensureFontLoaded } from '@/lib/fonts';

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

    const fontId = localStorage.getItem(FONT_STORAGE_KEY) as FontId | null;
    if (fontId && fontId !== 'inter') {
      ensureFontLoaded(fontId);
      document.documentElement.style.setProperty('--font-override', getFontStack(fontId));
      document.documentElement.setAttribute('data-font', fontId);
    }
  }, []);

  return null;
};

const ThemeProviderComponent = ({ children }: { children: React.ReactNode }) => {
  return (
    <ThemeProvider attribute="class" enableSystem={false} defaultTheme="dark">
      <ThemeColorMeta />
      {children}
    </ThemeProvider>
  );
};

export default ThemeProviderComponent;
