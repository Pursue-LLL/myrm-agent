'use client';

import { cn } from '@/lib/utils/classnameUtils';
import NavBar, { type NavTab } from './NavBar';
import ContentSidebar from './ContentSidebar';

interface MobileSidebarDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  isSettingsPage: boolean;
  shouldShowContentSidebar: boolean;
  lastChatUrl: string | null;
  lastWorkUrl: string | null;
  lastProjectsUrl: string | null;
  currentPathname: string;
}

export function MobileSidebarDrawer({
  isOpen,
  onClose,
  activeTab,
  onTabChange,
  isSettingsPage,
  shouldShowContentSidebar,
  lastChatUrl,
  lastWorkUrl,
  lastProjectsUrl,
  currentPathname,
}: MobileSidebarDrawerProps) {
  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onClose} role="presentation" />
      )}
      <div
        className={cn(
          'fixed top-0 left-0 bottom-0 z-50 flex w-full max-w-[420px] overflow-hidden myrm-safe-top myrm-safe-bottom',
          'transform transition-transform duration-300 ease-out',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <NavBar
          activeTab={activeTab}
          onTabChange={(tab) => {
            onTabChange(tab);
            if (tab !== 'chat') {
              onClose();
            }
          }}
          isSidebarCollapsed={false}
          onToggleSidebar={onClose}
          isSettingsPage={isSettingsPage}
          hideSidebarToggle
          isMobile
          onCloseMobileSidebar={onClose}
          lastChatUrl={lastChatUrl}
          lastWorkUrl={lastWorkUrl}
          lastProjectsUrl={lastProjectsUrl}
          currentPathname={currentPathname}
        />
        {shouldShowContentSidebar && isOpen && (
          <ContentSidebar isCollapsed={false} onToggleCollapse={onClose} navbarWidth={0} isMobile />
        )}
      </div>
    </>
  );
}
