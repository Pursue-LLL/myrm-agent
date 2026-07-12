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
  selectedAgentId: string | undefined;
  onSelectAgent: (id: string | undefined) => void;
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
  selectedAgentId,
  onSelectAgent,
  lastChatUrl,
  lastWorkUrl,
  lastProjectsUrl,
  currentPathname,
}: MobileSidebarDrawerProps) {
  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
          onClick={onClose}
        />
      )}
      <div
        className={cn(
          'fixed top-0 left-0 bottom-0 z-50 flex w-full max-w-[420px] overflow-hidden pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]',
          'transform transition-transform duration-300 ease-out',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <NavBar
          activeTab={activeTab}
          onTabChange={(tab) => {
            onTabChange(tab);
            if (tab !== 'chat') onClose();
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
          <ContentSidebar
            activeTab={activeTab}
            isCollapsed={false}
            onToggleCollapse={onClose}
            navbarWidth={0}
            selectedAgentId={selectedAgentId}
            onSelectAgent={(id) => {
              onSelectAgent(id);
              onClose();
            }}
            isMobile
          />
        )}
      </div>
    </>
  );
}
