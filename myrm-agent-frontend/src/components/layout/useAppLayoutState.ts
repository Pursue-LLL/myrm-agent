'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { checkIsMobile } from '@/lib/utils/deviceDetection';
import { requestManager } from '@/lib/utils/requestManager';
import { consumeMigrationChatAgent } from '@/lib/migrationChatHandoff';
import { useResizableSidebar } from '@/hooks/useResizableSidebar';
import type { NavTab } from './NavBar';

export const NAVBAR_WIDTH = 60;

function getTabFromPathname(pathname: string): NavTab {
  if (
    pathname === '/work' ||
    pathname.startsWith('/work/') ||
    pathname.startsWith('/agents') ||
    pathname.startsWith('/agent')
  ) {
    return 'work';
  }
  if (
    pathname === '/projects' ||
    pathname.startsWith('/projects/') ||
    pathname.startsWith('/kanban') ||
    pathname.startsWith('/cron') ||
    pathname.startsWith('/artifacts')
  ) {
    return 'projects';
  }
  return 'chat';
}

export function useAppLayoutState() {
  const pathname = usePathname();

  const [isMobile, setIsMobile] = useState(false);
  const [activeTab, setActiveTab] = useState<NavTab>(() => getTabFromPathname(pathname));
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | undefined>();
  const [isNavButtonHidden, setIsNavButtonHidden] = useState(false);
  const [lastChatUrl, setLastChatUrl] = useState<string | null>(null);
  const [lastWorkUrl, setLastWorkUrl] = useState<string | null>(null);
  const [lastProjectsUrl, setLastProjectsUrl] = useState<string | null>(null);
  const lastScrollPositionRef = useRef(0);
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  useEffect(() => {
    const newTab = getTabFromPathname(pathname);
    setActiveTab((prev) => (prev !== newTab ? newTab : prev));
  }, [pathname]);

  useEffect(() => {
    if (pathname === '/' || pathname.match(/^\/c-/)) {
      setLastChatUrl(pathname);
    } else if (
      pathname === '/work' ||
      pathname.startsWith('/work/') ||
      pathname.startsWith('/agents') ||
      pathname.startsWith('/agent')
    ) {
      setLastWorkUrl(pathname);
    } else if (
      pathname === '/projects' ||
      pathname.startsWith('/projects/') ||
      pathname.startsWith('/kanban') ||
      pathname.startsWith('/cron') ||
      pathname.startsWith('/artifacts')
    ) {
      setLastProjectsUrl(pathname);
    }
  }, [pathname]);

  useEffect(() => {
    const initialMobile = checkIsMobile();
    if (initialMobile !== isMobile) {
      setIsMobile(initialMobile);
      if (initialMobile) {
        setIsSidebarCollapsed(true);
      }
    }

    let resizeTimer: ReturnType<typeof setTimeout> | null = null;
    const handleResize = () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const mobile = checkIsMobile();
        if (mobile !== isMobile) {
          setIsMobile(mobile);
          if (mobile) {
            setIsSidebarCollapsed(true);
          }
        }
      }, 100);
    };

    window.addEventListener('resize', handleResize);
    return () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      window.removeEventListener('resize', handleResize);
    };
  }, [isMobile]);

  useEffect(() => () => requestManager.cancelAllRequests(), []);

  useEffect(() => {
    if (!isMobile) return;

    const handleScroll = () => {
      const currentScrollPosition = window.scrollY;
      const scrollDelta = currentScrollPosition - lastScrollPositionRef.current;

      if (scrollDelta > 10 && currentScrollPosition > 100) {
        setIsNavButtonHidden(true);
      }
      if (scrollDelta < -10) setIsNavButtonHidden(false);
      if (currentScrollPosition < 50) setIsNavButtonHidden(false);

      if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
      scrollTimerRef.current = setTimeout(() => setIsNavButtonHidden(false), 1500);
      lastScrollPositionRef.current = currentScrollPosition;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
    };
  }, [isMobile]);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const handleTabChange = useCallback((tab: NavTab) => {
    setActiveTab(tab);
  }, []);

  const isSettingsPage = pathname.startsWith('/settings');
  const shouldShowContentSidebar = !isSettingsPage && activeTab === 'chat';
  const showMobileLayout = isMobile;
  const paddingLeft = showMobileLayout
    ? '0px'
    : !shouldShowContentSidebar
      ? `${NAVBAR_WIDTH}px`
      : isSidebarCollapsed
        ? `${NAVBAR_WIDTH}px`
        : `${NAVBAR_WIDTH + sidebarWidth}px`;

  return {
    pathname,
    activeTab,
    isSidebarCollapsed,
    isMobileSidebarOpen,
    setIsMobileSidebarOpen,
    selectedAgentId,
    setSelectedAgentId,
    isNavButtonHidden,
    lastChatUrl,
    lastWorkUrl,
    lastProjectsUrl,
    sidebarWidth,
    isSidebarDragging,
    handleSidebarResizeStart,
    handleSidebarDoubleClick,
    handleToggleSidebar,
    handleTabChange,
    isSettingsPage,
    shouldShowContentSidebar,
    showMobileLayout,
    paddingLeft,
  };
}
