'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useAuthStore from '@/store/useAuthStore';
import NavBar from './NavBar';
import ContentSidebar from './ContentSidebar';
import { MobileSidebarDrawer } from './MobileSidebarDrawer';
import { NAVBAR_WIDTH, useAppLayoutState } from './useAppLayoutState';
import { PanelLeftOpen } from 'lucide-react';
import { useTrayStatus } from '@/hooks/tauri/useTrayStatus';
import { useTabBadge } from '@/hooks/shell/useTabBadge';
import { useDesktopWakeRecovery } from '@/hooks/tauri/useDesktopWakeRecovery';
import { useConnectionsChangedReload } from '@/hooks/tauri/useConnectionsChangedReload';
import { useGlobalShortcuts } from '@/hooks/shell/useGlobalShortcuts';
import { useComputerUseEscapeAbort } from '@/hooks/shell/useComputerUseEscapeAbort';
import { useVisibilityThrottling } from '@/hooks/ui/useVisibilityThrottling';
import { useTrayEvents } from '@/hooks/tauri/useTrayEvents';
import { useCurtainTexts } from '@/hooks/tauri/useCurtainTexts';
import { useCrashLoopGuard } from '@/hooks/shell/useCrashLoopGuard';
import BudgetExceededDialog from '@/components/billing/BudgetExceededDialog';
import UpgradeNudgeDialog from '@/components/billing/UpgradeNudgeDialog';
import CrashRecoveryDialog from '@/components/features/app-shell/crash-recovery-dialog';
import LocalBackendUnavailableBanner, {
  ConfigReadinessDegradedBanner,
} from '@/components/features/app-shell/local-backend-unavailable-banner';
import CronSchedulerHealthBanner from '@/components/features/app-shell/cron-scheduler-health-banner';
import ConfigUnreadableBanner from '@/components/features/app-shell/config-unreadable-banner';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { useProgressionStore } from '@/store/useProgressionStore';
import { useWuBalanceWatcher } from '@/hooks/billing/useWuBalanceWatcher';
import { useExtensionWebUiOriginSeed } from '@/hooks/extension/useExtensionWebUiOriginSeed';
import { scheduleWhenIdle } from '@/lib/utils/scheduleWhenIdle';
import E2ECompanionBridge from '@/components/dev/E2ECompanionBridge';

interface AppLayoutProps {
  children: React.ReactNode;
  configReadinessDegraded?: boolean;
  onRetryConfigReadiness?: () => void;
}

interface PageKind {
  isSettingsPage: boolean;
  isResearchPage: boolean;
  isRemoteSurface: boolean;
}

// How the shell frames a page: the height policy of `<main>` and the box the page (and the banners above it) sits in.
// - Settings and the research workbench own their scrolling, so `<main>` is pinned to the viewport. The workbench uses
//   the dynamic viewport so its composer stays above a mobile browser's toolbar.
// - The paired-phone surface fills the viewport itself (own status bar, safe-area handling and full-height boards), so
//   the frame must not add padding on top of that or the screen gains a phantom scroll. On a wide desktop browser it is
//   still capped to the page width instead of stretching across the monitor.
// - Every other page is a centred column.
function pageFrame({ isSettingsPage, isResearchPage, isRemoteSurface }: PageKind): { main: string; content: string } {
  if (isSettingsPage) {
    return { main: 'h-screen overflow-hidden', content: 'h-full overflow-y-auto' };
  }
  if (isResearchPage) {
    return { main: 'h-dvh overflow-hidden', content: 'flex h-full flex-col overflow-hidden' };
  }
  if (isRemoteSurface) {
    return { main: 'min-h-screen', content: 'lg:max-w-screen-lg lg:mx-auto' };
  }
  return { main: 'min-h-screen', content: 'max-w-screen-lg mx-auto px-4 pt-4 overflow-visible' };
}

function AppLayout({ children, configReadinessDegraded = false, onRetryConfigReadiness }: AppLayoutProps) {
  const { initAuth } = useAuthStore();
  const t = useTranslations('layout');
  const [dismissedReadinessDegraded, setDismissedReadinessDegraded] = useState(false);

  const layout = useAppLayoutState();

  useExtensionWebUiOriginSeed();

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  useEffect(
    () =>
      scheduleWhenIdle(() => {
        void useFeatureGateStore.getState().loadFeatures();
        void useProgressionStore.getState().load();
      }),
    [],
  );

  // 就绪降级一旦恢复，之前的“已关闭”就作废：下一次降级要重新提示。
  if (!configReadinessDegraded && dismissedReadinessDegraded) {
    setDismissedReadinessDegraded(false);
  }

  useTrayStatus();
  useTabBadge();
  useDesktopWakeRecovery();
  useConnectionsChangedReload();
  useVisibilityThrottling();
  useTrayEvents();
  useCurtainTexts();
  useGlobalShortcuts();
  useComputerUseEscapeAbort();
  useWuBalanceWatcher();
  const { crashLoopActive, errorMessage: crashError, dismiss: dismissCrashLoop } = useCrashLoopGuard();

  const frame = pageFrame(layout);

  return (
    <>
      <CrashRecoveryDialog visible={crashLoopActive} errorMessage={crashError} onDismiss={dismissCrashLoop} />
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

      {layout.showMobileLayout && !layout.isSettingsPage && !layout.isRemoteSurface && (
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
          aria-label={t('showSidebar')}
        >
          <PanelLeftOpen size={18} />
        </button>
      )}

      {layout.shouldShowContentSidebar && !layout.showMobileLayout && (
        <ContentSidebar
          isCollapsed={layout.isSidebarCollapsed}
          onToggleCollapse={layout.handleToggleSidebar}
          navbarWidth={NAVBAR_WIDTH}
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
          lastChatUrl={layout.lastChatUrl}
          lastWorkUrl={layout.lastWorkUrl}
          lastProjectsUrl={layout.lastProjectsUrl}
          currentPathname={layout.pathname}
        />
      )}

      <main
        data-theme-shell="main"
        data-testid="app-layout"
        className={cn(
          'main-content-area bg-background',
          !layout.isSidebarDragging && 'transition-all duration-300 ease-in-out',
          frame.main,
        )}
        style={{ paddingLeft: layout.paddingLeft }}
      >
        <div className={frame.content}>
          <LocalBackendUnavailableBanner />
          <CronSchedulerHealthBanner />
          <ConfigUnreadableBanner />
          <ConfigReadinessDegradedBanner
            visible={configReadinessDegraded && !dismissedReadinessDegraded}
            onRetry={onRetryConfigReadiness}
            onDismiss={() => setDismissedReadinessDegraded(true)}
          />
          {children}
        </div>
      </main>

      <BudgetExceededDialog />
      <UpgradeNudgeDialog />
      <E2ECompanionBridge />
    </>
  );
}

export default AppLayout;
