'use client';

import { useState, useEffect, lazy, Suspense } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useAuthStore from '@/store/useAuthStore';
import NavBar from './NavBar';
import ContentSidebar from './ContentSidebar';
import { MobileSidebarDrawer } from './MobileSidebarDrawer';
import { NAVBAR_WIDTH, useAppLayoutState } from './useAppLayoutState';
import { PanelLeftOpen } from 'lucide-react';
import { useTrayStatus } from '@/hooks/useTrayStatus';
import { useTabBadge } from '@/hooks/useTabBadge';
import { usePowerLock } from '@/hooks/usePowerLock';
import { useGlobalShortcuts } from '@/hooks/useGlobalShortcuts';
import { useVisibilityThrottling } from '@/hooks/useVisibilityThrottling';
import { useTrayEvents } from '@/hooks/useTrayEvents';
import BudgetExceededDialog from '@/components/billing/BudgetExceededDialog';
import LocalBackendUnavailableBanner, {
  ConfigReadinessDegradedBanner,
} from '@/components/features/app-shell/local-backend-unavailable-banner';

const CronPushPoller = lazy(() =>
  import('@/components/features/cron/CronPushPoller').then((mod) => ({ default: mod.default })),
);

interface AppLayoutProps {
  children: React.ReactNode;
  configReadinessDegraded?: boolean;
  onRetryConfigReadiness?: () => void;
}

function AppLayout({
  children,
  configReadinessDegraded = false,
  onRetryConfigReadiness,
}: AppLayoutProps) {
  const { initAuth } = useAuthStore();
  const t = useTranslations();
  const [dismissedReadinessDegraded, setDismissedReadinessDegraded] = useState(false);

  const layout = useAppLayoutState();

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  useEffect(() => {
    if (!configReadinessDegraded) {
      setDismissedReadinessDegraded(false);
    }
  }, [configReadinessDegraded]);

  useTrayStatus();
  useTabBadge();
  usePowerLock();
  useVisibilityThrottling();
  useTrayEvents();
  useGlobalShortcuts();

  return (
    <>
      {!layout.showMobileLayout && (
        <NavBar
          activeTab={layout.activeTab}
          onTabChange={layout.handleTabChange}
          isSidebarCollapsed={layout.isSidebarCollapsed}
          onToggleSidebar={layout.handleToggleSidebar}
          isSettingsPage={layout.isSettingsPage}
          hideSidebarToggle={!layout.shouldShowContentSidebar || layout.isSidebarCollapsed}
          lastChatUrl={layout.lastChatUrl}
          lastWorkUrl={layout.lastWorkUrl}
          lastProjectsUrl={layout.lastProjectsUrl}
          currentPathname={layout.pathname}
        />
      )}

      {layout.showMobileLayout && !layout.isSettingsPage && (
        <button
          onClick={() => layout.setIsMobileSidebarOpen(true)}
          className={cn(
            'fixed top-4 left-4 z-40 p-2 rounded-lg',
            'bg-background/80 backdrop-blur-sm',
            'border border-border/50',
            'text-muted-foreground hover:text-foreground',
            'hover:bg-muted transition-all duration-300',
            layout.isNavButtonHidden && 'opacity-0 -translate-y-full pointer-events-none',
          )}
          aria-label={t('layout.showSidebar')}
        >
          <PanelLeftOpen size={18} />
        </button>
      )}

      {layout.shouldShowContentSidebar && !layout.showMobileLayout && (
        <ContentSidebar
          activeTab={layout.activeTab}
          isCollapsed={layout.isSidebarCollapsed}
          onToggleCollapse={layout.handleToggleSidebar}
          navbarWidth={NAVBAR_WIDTH}
          selectedAgentId={layout.selectedAgentId}
          onSelectAgent={layout.setSelectedAgentId}
          width={layout.sidebarWidth}
          isDragging={layout.isSidebarDragging}
          onResizeStart={layout.handleSidebarResizeStart}
          onResizeDoubleClick={layout.handleSidebarDoubleClick}
        />
      )}

      {layout.showMobileLayout && (
        <MobileSidebarDrawer
          isOpen={layout.isMobileSidebarOpen}
          onClose={() => layout.setIsMobileSidebarOpen(false)}
          activeTab={layout.activeTab}
          onTabChange={layout.handleTabChange}
          isSettingsPage={layout.isSettingsPage}
          shouldShowContentSidebar={layout.shouldShowContentSidebar}
          selectedAgentId={layout.selectedAgentId}
          onSelectAgent={layout.setSelectedAgentId}
          lastChatUrl={layout.lastChatUrl}
          lastWorkUrl={layout.lastWorkUrl}
          lastProjectsUrl={layout.lastProjectsUrl}
          currentPathname={layout.pathname}
        />
      )}

      <main
        data-testid="app-layout"
        className={cn(
          'main-content-area bg-background',
          !layout.isSidebarDragging && 'transition-all duration-300 ease-in-out',
          layout.isSettingsPage ? 'h-screen overflow-hidden' : 'min-h-screen',
        )}
        style={{ paddingLeft: layout.paddingLeft }}
      >
        <div
          className={cn(
            layout.isSettingsPage ? 'h-full overflow-y-auto' : 'max-w-screen-lg mx-auto px-4 pt-4 overflow-visible',
          )}
        >
          <LocalBackendUnavailableBanner />
          <ConfigReadinessDegradedBanner
            visible={configReadinessDegraded && !dismissedReadinessDegraded}
            onRetry={onRetryConfigReadiness}
            onDismiss={() => setDismissedReadinessDegraded(true)}
          />
          {children}
        </div>
      </main>

      <Suspense fallback={null}>
        <CronPushPoller />
      </Suspense>
      <BudgetExceededDialog />
    </>
  );
}

export default AppLayout;
