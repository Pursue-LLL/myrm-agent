'use client';

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { LogIn, FlaskConical } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import useAuthStore from '@/store/useAuthStore';
import { buildAuthLoginPath } from '@/lib/auth-redirect';

interface LoginPromptProps {
  className?: string;
  title?: string;
  description?: string;
  variant?: 'default' | 'compact';
  showTestLogin?: boolean;
}

const isDev = process.env.NODE_ENV === 'development';

const LoginPrompt = memo<LoginPromptProps>(
  ({ className, title, description, variant = 'default', showTestLogin = isDev }) => {
    const tAuth = useTranslations('auth');
    const tUserMenu = useTranslations('userMenu');
    const { loginMock } = useAuthStore();

    const handleSignIn = useCallback(() => {
      const returnPath =
        typeof window !== 'undefined' ? window.location.pathname + window.location.search : '/';
      window.location.href = buildAuthLoginPath(returnPath);
    }, []);

    const handleTestLogin = useCallback(() => {
      loginMock();
    }, [loginMock]);

    const signInLabel = tAuth('login.buttonLogin');

    if (variant === 'compact') {
      return (
        <div className={cn('flex flex-col items-center gap-4 py-8', className)}>
          <p className="text-sm text-muted-foreground text-center">{title || tUserMenu('loginTitle')}</p>
          <div className="flex flex-col gap-2">
            <button
              onClick={handleSignIn}
              className={cn(
                'flex items-center justify-center gap-2 px-6 py-2.5',
                'text-sm font-medium text-foreground',
                'bg-background border border-border rounded-lg',
                'hover:bg-accent hover:border-border/80',
                'transition-all duration-200',
                ' hover:shadow',
              )}
            >
              <LogIn className="w-4 h-4 shrink-0" />
              <span>{signInLabel}</span>
            </button>
            {showTestLogin && (
              <button
                onClick={handleTestLogin}
                className={cn(
                  'flex items-center justify-center gap-2 px-6 py-2.5',
                  'text-sm font-medium text-muted-foreground',
                  'bg-accent/50 border border-dashed border-border rounded-lg',
                  'hover:bg-accent hover:text-foreground',
                  'transition-all duration-200',
                )}
              >
                <FlaskConical size={16} />
                <span>{tUserMenu('loginForTest')}</span>
              </button>
            )}
          </div>
        </div>
      );
    }

    return (
      <div className={cn('flex flex-col items-center justify-center py-16', className)}>
        <div className="relative">
          <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full" />
          <div className="relative bg-accent/50 p-4 rounded-2xl">
            <LogIn className="h-10 w-10 text-muted-foreground/50" />
          </div>
        </div>
        <p className="mt-4 text-sm font-medium text-foreground">{title || tUserMenu('loginTitle')}</p>
        {description && <p className="mt-1 text-xs text-muted-foreground text-center max-w-xs">{description}</p>}
        <div className="mt-6 flex flex-col gap-3">
          <button
            onClick={handleSignIn}
            className={cn(
              'flex items-center justify-center gap-2.5 px-6 py-3',
              'text-sm font-medium text-foreground',
              'bg-background border border-border rounded-xl',
              'hover:bg-accent hover:border-border/80',
              'transition-all duration-200',
              ' hover:shadow-md',
            )}
          >
            <LogIn className="w-4 h-4 shrink-0" />
            <span>{signInLabel}</span>
          </button>
          {showTestLogin && (
            <button
              onClick={handleTestLogin}
              className={cn(
                'flex items-center justify-center gap-2 px-6 py-2.5',
                'text-sm font-medium text-muted-foreground',
                'bg-accent/50 border border-dashed border-border rounded-xl',
                'hover:bg-accent hover:text-foreground',
                'transition-all duration-200',
              )}
            >
              <FlaskConical size={16} />
              <span>{tUserMenu('loginForTest')}</span>
            </button>
          )}
        </div>
      </div>
    );
  },
);

LoginPrompt.displayName = 'LoginPrompt';

export default LoginPrompt;
