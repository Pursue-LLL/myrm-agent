'use client';

import { memo, type ComponentType, useCallback, useSyncExternalStore } from 'react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { Settings, Sidebar, Plug, Briefcase, FolderKanban } from 'lucide-react';
import { AiGenerativeIcon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { isRemoteGatewayActive } from '@/lib/deploy-mode';
import { useNavBadges } from '@/hooks/shell/useNavBadges';

import { NavMoreMenu } from './NavMoreMenu';
import { NavAccountMenu } from './NavAccountMenu';
import NotificationBell from '@/components/features/notifications/NotificationBell';
import BackgroundTasksPanel from '@/components/features/background-tasks/BackgroundTasksPanel';
import { IconTerminal } from '@/components/features/icons/PremiumIcons';
import { ExtensionSlot } from '@/components/features/extension-slots';
import { useTrafficLightInsets } from '@/hooks/ui/useTrafficLightInsets';

type NavIconComponent = ComponentType<{ size?: number; className?: string }>;

export type NavTab = 'chat' | 'work' | 'projects';

const NAVBAR_WIDTH = '60px';
const DEFAULT_HREFS: Record<NavTab, string> = { chat: '/', work: '/work', projects: '/projects' };

interface NavBarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  isSidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  currentPathname: string;
  isSettingsPage?: boolean;
  hideSidebarToggle?: boolean;
  isMobile?: boolean;
  onCloseMobileSidebar?: () => void;
  lastChatUrl?: string | null;
  lastWorkUrl?: string | null;
  lastProjectsUrl?: string | null;
}

