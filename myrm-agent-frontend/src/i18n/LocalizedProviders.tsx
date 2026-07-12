/**
 * [INPUT]
 * next-intl/server::getLocale, getMessages (POS: Server Component locale 解析)
 * @/components/layout/PageLayout (POS: 根 layout 客户端入口，shell-first)
 *
 * [OUTPUT]
 * LocalizedProviders: Suspense-bound locale/messages provider tree for the app shell.
 *
 * [POS]
 * Root i18n provider assembly. Reads cookie locale inside Suspense so cacheComponents builds stay instant-safe.
 */
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import type { ReactNode } from 'react';

import DocumentLang from '@/i18n/DocumentLang';
import PageLayout from '@/components/layout/PageLayout';
import { TooltipProvider } from '@/components/primitives/tooltip';
import ThemeProvider from '@/components/features/theme/ThemeProvider';
import ToastServiceInitializer from '@/components/features/app-shell/toast-service-initializer';
import SettingsSyncInitializer from '@/components/features/app-shell/settings-sync-initializer';
import AuthInitializer from '@/components/features/app-shell/auth-initializer';
import GlobalEventsInitializer from '@/components/features/app-shell/global-events-initializer';
import SystemStatusBanner from '@/components/features/app-shell/SystemStatusBanner';
import { Toaster } from '@/components/primitives/sonner';
import { GlobalErrorBoundary } from '@/components/error-boundary/GlobalErrorBoundary';
import { QuarantineDialog } from '@/components/features/app-shell/QuarantineDialog';
import { VaultUnlockModal } from '@/components/features/app-shell/VaultUnlockModal';
import { ApprovalDrawer } from '@/components/approval/ApprovalDrawer';
import DeepLinkListener from '@/components/features/app-shell/deep-link-listener';
import { FlowPadModal } from '@/components/features/app-shell/flow-pad-modal';
import { PWAUpdater } from '@/components/features/app-shell/pwa-updater';
import { AppUpdatePrompt } from '@/components/features/app-shell/app-update-prompt';
import { WhatsNewModal } from '@/components/features/app-shell/whats-new-modal';
import AppshotInitializer from '@/components/features/app-shell/appshot-initializer';
import VoicePttInitializer from '@/components/features/app-shell/voice-ptt-initializer';

interface LocalizedProvidersProps {
  children: ReactNode;
}

export async function LocalizedProviders({ children }: LocalizedProvidersProps) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <>
      <DocumentLang locale={locale} />
      <GlobalErrorBoundary>
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
              <WhatsNewModal />
              <AppshotInitializer />
              <VoicePttInitializer />
              <PageLayout>{children}</PageLayout>
              <Toaster position="top-right" expand={true} richColors />
            </NextIntlClientProvider>
          </TooltipProvider>
        </ThemeProvider>
      </GlobalErrorBoundary>
    </>
  );
}
