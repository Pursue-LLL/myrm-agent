'use client';
import { ThemeProvider, useTheme } from 'next-themes';
import { useEffect } from 'react';

const ThemeColorMeta = () => {
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      const color = resolvedTheme === 'dark' ? '#0a0a0a' : '#fdfdfb';
      metaThemeColor.setAttribute('content', color);
    }
  }, [resolvedTheme]);

  return null;
};

const nextThemesScriptProps =
  typeof window === 'undefined' ? undefined : ({ type: 'application/json' } as const);

const ThemeProviderComponent = ({ children }: { children: React.ReactNode }) => {
  return (
    <ThemeProvider
      attribute="class"
      enableSystem
      defaultTheme="dark"
      scriptProps={nextThemesScriptProps}
    >
      <ThemeColorMeta />
      {children}
    </ThemeProvider>
  );
};

export default ThemeProviderComponent;