function NavBarInner({
  activeTab,
  onTabChange,
  isSidebarCollapsed,
  onToggleSidebar,
  currentPathname,
  isSettingsPage = false,
  hideSidebarToggle = false,
  isMobile = false,
  onCloseMobileSidebar,
  lastChatUrl,
  lastWorkUrl,
  lastProjectsUrl,
}: NavBarProps) {
  const t = useTranslations();
  const tBackgroundTasks = useTranslations('backgroundTasks');
  const badges = useNavBadges();
  const { isImmersiveMac } = useTrafficLightInsets();
  const projectsBadgeCount = badges.cronFailures + badges.pendingApprovals;

  const closeMobileSidebar = useCallback(() => {
    if (isMobile && onCloseMobileSidebar) {
      onCloseMobileSidebar();
    }
  }, [isMobile, onCloseMobileSidebar]);

  const isOnSettingsPage = currentPathname.startsWith('/settings');
  const lastUrls: Record<NavTab, string | null | undefined> = {
    chat: lastChatUrl,
    work: lastWorkUrl,
    projects: lastProjectsUrl,
  };

  const navItems: { id: NavTab; icon: NavIconComponent; label: string }[] = [
    { id: 'chat', icon: AiGenerativeIcon, label: t('nav.chat') },
    { id: 'work', icon: Briefcase, label: t('nav.work') },
    { id: 'projects', icon: FolderKanban, label: t('nav.projects') },
  ];

  return (
    <nav
      data-theme-shell="nav"
      className={cn(
        'flex flex-col',
        'bg-background',
        'border-r border-border/50',
        'transition-all duration-300 ease-in-out',
        // 移动端使用相对定位，以便跟随父容器变换
        // 桌面端使用固定定位，窄屏在客户端判定出移动布局之前由 globals.css 先隐藏
        isMobile ? 'relative h-full' : 'wide-layout-only fixed inset-y-0 left-0 z-50',
      )}
      style={{ width: NAVBAR_WIDTH }}
    >
      {/* Header: User Avatar with Popover Menu */}
      <div className={cn('p-2 flex flex-col items-center gap-2', isImmersiveMac && !isMobile && 'pt-9')}>
        <NavAccountMenu currentPathname={currentPathname} onNavigate={closeMobileSidebar} />
      </div>

      {/* Divider */}
      <div className="mx-2 border-t border-border/50" />

      {/* Navigation Items */}
      <div className="flex-1 py-3 flex flex-col gap-1 items-center">
        {navItems.map((item) => {
          const Icon = item.icon;
          // Settings is its own destination: the Chat tab stays unlit there even though a chat is the active tab.
          const isActive = item.id === 'chat' ? !isOnSettingsPage && activeTab === 'chat' : activeTab === item.id;
          const href = lastUrls[item.id] || DEFAULT_HREFS[item.id];

          return (
            <Tooltip key={item.id}>
              <TooltipTrigger asChild>
                <Link
                  href={href}
                  onClick={() => {
                    onTabChange(item.id);
                    closeMobileSidebar();
                  }}
                  className={cn(
                    'relative w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200',
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:bg-primary/5 hover:text-accent-warm hover:shadow-brand',
                  )}
                  aria-label={item.label}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon size={18} />
                  {item.id === 'projects' && projectsBadgeCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium leading-none text-white ring-2 ring-background">
                      {projectsBadgeCount > 99 ? '99+' : projectsBadgeCount}
                    </span>
                  )}
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right">{item.label}</TooltipContent>
            </Tooltip>
          );
        })}

        {/* Everything beyond the primary destinations (monitoring pages, extension surfaces, tool panels) */}
        <NavMoreMenu
          currentPathname={currentPathname}
          extensionConnected={badges.extensionConnected}
          onNavigate={closeMobileSidebar}
        />
      </div>

      {/* Footer: Sidebar Toggle + Settings */}
      <div className="p-2 flex flex-col gap-1 items-center">
        {/* Background Tasks */}
        <BackgroundTasksPanel
          trigger={
            <button
              className="w-10 h-10 rounded-xl flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              aria-label={tBackgroundTasks('title')}
            >
              <IconTerminal className="h-[18px] w-[18px]" />
            </button>
          }
        />

        {/* Notification Bell */}
        <NotificationBell />

        {/* Show sidebar toggle button when sidebar is collapsed, not on settings page, and not hidden */}
        {isSidebarCollapsed && !isSettingsPage && !hideSidebarToggle && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onToggleSidebar}
                className="w-10 h-10 rounded-xl flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                aria-label={t('common.expandMenu')}
              >
                <Sidebar size={18} />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">{t('common.expandMenu')}</TooltipContent>
          </Tooltip>
        )}

        {/* Remote Gateway Indicator */}
        {isRemoteGatewayActive() && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link
                href="/settings/system"
                onClick={closeMobileSidebar}
                className="inline-flex items-center justify-center w-10 h-10 rounded-xl transition-transform hover:scale-105"
                aria-label={t('nav.remoteGateway')}
              >
                <Plug size={14} className="text-indigo-400" />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right">{t('nav.remoteGateway')}</TooltipContent>
          </Tooltip>
        )}

        {/* Declarative Extension Slot for bottom tools */}
        <ExtensionSlot name="navbar.bottom.tools" className="flex flex-col gap-1 items-center" />

        {/* Settings */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href="/settings"
              onClick={closeMobileSidebar}
              className={cn(
                'w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200',
                isSettingsPage
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
              aria-label={t('userMenu.settings')}
              aria-current={isSettingsPage ? 'page' : undefined}
            >
              <Settings size={18} />
            </Link>
          </TooltipTrigger>
          <TooltipContent side="right">{t('userMenu.settings')}</TooltipContent>
        </Tooltip>
      </div>
    </nav>
  );
}

// Nothing here ever changes: the snapshot is `false` on the server and while hydrating, `true` once on the client.
const subscribeToNothing = () => () => {};

// The rail depends on client-only state, so the server and the hydrating render draw nothing.
const NavBar = memo<NavBarProps>((props) => {
  const isClient = useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false,
  );

  return isClient ? <NavBarInner {...props} /> : null;
});

NavBar.displayName = 'NavBar';

export default NavBar;
