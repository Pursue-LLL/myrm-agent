/**
 * [POS] Next.js 根布局：主题、国际化、全局初始化器、页面壳层。
 */
import type { Metadata, Viewport } from 'next';
import './globals.css';
import { NextIntlClientProvider } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { PageLayout } from '@/components/layout';
import { TooltipProvider } from '@/components/primitives/tooltip';
import ThemeProvider from '@/components/features/theme/ThemeProvider';
import ToastServiceInitializer from '@/components/features/app-shell/toast-service-initializer';
import SettingsSyncInitializer from '@/components/features/app-shell/settings-sync-initializer';
import AuthInitializer from '@/components/features/app-shell/auth-initializer';
import GlobalEventsInitializer from '@/components/features/app-shell/global-events-initializer';
import SystemStatusBanner from '@/components/features/app-shell/SystemStatusBanner';
import { Toaster } from '@/components/primitives/sonner';
import { GlobalErrorBoundary } from '@/components/error-boundary';
import { QuarantineDialog } from '@/components/features/app-shell/QuarantineDialog';
import { VaultUnlockModal } from '@/components/features/app-shell/VaultUnlockModal';
import { ApprovalDrawer } from '@/components/approval/ApprovalDrawer';
import DeepLinkListener from '@/components/features/app-shell/deep-link-listener';
import { FlowPadModal } from '@/components/features/app-shell/flow-pad-modal';
import { PWAUpdater } from '@/components/features/app-shell/pwa-updater';
import { AppUpdatePrompt } from '@/components/features/app-shell/app-update-prompt';
import AppshotInitializer from '@/components/features/app-shell/appshot-initializer';
import VoicePttInitializer from '@/components/features/app-shell/voice-ptt-initializer';
import { WebVitals } from './web-vitals';
import { getLocale, getMessages } from 'next-intl/server';
import { getTranslations } from 'next-intl/server';
import { fontSans, fontMono } from '@/lib/fonts';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

export async function generateMetadata(props: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const params = await props.params;
  const { locale } = params;

  const t = await getTranslations({ locale, namespace: 'metadata' });

  return {
    title: t('appTitle'),
    description: t('appDescription'),
  };
}

export default async function LocaleLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} className="min-h-full" suppressHydrationWarning>
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#fdfdfb" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                var d=document.documentElement;
                var theme=localStorage.getItem('theme');
                var isDark=theme==='dark';
                var meta=document.querySelector('meta[name="theme-color"]');
                if(meta)meta.setAttribute('content',isDark?'#0a0a0a':'#fdfdfb');
                var skin=localStorage.getItem('myrm-skin');
                if(skin&&skin!=='default')d.setAttribute('data-skin',skin);
                var font=localStorage.getItem('myrm-font');
                if(font&&font!=='inter')d.setAttribute('data-font',font);
              } catch(e){}
            `,
          }}
        />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <link rel="apple-touch-icon" href="/icons/icon-192x192.png" />
        {/* next/font self-hosts woff2 — no external preconnect needed */}
        <link rel="preload" as="image" href="/brand/logo-icon.webp" type="image/webp" />
      </head>
      <body className={cn('min-h-full', fontSans.variable, fontMono.variable)}>
        <GlobalErrorBoundary>
          <WebVitals />
          <ThemeProvider>
            <TooltipProvider delayDuration={300} skipDelayDuration={100}>
              <NextIntlClientProvider messages={messages} locale={locale}>
                <ToastServiceInitializer />
                <AuthInitializer />
                <SettingsSyncInitializer />
                <GlobalEventsInitializer />
                <DeepLinkListener />
                <SystemStatusBanner />
                <QuarantineDialog />
                <VaultUnlockModal />
                <ApprovalDrawer />
                <FlowPadModal />
                <PWAUpdater />
                <AppUpdatePrompt />
                <AppshotInitializer />
                <VoicePttInitializer />
                <PageLayout>{children}</PageLayout>
                <Toaster position="top-right" expand={true} richColors />
              </NextIntlClientProvider>
            </TooltipProvider>
          </ThemeProvider>
        </GlobalErrorBoundary>
      </body>
    </html>
  );
}
