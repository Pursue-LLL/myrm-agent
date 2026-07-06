'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import Image from 'next/image';
import { CreditCard, Settings, LogOut, User, FlaskConical, Crown, Zap, Layers, BrainCircuit } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { STYLES } from './constants';
import { localizeReactNode } from '@/lib/utils/localeText';
import useAuthStore from '@/store/useAuthStore';
import { useMemoryStore } from '@/store/memory';
import { useSubscription } from '@/hooks/useSubscription';
import { useUsageAnalytics } from '@/hooks/useUsageAnalytics';
import { isLocalMode } from '@/lib/deploy-mode';
import { buildAuthLoginPath } from '@/lib/auth-redirect';

interface UserMenuProps {
  isExpanded: boolean;
  isMobile: boolean;
  isMobileOpen: boolean;
  onMobileClose: () => void;
}

const isDev = process.env.NODE_ENV === 'development';

const UserMenu = memo<UserMenuProps>(({ isExpanded, isMobile, isMobileOpen, onMobileClose }) => {
  const t = useTranslations('userMenu');
  const tPricing = useTranslations('pricing');
  const locale = useLocale();
  const router = useRouter();
  const { user, isLoading, initAuth, logout, loginMock } = useAuthStore();
  const { pendingCount, fetchPendingMemories, fetchConflicts } = useMemoryStore();
  const { isPro } = useSubscription();
  const { usage, isLoading: isUsageLoading } = useUsageAnalytics();
  const isLocal = isLocalMode();

  // Sandbox 模式：初始化认证状态
  useEffect(() => {
    if (!isLocal) {
      initAuth();
    }
  }, [isLocal, initAuth]);

  // 获取一次待审批记忆和冲突（不轮询）
  // Local 模式无需 user 条件；Sandbox 模式需等登录后再获取
  useEffect(() => {
    if (isLocal || user) {
      fetchPendingMemories();
      fetchConflicts();
    }
  }, [user, isLocal, fetchPendingMemories, fetchConflicts]);

  const handleNavigate = useCallback(
    (path: string, hash?: string) => {
      onMobileClose();
      if (hash) {
        router.push(`${path}?tab=${hash}`);
      } else {
        router.push(path);
      }
    },
    [router, onMobileClose],
  );

  const handleSignIn = useCallback(() => {
    onMobileClose();
    const returnPath =
      typeof window !== 'undefined' ? window.location.pathname + window.location.search : '/';
    router.push(buildAuthLoginPath(returnPath));
  }, [onMobileClose, router]);

  const handleTestLogin = useCallback(() => {
    onMobileClose();
    loginMock();
  }, [onMobileClose, loginMock]);

  const handleLogout = useCallback(() => {
    onMobileClose();
    logout();
  }, [onMobileClose, logout]);

  // 本地模式：移除订阅和个性化选项
  const menuItems = isLocal
    ? [
        {
          icon: BrainCircuit,
          label: 'Brain Console',
          onClick: () => handleNavigate('/brain'),
        },
        {
          icon: Layers,
          label: t('batchOptimization'),
          onClick: () => handleNavigate('/batch-optimization'),
        },
        {
          icon: Settings,
          label: t('settings'),
          onClick: () => handleNavigate('/settings'),
        },
      ]
    : [
        {
          icon: isPro ? Crown : Zap,
          label: isPro ? 'Pro' : tPricing('upgrade'),
          onClick: () => handleNavigate('/pricing'),
          highlight: !isPro,
        },
        {
          icon: CreditCard,
          label: t('subscription'),
          onClick: () => handleNavigate('/subscription'),
        },
        {
          icon: BrainCircuit,
          label: 'Brain Console',
          onClick: () => handleNavigate('/brain'),
        },
        {
          icon: Layers,
          label: t('batchOptimization'),
          onClick: () => handleNavigate('/batch-optimization'),
        },
        {
          icon: Settings,
          label: t('settings'),
          onClick: () => handleNavigate('/settings'),
        },
        {
          icon: IconGlow,
          label: t('personalization'),
          onClick: () => handleNavigate('/settings', 'personalization'),
          badge: pendingCount > 0 ? pendingCount : undefined,
        },
      ];

  const showExpanded = (isExpanded && !isMobile) || isMobileOpen;

  const getButtonClasses = () =>
    cn('p-2 lg:p-3 rounded-xl transition-colors duration-200', STYLES.button.hover, STYLES.button.touch);

  // 获取显示名称
  const displayName = user?.display_name || user?.email || (isLocal ? 'Local User' : t('guest'));

  // 头像加载失败状态
  const [avatarError, setAvatarError] = useState(false);

  // 用户头像
  const UserAvatar = () => {
    if (user?.avatar_url && !avatarError) {
      return (
        <Image
          src={user.avatar_url}
          alt={displayName}
          width={32}
          height={32}
          className="rounded-full object-cover"
          style={{ width: 32, height: 32 }}
          onError={() => setAvatarError(true)}
          referrerPolicy="no-referrer"
          unoptimized
        />
      );
    }
    return (
      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
        <User size={16} className="text-primary" />
      </div>
    );
  };

  // Sandbox 模式：未登录状态
  if (!user && !isLocal) {
    return localizeReactNode(
      <Popover>
        <PopoverTrigger asChild>
          {showExpanded ? (
            <button
              className={cn(
                'flex items-center gap-3 px-3 lg:px-4 py-2 lg:py-3 w-full',
                getButtonClasses(),
                STYLES.text.secondary,
              )}
              aria-label={t('login')}
            >
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                <User size={16} className="text-primary" />
              </div>
              <span className="text-sm lg:text-base font-medium truncate">{isLoading ? t('loading') : t('guest')}</span>
            </button>
          ) : (
            <button
              className={cn('flex items-center justify-center', getButtonClasses(), STYLES.text.secondary)}
              title={t('login')}
              aria-label={t('login')}
            >
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                <User size={16} className="text-primary" />
              </div>
            </button>
          )}
        </PopoverTrigger>

        <PopoverContent side="top" align="start" sideOffset={8} className="w-64 p-0 overflow-hidden">
          {/* 登录选项 */}
          <div className="p-4 space-y-3">
            <p className="text-sm font-medium text-foreground">{t('loginTitle')}</p>
            <button
              onClick={handleSignIn}
              disabled={isLoading}
              className="flex items-center justify-center gap-2 w-full px-4 py-2.5 text-sm font-medium text-foreground bg-background border border-border rounded-lg hover:bg-accent transition-colors disabled:opacity-50"
            >
              <User size={16} className="text-primary shrink-0" />
              <span>{t('login')}</span>
            </button>
            {isDev && (
              <button
                onClick={handleTestLogin}
                disabled={isLoading}
                className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium text-muted-foreground bg-accent/50 border border-dashed border-border rounded-lg hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
              >
                <FlaskConical size={16} />
                <span>{t('loginForTest')}</span>
              </button>
            )}
          </div>

          {/* 设置链接 */}
          <div className="border-t border-border py-1">
            <button
              onClick={() => handleNavigate('/pricing')}
              className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-primary bg-primary/5 hover:bg-primary/10 transition-colors"
            >
              <Zap size={16} className="text-primary" />
              <span>{tPricing('upgrade')}</span>
            </button>
            <button
              onClick={() => handleNavigate('/settings')}
              className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
            >
              <Settings size={16} className="text-muted-foreground" />
              <span>{t('settings')}</span>
            </button>
          </div>
        </PopoverContent>
      </Popover>,
      locale,
    );
  }

  // 已登录状态
  return localizeReactNode(
    <Popover>
      <PopoverTrigger asChild>
        {showExpanded ? (
          <button
            className={cn(
              'flex items-center gap-3 px-3 lg:px-4 py-2 lg:py-3 w-full',
              getButtonClasses(),
              STYLES.text.secondary,
            )}
            aria-label={t('openMenu')}
          >
            <UserAvatar />
            <span className="text-sm lg:text-base font-medium truncate">{displayName}</span>
          </button>
        ) : (
          <button
            className={cn('flex items-center justify-center', getButtonClasses(), STYLES.text.secondary)}
            title={t('openMenu')}
            aria-label={t('openMenu')}
          >
            <UserAvatar />
          </button>
        )}
      </PopoverTrigger>

      <PopoverContent side="top" align="start" sideOffset={8} className="w-64 p-0 overflow-hidden">
        {/* 用户信息区域 */}
        <div className="px-4 py-3 border-b border-border flex items-center gap-3">
          <UserAvatar />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground truncate">{displayName}</p>
            {user.email && user.email !== displayName && (
              <p className="text-xs text-muted-foreground truncate">{user.email}</p>
            )}
          </div>
        </div>

        {/* 配额概览（改为 BYOK Usage Radar） */}
        <div className="px-3 py-2.5 border-b border-border bg-gradient-to-br from-blue-500/5 to-indigo-500/5">
          <div className="flex items-center justify-between mb-1.5 px-1">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              {t('usageAnalytics', { defaultMessage: 'USAGE ANALYTICS' })}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {/* Model Calls */}
            <div className="flex flex-col items-center p-2 rounded-lg bg-background/60 hover:bg-background/90 transition-colors border border-black/[0.03] dark:border-white/[0.03]">
              <IconGlow className="w-3.5 h-3.5 text-amber-500 mb-1" />
              <span className="text-[10px] text-muted-foreground mb-0.5">
                {t('totalCalls', { defaultMessage: 'Calls' })}
              </span>
              <span className="text-xs font-bold text-foreground">
                {isUsageLoading
                  ? '...'
                  : usage.total_calls >= 1000
                    ? `${(usage.total_calls / 1000).toFixed(1)}K`
                    : usage.total_calls}
              </span>
            </div>
            {/* Tokens */}
            <div className="flex flex-col items-center p-2 rounded-lg bg-background/60 hover:bg-background/90 transition-colors border border-black/[0.03] dark:border-white/[0.03]">
              <Zap size={14} className="text-blue-500 mb-1" />
              <span className="text-[10px] text-muted-foreground mb-0.5">
                {t('totalTokens', { defaultMessage: 'Tokens' })}
              </span>
              <span className="text-xs font-bold text-foreground">
                {isUsageLoading
                  ? '...'
                  : usage.total_tokens >= 1000000
                    ? `${(usage.total_tokens / 1000000).toFixed(1)}M`
                    : usage.total_tokens >= 1000
                      ? `${(usage.total_tokens / 1000).toFixed(1)}K`
                      : usage.total_tokens}
              </span>
            </div>
            {/* USD Cost */}
            <div className="flex flex-col items-center p-2 rounded-lg bg-background/60 hover:bg-background/90 transition-colors border border-black/[0.03] dark:border-white/[0.03]">
              <svg className="w-3.5 h-3.5 text-emerald-500 mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="text-[10px] text-muted-foreground mb-0.5">Est. Cost</span>
              <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">
                {isUsageLoading ? '...' : `$${usage.total_usd.toFixed(4)}`}
              </span>
            </div>
          </div>
        </div>

        {/* 菜单项 */}
        <div className="py-1">
          {menuItems.map((item) => (
            <button
              key={item.label}
              onClick={item.onClick}
              className={cn(
                'flex items-center gap-3 w-full px-4 py-2.5 text-sm transition-colors',
                item.highlight ? 'text-primary bg-primary/5 hover:bg-primary/10' : 'text-foreground hover:bg-accent',
              )}
            >
              <item.icon size={16} className={item.highlight ? 'text-primary' : 'text-muted-foreground'} />
              <span className="flex-1 text-left">{item.label}</span>
              {item.badge && (
                <span className="min-w-[20px] h-5 flex items-center justify-center text-xs font-bold text-white bg-gradient-to-br from-red-500 to-rose-600 rounded-full px-1.5">
                  {item.badge > 99 ? '99+' : item.badge}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* 退出登录 */}
        {!isLocal && (
          <div className="border-t border-border py-1">
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-foreground hover:bg-accent transition-colors"
            >
              <LogOut size={16} className="text-muted-foreground" />
              <span>{t('logout')}</span>
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>,
    locale,
  );
});

UserMenu.displayName = 'UserMenu';

export default UserMenu;
