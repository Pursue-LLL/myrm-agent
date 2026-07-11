'use client';

import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { requestManager } from '@/lib/utils/requestManager';
import { checkIsMobile } from '@/lib/utils/deviceDetection';
import useAuthStore from '@/store/useAuthStore';
import NavBar, { type NavTab } from './NavBar';
import ContentSidebar from './ContentSidebar';
import { PanelLeftOpen } from 'lucide-react';
import { useTrayStatus } from '@/hooks/useTrayStatus';
import { useTabBadge } from '@/hooks/useTabBadge';
import { usePowerLock } from '@/hooks/usePowerLock';
import { useGlobalShortcuts } from '@/hooks/useGlobalShortcuts';
import { useResizableSidebar } from '@/hooks/useResizableSidebar';
import { consumeMigrationChatAgent } from '@/lib/migrationChatHandoff';

import { useVisibilityThrottling } from '@/hooks/useVisibilityThrottling';
import { useTrayEvents } from '@/hooks/useTrayEvents';

import BudgetExceededDialog from '@/components/billing/BudgetExceededDialog';
import LocalBackendUnavailableBanner, {
  ConfigReadinessDegradedBanner,
} from '@/components/features/app-shell/local-backend-unavailable-banner';

const CronPushPoller = lazy(() => import('@/components/features/cron/CronPushPoller'));

/**
 * AppLayout - 应用主布局组件
 *
 * 架构说明：
 * 1. 响应式设计：桌面端（NavBar + ContentSidebar）、移动端（滑出式侧边栏）
 * 2. 客户端检测：所有状态检测在客户端完成，更准确、更简洁
 * 3. 动态更新：监听 resize 事件，支持窗口大小调整
 *
 * 优化要点：
 * - 使用 usePathname() 获取路径（Next.js 官方 hook）
 * - 使用 window.innerWidth 检测移动端（比 User-Agent 更准确）
 * - 无需服务端传递 props，避免不必要的 SSR 开销
 */

