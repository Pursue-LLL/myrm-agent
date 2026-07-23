/**
 * [INPUT]
 * - @/i18n/config (POS: defaultLocale 静态 html lang 占位)
 * - @/i18n/LocalizedProviders (POS: 根 i18n + 全局 initializer 树)
 *
 * [POS] Next.js 根布局：主题、国际化（DocumentLang 在 Suspense 内同步 lang）、全局初始化器、页面壳层。
 */
import type { Metadata, Viewport } from 'next';
import Script from 'next/script';
import { Suspense } from 'react';
import './globals.css';
import { defaultLocale } from '@/i18n/config';
import { LocalizedProviders } from '@/i18n/LocalizedProviders';
import { cn } from '@/lib/utils/classnameUtils';
import AppShellSkeleton from '@/components/features/app-shell/AppShellSkeleton';
import { WebVitals } from './web-vitals';
import { getBuildTimeMetadataMessages } from '@/lib/metadata/static-metadata';
import { fontSans, fontMono } from '@/lib/fonts';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

const metadataMessages = getBuildTimeMetadataMessages();

export const metadata: Metadata = {
  title: metadataMessages.appTitle,
  description: metadataMessages.appDescription,
};

export default function LocaleLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang={defaultLocale} className="min-h-full" suppressHydrationWarning>
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#fdfdfb" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
        <link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png" />
        <link rel="icon" type="image/png" sizes="64x64" href="/favicon-64.png" />
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="apple-touch-icon" href="/icons/icon-192x192.png" />
        <link rel="preload" as="image" href="/brand/brand-mark-128.webp" type="image/webp" />
      </head>
      <body
        className={cn('min-h-full', fontSans.variable, fontMono.variable)}
        suppressHydrationWarning
      >
        <Script
          id="e2e-runtime-bootstrap"
          src="/e2e-runtime-bootstrap.js"
          strategy="beforeInteractive"
        />
        <Script id="theme-pre-init" src="/theme-init.js" strategy="beforeInteractive" />
        <WebVitals />
        <Suspense fallback={<AppShellSkeleton />}>
          <LocalizedProviders>{children}</LocalizedProviders>
        </Suspense>
      </body>
    </html>
  );
}
