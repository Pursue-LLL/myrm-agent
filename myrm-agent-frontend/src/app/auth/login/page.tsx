'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import dynamic from 'next/dynamic';
import { Card } from '@/components/primitives/card';
import { AUTH_SESSION_COOKIE, clearAuthSessionCookie } from '@/lib/auth-cookie';
import { isSandboxAuthBuild } from '@/lib/deploy-mode';
import { getAuthToken } from '@/lib/guest';
import { readAuthRedirectParam } from '@/lib/auth-redirect';
import { getWebuiUrl } from '@/lib/api';

const LocalLoginForm = dynamic(() => import('@/components/auth/LocalLoginForm'), {
  ssr: false,
  loading: () => <Loader2 className="w-8 h-8 animate-spin mx-auto text-muted-foreground" />,
});
const SandboxLoginForm = dynamic(() => import('@/components/auth/SandboxLoginForm'), {
  ssr: false,
  loading: () => <Loader2 className="w-8 h-8 animate-spin mx-auto text-muted-foreground" />,
});

export default function LoginPage() {
  const t = useTranslations('auth');
  const sandbox = isSandboxAuthBuild();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [autoLoginInProgress, setAutoLoginInProgress] = useState(false);

  const tempToken = searchParams.get('token');
  const postAuthPath = readAuthRedirectParam(searchParams) ?? '/';

  const navigateAfterAuth = useCallback(() => {
    router.replace(postAuthPath);
  }, [router, postAuthPath]);

  const checkAuth = useCallback(async () => {
    if (sandbox) return;
    try {
      const response = await fetch(getWebuiUrl('/auth/status'), {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();

        if (!data.is_setup_done) {
          router.push('/auth/setup');
          return;
        }

        if (data.username) {
          setUsername(data.username);
        }

        if (data.is_authenticated) {
          navigateAfterAuth();
          return;
        }
      }
    } catch (err) {
      console.error('Auth check error:', err);
    }
  }, [navigateAfterAuth, router, sandbox]);

  const exchangeToken = useCallback(
    async (token: string) => {
      setAutoLoginInProgress(true);
      try {
        const response = await fetch(getWebuiUrl('/auth/token-exchange'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ temp_token: token }),
        });

        if (response.ok) {
          navigateAfterAuth();
          return;
        }

        setError(t('login.autoLoginFailed'));
      } catch {
        setError(t('login.autoLoginFailed'));
      } finally {
        setAutoLoginInProgress(false);
        const url = new URL(window.location.href);
        url.searchParams.delete('token');
        window.history.replaceState({}, '', url.toString());
      }

      await checkAuth();
    },
    [navigateAfterAuth, t, checkAuth],
  );

  useEffect(() => {
    if (sandbox) {
      const hasCookie =
        typeof document !== 'undefined' &&
        document.cookie.split(';').some((part) => part.trim().startsWith(`${AUTH_SESSION_COOKIE}=1`));
      const token = getAuthToken();
      if (hasCookie && !token) {
        clearAuthSessionCookie();
        return;
      }
      if (hasCookie && token) {
        window.location.href = postAuthPath;
      }
      return;
    }
    if (tempToken) {
      void (async () => {
        try {
          const statusRes = await fetch(getWebuiUrl('/auth/status'), { credentials: 'include' });
          if (statusRes.ok) {
            const status = await statusRes.json();
            if (!status.is_setup_done) {
              router.push(`/auth/setup?token=${encodeURIComponent(tempToken)}`);
              return;
            }
          }
        } catch {
          // fall through to token exchange
        }
        await exchangeToken(tempToken);
      })();
      return;
    }
    checkAuth();
  }, [sandbox, tempToken, exchangeToken, checkAuth, postAuthPath, router]);

  const handleLocalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetch(getWebuiUrl('/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });

      if (response.ok) {
        navigateAfterAuth();
      } else if (response.status === 429) {
        const retryAfterHeader = response.headers.get('Retry-After');
        const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : 60;
        setError(t('login.errorRateLimit', { seconds: retryAfter }));
      } else {
        const data = await response.json();
        setError(data.detail || t('login.errorGeneric'));
        setFailedAttempts((prev) => prev + 1);
      }
    } catch (err) {
      console.error('Login error:', err);
      setError(t('login.errorNetwork'));
    } finally {
      setLoading(false);
    }
  };

  if (autoLoginInProgress) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-background to-primary-50 dark:from-gray-900 dark:via-background dark:to-gray-900 p-4">
        <Card className="w-full max-w-md shadow-2xl">
          <div className="flex flex-col items-center justify-center py-12 gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-primary-600 dark:text-primary-400" />
            <p className="text-sm text-muted-foreground">{t('login.autoLogin')}</p>
          </div>
        </Card>
      </div>
    );
  }

  if (sandbox) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-background to-primary-50 dark:from-background dark:via-background dark:to-background p-4">
        <Card className="w-full max-w-md shadow-2xl border-border/60">
          <SandboxLoginForm postAuthPath={postAuthPath} />
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50/50 via-background to-emerald-50/50 dark:from-background dark:via-background dark:to-background p-4">
      <LocalLoginForm
        username={username}
        password={password}
        loading={loading}
        error={error}
        failedAttempts={failedAttempts}
        onPasswordChange={setPassword}
        onSubmit={handleLocalSubmit}
      />
    </div>
  );
}