const NAVBAR_WIDTH = 60;

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
  const pathname = usePathname();

  // 移动端状态：初始固定为 false，避免 hydration 错误
  // 注意：不能在 useState 初始化时使用 window.innerWidth，会导致 SSR/CSR 不一致
  const [isMobile, setIsMobile] = useState<boolean>(false);

  // 初始化认证状态
  useEffect(() => {
    initAuth();
  }, [initAuth]);

  // 根据路径确定当前 Tab
  const getTabFromPath = useCallback((): NavTab => {
    if (pathname === '/work' || pathname.startsWith('/work/') || pathname.startsWith('/agents') || pathname.startsWith('/agent')) {
      return 'work';
    }
    if (pathname === '/projects' || pathname.startsWith('/projects/') || pathname.startsWith('/kanban') || pathname.startsWith('/cron') || pathname.startsWith('/artifacts')) {
      return 'projects';
    }
    return 'chat';
  }, [pathname]);

  const [activeTab, setActiveTab] = useState<NavTab>(() => getTabFromPath());
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | undefined>();
  const [isNavButtonHidden, setIsNavButtonHidden] = useState(false);
  const [dismissedReadinessDegraded, setDismissedReadinessDegraded] = useState(false);

  useEffect(() => {
    if (!configReadinessDegraded) {
      setDismissedReadinessDegraded(false);
    }
  }, [configReadinessDegraded]);
  const [lastChatUrl, setLastChatUrl] = useState<string | null>(null);
  const [lastWorkUrl, setLastWorkUrl] = useState<string | null>(null);
  const [lastProjectsUrl, setLastProjectsUrl] = useState<string | null>(null);
  const lastScrollPositionRef = useRef(0);
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useTrayStatus();
  useTabBadge();
  usePowerLock();
  useVisibilityThrottling();
  useTrayEvents();
  useGlobalShortcuts();

  const handleSidebarCollapse = useCallback(() => {
    setIsSidebarCollapsed(true);
  }, []);

  const {
    width: sidebarWidth,
    isDragging: isSidebarDragging,
    handleMouseDown: handleSidebarResizeStart,
    handleDoubleClick: handleSidebarDoubleClick,
  } = useResizableSidebar({ onCollapse: handleSidebarCollapse });

  useEffect(() => {
    const pendingAgentId = consumeMigrationChatAgent();
    if (pendingAgentId) {
      setSelectedAgentId(pendingAgentId);
      setActiveTab('chat');
    }
  }, []);

  // 监听路径变化更新 Tab
  useEffect(() => {
    const newTab = getTabFromPath();
    if (newTab !== activeTab) {
      setActiveTab(newTab);
    }
  }, [pathname, getTabFromPath, activeTab]);

  useEffect(() => {
    if (pathname === '/' || pathname.match(/^\/c-/)) {
      setLastChatUrl(pathname);
    } else if (pathname === '/work' || pathname.startsWith('/work/') || pathname.startsWith('/agents') || pathname.startsWith('/agent')) {
      setLastWorkUrl(pathname);
    } else if (pathname === '/projects' || pathname.startsWith('/projects/') || pathname.startsWith('/kanban') || pathname.startsWith('/cron') || pathname.startsWith('/artifacts')) {
      setLastProjectsUrl(pathname);
    }
  }, [pathname]);

  // 响应式布局：监听窗口大小变化
  // 架构说明：
  // - 初始值固定为 false，避免 SSR/CSR 不一致
  // - mount 后立即检测一次，设置正确的初始值
  // - 监听 resize 事件动态更新
  // - 使用防抖优化性能，避免频繁更新
  useEffect(() => {
    // 初始检测（仅在 mount 时执行一次）
    const initialMobile = checkIsMobile();
    if (initialMobile !== isMobile) {
      setIsMobile(initialMobile);
      if (initialMobile) {
        setIsSidebarCollapsed(true);
      }
    }

    let resizeTimer: ReturnType<typeof setTimeout> | null = null;

    const handleResize = () => {
      // 防抖：延迟 100ms 执行，避免频繁触发
      if (resizeTimer) {
        clearTimeout(resizeTimer);
      }

      resizeTimer = setTimeout(() => {
        const mobile = checkIsMobile();
        if (mobile !== isMobile) {
          setIsMobile(mobile);
          // 切换到移动端时自动折叠侧边栏
          if (mobile) {
            setIsSidebarCollapsed(true);
          }
        }
      }, 100);
    };

    window.addEventListener('resize', handleResize);
    return () => {
      if (resizeTimer) {
        clearTimeout(resizeTimer);
      }
      window.removeEventListener('resize', handleResize);
    };
  }, [isMobile]);

  // 组件卸载时取消请求
  useEffect(() => {
    return () => {
      requestManager.cancelAllRequests();
    };
  }, []);

  // 移动端：滚动时隐藏/显示导航按钮
  useEffect(() => {
    if (!isMobile) return;

    const handleScroll = () => {
      const currentScrollPosition = window.scrollY;
      const scrollDelta = currentScrollPosition - lastScrollPositionRef.current;

      // 向下滚动超过阈值时隐藏按钮
      if (scrollDelta > 10 && currentScrollPosition > 100) {
        setIsNavButtonHidden(true);
      }

      // 向上滚动超过阈值时显示按钮
      if (scrollDelta < -10) {
        setIsNavButtonHidden(false);
      }

      // 在顶部附近时始终显示
      if (currentScrollPosition < 50) {
        setIsNavButtonHidden(false);
      }

      // 重置定时器
      if (scrollTimerRef.current) {
        clearTimeout(scrollTimerRef.current);
      }

      // 滚动停止1.5秒后显示按钮
      scrollTimerRef.current = setTimeout(() => {
        setIsNavButtonHidden(false);
      }, 1500);

      lastScrollPositionRef.current = currentScrollPosition;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (scrollTimerRef.current) {
        clearTimeout(scrollTimerRef.current);
      }
    };
  }, [isMobile]);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const handleTabChange = useCallback((tab: NavTab) => {
    setActiveTab(tab);
  }, []);

  // 设置页面特殊处理
  const isSettingsPage = pathname.startsWith('/settings');

  const shouldShowContentSidebar = !isSettingsPage && activeTab === 'chat';

  // 移动端布局标识
  // 使用 middleware cookie 初始化后，isMobile 在 SSR 和 CSR 首次渲染时保持一致
  const showMobileLayout = isMobile;

  // 计算主内容区左边距
  // 移动端：没有左边距（导航栏和侧边栏是滑出式的）
  // 桌面端：NavBar + ContentSidebar（如果展开）
  const paddingLeft = showMobileLayout
    ? '0px'
    : !shouldShowContentSidebar
      ? `${NAVBAR_WIDTH}px`
      : isSidebarCollapsed
        ? `${NAVBAR_WIDTH}px`
        : `${NAVBAR_WIDTH + sidebarWidth}px`;

  return (
    <>
      {/* 桌面端：NavBar 始终显示 */}
      {!showMobileLayout && (
        <NavBar
          activeTab={activeTab}
          onTabChange={handleTabChange}
          isSidebarCollapsed={isSidebarCollapsed}
          onToggleSidebar={handleToggleSidebar}
          isSettingsPage={isSettingsPage}
          hideSidebarToggle={!shouldShowContentSidebar || isSidebarCollapsed}
          lastChatUrl={lastChatUrl}
          lastWorkUrl={lastWorkUrl}
          lastProjectsUrl={lastProjectsUrl}
          currentPathname={pathname}
        />
      )}

      {/* 移动端左上角侧边栏切换按钮（设置页面有自己的导航头部，不显示此按钮） */}
      {showMobileLayout && !isSettingsPage && (
        <button
          onClick={() => setIsMobileSidebarOpen(true)}
          className={cn(
            'fixed top-4 left-4 z-40 p-2 rounded-lg',
            'bg-background/80 backdrop-blur-sm',
            'border border-border/50',
            'text-muted-foreground hover:text-foreground',
            'hover:bg-muted transition-all duration-300',
            '',
            isNavButtonHidden && 'opacity-0 -translate-y-full pointer-events-none',
          )}
          aria-label={t('layout.showSidebar')}
        >
          <PanelLeftOpen size={18} />
        </button>
      )}

      {/* 桌面端：ContentSidebar - 条件渲染避免与移动端重复挂载 */}
      {shouldShowContentSidebar && !showMobileLayout && (
        <ContentSidebar
          activeTab={activeTab}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={handleToggleSidebar}
          navbarWidth={NAVBAR_WIDTH}
          selectedAgentId={selectedAgentId}
          onSelectAgent={setSelectedAgentId}
          width={sidebarWidth}
          isDragging={isSidebarDragging}
          onResizeStart={handleSidebarResizeStart}
          onResizeDoubleClick={handleSidebarDoubleClick}
        />
      )}

      {/* 移动端：滑出式 NavBar + ContentSidebar 组合 */}
      {showMobileLayout && (
        <>
          {/* 遮罩层 */}
          {isMobileSidebarOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
              onClick={() => setIsMobileSidebarOpen(false)}
            />
          )}
          {/* 滑出式面板：包含 NavBar 和 ContentSidebar */}
          <div
            className={cn(
              'fixed top-0 left-0 bottom-0 z-50 flex w-full max-w-[420px] overflow-hidden pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]',
              'transform transition-transform duration-300 ease-out',
              isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full',
            )}
          >
            {/* NavBar */}
            <NavBar
              activeTab={activeTab}
              onTabChange={(tab) => {
                handleTabChange(tab);
                if (tab !== 'chat') {
                  setIsMobileSidebarOpen(false);
                }
              }}
              isSidebarCollapsed={false}
              onToggleSidebar={() => setIsMobileSidebarOpen(false)}
              isSettingsPage={isSettingsPage}
              hideSidebarToggle
              isMobile
              onCloseMobileSidebar={() => setIsMobileSidebarOpen(false)}
              lastChatUrl={lastChatUrl}
              lastWorkUrl={lastWorkUrl}
              lastProjectsUrl={lastProjectsUrl}
              currentPathname={pathname}
            />
            {/* ContentSidebar - 仅在侧边栏打开且是聊天页面时挂载 */}
            {shouldShowContentSidebar && isMobileSidebarOpen && (
              <ContentSidebar
                activeTab={activeTab}
                isCollapsed={false}
                onToggleCollapse={() => setIsMobileSidebarOpen(false)}
                navbarWidth={0}
                selectedAgentId={selectedAgentId}
                onSelectAgent={(id) => {
                  setSelectedAgentId(id);
                  setIsMobileSidebarOpen(false);
                }}
                isMobile
              />
            )}
          </div>
        </>
      )}

      {/* 主内容区 */}
      <main
        className={cn(
          'main-content-area bg-background',
          !isSidebarDragging && 'transition-all duration-300 ease-in-out',
          isSettingsPage ? 'h-screen overflow-hidden' : 'min-h-screen',
        )}
        style={{ paddingLeft }}
      >
        <div className={cn(isSettingsPage ? 'h-full overflow-y-auto' : 'max-w-screen-lg mx-auto px-4 pt-4')}>
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
