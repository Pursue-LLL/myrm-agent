'use client';

/**
 * [INPUT]
 * - @/store/useAuthStore (POS: 当前登录用户与登录/退出动作)
 * - @/hooks/billing/useSubscription (POS: 是否订阅 Pro)
 * - @/lib/deploy-mode::isLocalMode (POS: 本地部署不展示订阅入口)
 * - @/lib/auth-redirect::buildAuthLoginPath (POS: 登录后回到当前页面的路径)
 *
 * [OUTPUT]
 * - NavAccountMenu: 导航栏顶部的头像按钮与账号菜单（访客登录、订阅入口、设置、退出）
 *
 * [POS]
 * 左侧导航栏的账号入口。头像是稳定的组件：导航栏任何更新都不会重建图片；头像地址变了会重新尝试加载。
 */
import { memo, useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import Image from 'next/image';
import Link from 'next/link';
import { Crown, CreditCard, FlaskConical, LogOut, Settings, User, Zap } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import useAuthStore from '@/store/useAuthStore';
import { useSubscription } from '@/hooks/billing/useSubscription';
import { isLocalMode } from '@/lib/deploy-mode';
import { buildAuthLoginPath } from '@/lib/auth-redirect';

interface UserAvatarProps {
  avatarUrl?: string;
  name: string;
  /** The picture address that failed to load; a different address is tried again. */
  failedUrl: string | null;
  onLoadFailed: (url: string) => void;
  size?: number;
}

function UserAvatar({ avatarUrl, name, failedUrl, onLoadFailed, size = 28 }: UserAvatarProps) {
  if (avatarUrl && avatarUrl !== failedUrl) {
    return (
      <Image
        src={avatarUrl}
        alt={name}
        width={size}
        height={size}
        className="rounded-full object-cover"
        style={{ width: size, height: size }}
        onError={() => onLoadFailed(avatarUrl)}
        referrerPolicy="no-referrer"
        unoptimized
      />
    );
  }
  return (
    <div className="rounded-full bg-primary/10 flex items-center justify-center" style={{ width: size, height: size }}>
      <User size={size * 0.5} className="text-primary" />
    </div>
  );
}

interface NavAccountMenuProps {
  currentPathname: string;
  /** Called before leaving through a menu entry, so the mobile sidebar can close. */
  onNavigate: () => void;
}

export const NavAccountMenu = memo(function NavAccountMenu({ currentPathname, onNavigate }: NavAccountMenuProps) {
  const router = useRouter();
  const tPricing = useTranslations('pricing');
  const tUserMenu = useTranslations('userMenu');
  const { user, isLoading, logout, loginMock } = useAuthStore();
  const { isPro } = useSubscription();
  const isLocal = isLocalMode();
  const isDev = process.env.NODE_ENV === 'development';
  const [failedAvatarUrl, setFailedAvatarUrl] = useState<string | null>(null);

  const displayName = user?.display_name || user?.email || tUserMenu('guest');
  const avatarProps = {
    avatarUrl: user?.avatar_url,
    name: displayName,
    failedUrl: failedAvatarUrl,
    onLoadFailed: setFailedAvatarUrl,
  };

  const handleSignIn = useCallback(() => {
    onNavigate();
    router.push(buildAuthLoginPath(currentPathname || '/'));
  }, [onNavigate, currentPathname, router]);

  const handleTestLogin = useCallback(() => {
    onNavigate();
    loginMock();
  }, [onNavigate, loginMock]);

  const handleLogout = useCallback(() => {
    onNavigate();
    logout();
  }, [onNavigate, logout]);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className="w-10 h-10 rounded-xl flex items-center justify-center hover:bg-muted transition-colors"
          aria-label={displayName}
        >
          <UserAvatar {...avatarProps} />
        </button>
      </PopoverTrigger>
      <PopoverContent side="right" align="start" sideOffset={8} className="w-64 p-0 overflow-hidden">
        {user ? (
          <>
            {/* 用户信息区域 */}
            <div className="px-4 py-3 border-b border-border flex items-center gap-3">
              <UserAvatar {...avatarProps} size={32} />
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
                    onClick={onNavigate}
                    className={cn(
                      'flex items-center gap-3 w-full px-4 py-2.5 text-sm transition-colors',
                      isPro ? 'text-foreground hover:bg-accent' : 'text-primary bg-primary/5 hover:bg-primary/10',
                    )}
                  >
                    {isPro ? <Crown size={16} className="text-primary" /> : <Zap size={16} className="text-primary" />}
                    <span className="flex-1 text-left">{isPro ? tPricing('pro.name') : tPricing('upgrade')}</span>
                  </Link>
                  <Link
                    href="/subscription"
                    onClick={onNavigate}
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
                onClick={onNavigate}
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
                  onClick={onNavigate}
                  className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-accent-warm bg-accent-warm/8 hover:bg-accent-warm/12 transition-colors shadow-brand"
                >
                  <Zap size={16} className="text-accent-warm" />
                  <span>{tPricing('upgrade')}</span>
                </Link>
              )}
              <Link
                href="/settings"
                onClick={onNavigate}
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
  );
});
