'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import dynamic from 'next/dynamic';
import { Card } from '@/components/primitives/card';
import SandboxAuthLayout from '@/components/auth/SandboxAuthLayout';
import { AUTH_SESSION_COOKIE, clearAuthSessionCookie } from '@/lib/auth-cookie';
import { isSandboxAuthBuild } from '@/lib/deploy-mode';
import { getAuthToken } from '@/lib/guest';
import { readAuthRedirectParam } from '@/lib/auth-redirect';
import { getWebuiUrl } from '@/lib/api';
import { syncCookieLocaleToPersonalSettings } from '@/lib/locale-personal-sync';

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
          await syncCookieLocaleToPersonalSettings();
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
          await syncCookieLocaleToPersonalSettings();
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
        await syncCookieLocaleToPersonalSettings();
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
      <SandboxAuthLayout>
        <SandboxLoginForm postAuthPath={postAuthPath} />
      </SandboxAuthLayout>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4 relative overflow-hidden">
      {/* SaaS Style Decorative Background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-primary/20 blur-[120px] rounded-full opacity-50" />
        <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-blue-500/10 blur-[100px] rounded-full opacity-40" />
        <div className="absolute top-1/4 left-0 w-[500px] h-[500px] bg-purple-500/10 blur-[100px] rounded-full opacity-30" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]" />
      </div>

      <div className="w-full max-w-md relative z-10">
        <div className="bg-background/80 backdrop-blur-2xl border border-white/10 dark:border-white/5 shadow-2xl rounded-3xl p-8 relative overflow-hidden ring-1 ring-black/5 dark:ring-white/5">
          {/* Top highlight line */}
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-primary/50 to-transparent" />
          
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
      </div>
    </div>
  );
}