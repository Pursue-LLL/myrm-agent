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
import { getLocale, getMessages } from 'next-intl/server';
import type { ReactNode } from 'react';

import type { Locale } from '@/i18n/config';
import ClientIntlProvider from '@/i18n/ClientIntlProvider';
import DocumentLang from '@/i18n/DocumentLang';
import type { Messages } from '@/i18n/locale-manifest';
import PageLayout from '@/components/layout/PageLayout';
import { TooltipProvider } from '@/components/primitives/tooltip';
import ThemeProvider from '@/components/features/theme/ThemeProvider';
import ThemeProfileProvider from '@/components/features/theme/ThemeProfileProvider';
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
import ExternalLinkConfirmDialog from '@/components/features/app-shell/external-link-confirm-dialog';
import ExternalLinkInitializer from '@/components/features/app-shell/external-link-initializer';
import DeferredAppInitializers from '@/components/features/app-shell/deferred-app-initializers';
import { DesignerEyeOverlay } from '@/components/features/designer-eye';
import { SystemAssistantTrigger } from '@/components/features/system-assistant';
import { WorkspaceLayoutBar } from '@/components/features/workspace-layout';
import { DevPortsBar, DevPortSplitPreviewer } from '@/components/features/dev-ports';
import { ToolPickerTrigger } from '@/components/features/tool-picker';
import { PresentationTrigger } from '@/components/features/presentation';
import { InteractiveSpreadsheetViewer } from '@/components/features/spreadsheet';
import { SessionMapTrigger } from '@/components/features/session-map';
import { WorkbenchToggleTrigger, MultiTabWorkbench } from '@/components/features/workbench';

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
          <ThemeProfileProvider>
            <TooltipProvider delayDuration={300} skipDelayDuration={100}>
              <ClientIntlProvider locale={locale as Locale} shellMessages={messages as Messages}>
                <ToastServiceInitializer />
                <AuthInitializer />
                <SettingsSyncInitializer />
                <GlobalEventsInitializer />
                <DeepLinkListener />
                <ExternalLinkInitializer />
                <ExternalLinkConfirmDialog />
                <SystemStatusBanner />
                <QuarantineDialog />
                <VaultUnlockModal />
                <ApprovalDrawer />
                <DeferredAppInitializers />
                <PageLayout>{children}</PageLayout>
                <DesignerEyeOverlay />
                <SystemAssistantTrigger />
                <WorkspaceLayoutBar />
                <DevPortsBar />
                <DevPortSplitPreviewer />
                <ToolPickerTrigger />
                <PresentationTrigger />
                <InteractiveSpreadsheetViewer />
                <SessionMapTrigger />
                <WorkbenchToggleTrigger />
                <MultiTabWorkbench />
                <Toaster position="top-right" expand={true} richColors />
              </ClientIntlProvider>
            </TooltipProvider>
          </ThemeProfileProvider>
        </ThemeProvider>
      </GlobalErrorBoundary>
    </>
  );
}
