'use client';

import { memo, type ComponentType, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import Image from 'next/image';
import Link from 'next/link';
import {
  Settings,
  User,
  Sidebar,
  Wand2,
  Plug,
  LogOut,
  Crown,
  Zap,
  FlaskConical,
  CreditCard,
  Briefcase,
  FolderKanban,
  TrendingUp,
  Shield,
} from 'lucide-react';
import { AiGenerativeIcon, InvestigationIcon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import useAuthStore from '@/store/useAuthStore';
import useConfigStore from '@/store/useConfigStore';
import { useSubscription } from '@/hooks/useSubscription';
import { isLocalMode } from '@/lib/deploy-mode';
import { buildAuthLoginPath } from '@/lib/auth-redirect';
import { preloadMonacoEditor } from '@/lib/utils/componentPreloader';
import { useNavBadges } from '@/hooks/useNavBadges';

import NotificationBell from '@/components/features/notifications/NotificationBell';
import BackgroundTasksPanel from '@/components/features/background-tasks/BackgroundTasksPanel';
import { IconTerminal } from '@/components/features/icons/PremiumIcons';

const isDev = process.env.NODE_ENV === 'development';
type NavIconComponent = ComponentType<{ size?: number; className?: string }>;

export type NavTab = 'chat' | 'work' | 'projects';

const NAVBAR_WIDTH = '60px';

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
  const router = useRouter();
  const t = useTranslations();
  const tPricing = useTranslations('pricing');
  const tUserMenu = useTranslations('userMenu');
  const tBackgroundTasks = useTranslations('backgroundTasks');
  const { user, isLoading, logout, loginMock } = useAuthStore();
  const enableEvalLab = useConfigStore((state) => state.enableEvalLab);
  const { isPro } = useSubscription();
  const [avatarError, setAvatarError] = useState(false);
  const isLocal = isLocalMode();
  const badges = useNavBadges();
  const projectsBadgeCount = badges.cronFailures + badges.pendingApprovals;

  const closeMobileSidebar = useCallback(() => {
    if (isMobile && onCloseMobileSidebar) {
      onCloseMobileSidebar();
    }
  }, [isMobile, onCloseMobileSidebar]);

  // 快捷入口：跳转到设置页对应 tab 或独立页面
  const quickAccessItems: {
    id: string;
    icon: NavIconComponent;
    label: string;
    settingsTab?: string;
    href?: string;
  }[] = [
    { id: 'health', icon: InvestigationIcon, label: t('nav.health'), href: '/health' },
    { id: 'security-center', icon: Shield, label: t('nav.securityCenter'), href: '/security' },
    { id: 'growth', icon: TrendingUp, label: t('growthDashboard.title'), href: '/growth' },
    { id: 'skills', icon: Wand2, label: t('settings.menu.skills'), settingsTab: 'skills' },
    { id: 'mcp', icon: Plug, label: t('settings.menu.mcp'), settingsTab: 'mcp' },
    ...(enableEvalLab ? [{ id: 'eval-lab', icon: FlaskConical, label: t('nav.evalLab'), href: '/eval-lab' }] : []),
  ];

  const navItems: { id: NavTab; icon: NavIconComponent; label: string }[] = [
    { id: 'chat', icon: AiGenerativeIcon, label: t('nav.chat') },
    { id: 'work', icon: Briefcase, label: t('nav.work') },
    { id: 'projects', icon: FolderKanban, label: t('nav.projects') },
  ];

  // 用户头像
  const UserAvatar = ({ size = 28 }: { size?: number }) => {
    if (user?.avatar_url && !avatarError) {
      return (
        <Image
          src={user.avatar_url}
          alt={user.display_name || 'User'}
          width={size}
          height={size}
          className="rounded-full object-cover"
          style={{ width: size, height: size }}
          onError={() => setAvatarError(true)}
          referrerPolicy="no-referrer"
          unoptimized
        />
      );
    }
    return (
      <div
        className="rounded-full bg-primary/10 flex items-center justify-center"
        style={{ width: size, height: size }}
      >
        <User size={size * 0.5} className="text-primary" />
      </div>
    );
  };

  const handleSignIn = useCallback(() => {
    closeMobileSidebar();
    const returnPath = currentPathname || '/';
    router.push(buildAuthLoginPath(returnPath));
  }, [closeMobileSidebar, currentPathname, router]);

  const handleTestLogin = useCallback(() => {
    if (isMobile && onCloseMobileSidebar) {
      onCloseMobileSidebar();
    }
    loginMock();
  }, [isMobile, onCloseMobileSidebar, loginMock]);

  const handleLogout = useCallback(() => {
    closeMobileSidebar();
    logout();
  }, [closeMobileSidebar, logout]);

  // 显示名称
  const displayName = user?.display_name || user?.email || tUserMenu('guest');

  return (
    <nav
      className={cn(
        'flex flex-col',
        'bg-background/95 backdrop-blur-xl',
        'border-r border-border/50',
        'transition-all duration-300 ease-in-out',
        // 移动端使用相对定位，以便跟随父容器变换
        // 桌面端使用固定定位
        isMobile ? 'relative h-full' : 'fixed inset-y-0 left-0 z-50',
      )}
      style={{ width: NAVBAR_WIDTH }}
    >
      {/* Header: User Avatar with Popover Menu */}
      <div className="p-2 flex flex-col items-center gap-2">
        <Popover>
          <PopoverTrigger asChild>
            <button
              className="w-10 h-10 rounded-xl flex items-center justify-center hover:bg-muted transition-colors"
              aria-label={displayName}
            >
              <UserAvatar />
            </button>
          </PopoverTrigger>
          <PopoverContent side="right" align="start" sideOffset={8} className="w-64 p-0 overflow-hidden">
            {user ? (
              <>
                {/* 用户信息区域 */}
                <div className="px-4 py-3 border-b border-border flex items-center gap-3">
                  <UserAvatar size={32} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{displayName}</p>
                    {user.email && user.email !== displayName && (
                      <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                    )}
                  </div>
                </div>

                {/* 菜单项 */}
                <div className="py-1">
                  {/* 订阅入口（仅 Sandbox 模式） */}
                  {!isLocal && (
                    <>
                      <Link
                        href="/pricing"
                        onClick={closeMobileSidebar}
                        className={cn(
                          'flex items-center gap-3 w-full px-4 py-2.5 text-sm transition-colors',
                          isPro ? 'text-foreground hover:bg-accent' : 'text-primary bg-primary/5 hover:bg-primary/10',
                        )}
                      >
                        {isPro ? (
                          <Crown size={16} className="text-primary" />
                        ) : (
                          <Zap size={16} className="text-primary" />
                        )}
                        <span className="flex-1 text-left">{isPro ? tPricing('pro.name') : tPricing('upgrade')}</span>
                      </Link>
                      <Link
                        href="/subscription"
                        onClick={closeMobileSidebar}
                        className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
                      >
                        <CreditCard size={16} className="text-muted-foreground" />
                        <span className="flex-1 text-left">{tUserMenu('subscription')}</span>
                      </Link>
                    </>
                  )}

                  {/* 设置 */}
                  <Link
                    href="/settings"
                    onClick={closeMobileSidebar}
                    className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
                  >
                    <Settings size={16} className="text-muted-foreground" />
                    <span>{tUserMenu('settings')}</span>
                  </Link>
                </div>

                {/* 退出登录 */}
                <div className="border-t border-border py-1">
                  <button
                    onClick={handleLogout}
                    className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
                  >
                    <LogOut size={16} className="text-muted-foreground" />
                    <span>{tUserMenu('logout')}</span>
                  </button>
                </div>
              </>
            ) : (
              <>
                {/* 登录选项 */}
                <div className="p-4 space-y-3">
                  <p className="text-sm font-medium text-foreground">{tUserMenu('loginTitle')}</p>
                  <button
                    onClick={handleSignIn}
                    disabled={isLoading}
                    className="flex items-center justify-center gap-2 w-full px-4 py-2.5 text-sm font-medium text-foreground bg-background border border-border rounded-lg hover:bg-accent transition-colors disabled:opacity-50"
                  >
                    <User size={16} className="text-primary shrink-0" />
                    <span>{tUserMenu('login')}</span>
                  </button>
                  {isDev && (
                    <button
                      onClick={handleTestLogin}
                      disabled={isLoading}
                      className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium text-muted-foreground bg-accent/50 border border-dashed border-border rounded-lg hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
                    >
                      <FlaskConical size={16} />
                      <span>{tUserMenu('loginForTest')}</span>
                    </button>
                  )}
                </div>

                {/* 升级入口 + 设置链接 */}
                <div className="border-t border-border py-1">
                  {/* 升级入口（仅 Sandbox 模式） */}
                  {!isLocal && (
                    <Link
                      href="/pricing"
                      onClick={closeMobileSidebar}
                      className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-accent-warm bg-accent-warm/8 hover:bg-accent-warm/12 transition-colors shadow-[var(--shadow-brand)]"
                    >
                      <Zap size={16} className="text-accent-warm" />
                      <span>{tPricing('upgrade')}</span>
                    </Link>
                  )}
                  <Link
                    href="/settings"
                    onClick={closeMobileSidebar}
                    className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
                  >
                    <Settings size={16} className="text-muted-foreground" />
                    <span>{tUserMenu('settings')}</span>
                  </Link>
                </div>
              </>
            )}
          </PopoverContent>
        </Popover>
      </div>

      {/* Divider */}
      <div className="mx-2 border-t border-border/50" />

      {/* Navigation Items */}
      <div className="flex-1 py-3 flex flex-col gap-1 items-center">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isInSettingsPage = currentPathname.startsWith('/settings');
          let isActive = false;

          if (item.id === 'chat') {
            isActive = !isInSettingsPage && activeTab === 'chat';
          } else if (item.id === 'work') {
            isActive = activeTab === 'work';
          } else if (item.id === 'projects') {
            isActive = activeTab === 'projects';
          }

          const href =
            item.id === 'chat'
              ? lastChatUrl || '/'
              : item.id === 'work'
                ? lastWorkUrl || '/work'
                : lastProjectsUrl || '/projects';

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
                      : 'text-muted-foreground hover:bg-primary/5 hover:text-accent-warm hover:shadow-[var(--shadow-brand)]',
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

        {/* Quick Access Items */}
        {quickAccessItems.map((item) => {
          const Icon = item.icon;
          // 判断当前是否在对应设置页或独立页面
          // 使用动态路由后可以通过 pathname 判断激活状态
          const href = item.href || `/settings/${item.settingsTab}`;
          const isActive = currentPathname === href;

          // 为eval-lab和skills页面添加hover预加载
          const handleMouseEnter = () => {
            if (item.id === 'eval-lab' || item.id === 'skills') {
              preloadMonacoEditor();
            }
          };

          return (
            <Tooltip key={item.id}>
              <TooltipTrigger asChild>
                <Link
                  href={href}
                  onClick={closeMobileSidebar}
                  onMouseEnter={handleMouseEnter}
                  className={cn(
                    'w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200',
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:bg-primary/5 hover:text-accent-warm hover:shadow-[var(--shadow-brand)]',
                  )}
                  aria-label={item.label}
                >
                  <Icon size={18} />
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right">{item.label}</TooltipContent>
            </Tooltip>
          );
        })}
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

        {/* Extension Bridge Status */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href="/settings/browser"
              onClick={closeMobileSidebar}
              className="inline-flex items-center justify-center w-10 h-10 rounded-xl transition-transform hover:scale-105"
              aria-label={
                badges.extensionConnected
                  ? t('nav.extensionConnected')
                  : t('nav.extensionDisconnected')
              }
            >
              <span
                className={cn(
                  'h-2.5 w-2.5 rounded-full transition-colors',
                  badges.extensionConnected
                    ? 'bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.14)]'
                    : 'bg-gray-300 shadow-[0_0_0_3px_rgba(156,163,175,0.12)]',
                )}
              />
            </Link>
          </TooltipTrigger>
          <TooltipContent side="right">
            {badges.extensionConnected
              ? t('nav.extensionConnected')
              : t('nav.extensionDisconnected')}
          </TooltipContent>
        </Tooltip>

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

const NavBar = memo<NavBarProps>((props) => {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return <NavBarInner {...props} />;
});

NavBar.displayName = 'NavBar';

export default NavBar;
