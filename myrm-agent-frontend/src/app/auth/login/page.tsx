'use client';

import Link from 'next/link';
import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { LogIn, Lock, User, Eye, EyeOff, Shield, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import CaptchaModal from '@/components/auth/CaptchaModal';
import OAuthButtons from '@/components/auth/OAuthButtons';
import { selectLocalizedText } from '@/lib/utils/localeText';
import { AUTH_SESSION_COOKIE, clearAuthSessionCookie } from '@/lib/auth-cookie';
import { isSandboxAuthBuild } from '@/lib/deploy-mode';
import { getAuthToken } from '@/lib/guest';
import { readAuthRedirectParam } from '@/lib/auth-redirect';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import useAuthStore from '@/store/useAuthStore';

export default function LoginPage() {
  const t = useTranslations('auth');
  const locale = useLocale();
  const sandbox = isSandboxAuthBuild();
  const cpLogin = useAuthStore((s) => s.login);
  const text = useCallback((value: string) => selectLocalizedText(value, locale), [locale]);
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [autoLoginInProgress, setAutoLoginInProgress] = useState(false);
  const [showCaptcha, setShowCaptcha] = useState(false);
  const [captchaVerifyUrl, setCaptchaVerifyUrl] = useState('');
  const [hcaptchaSiteKey] = useState(process.env.NEXT_PUBLIC_HCAPTCHA_SITE_KEY || '');

  const tempToken = searchParams.get('token');
  const postAuthPath = readAuthRedirectParam(searchParams) ?? '/';

  const navigateAfterAuth = useCallback(() => {
    router.replace(postAuthPath);
  }, [router, postAuthPath]);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/webui/auth/status`, {
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
  }, [navigateAfterAuth]);

  const exchangeToken = useCallback(
    async (token: string) => {
      setAutoLoginInProgress(true);
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/webui/auth/token-exchange`, {
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
      exchangeToken(tempToken);
      return;
    }
    checkAuth();
  }, [sandbox, tempToken, exchangeToken, checkAuth, postAuthPath]);

  const handleCaptchaVerified = () => {
    // CAPTCHA verified successfully, reset rate limit state and allow retry
    setError('');
    setFailedAttempts(0);
    // Auto-retry login could be implemented here if desired
  };

  const handleCaptchaClose = () => {
    setShowCaptcha(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (sandbox) {
        const response = await fetch(`${resolveCpBaseUrl()}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        const data = await response.json();
        if (!response.ok) {
          setError(typeof data.detail === 'string' ? data.detail : t('login.errorGeneric'));
          return;
        }
        await cpLogin(data.token, { id: data.user_id, email: data.email });
        window.location.href = postAuthPath;
        return;
      }

      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/webui/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });

      if (response.ok) {
        navigateAfterAuth();
      } else if (response.status === 429) {
        // OPT-7: Rate limit exceeded — parse Retry-After header
        const data = await response.json();
        const retryAfterHeader = response.headers.get('Retry-After');
        const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : 60;

        // Check if CAPTCHA is required
        if (data.require_captcha && data.captcha_verify_url) {
          setCaptchaVerifyUrl(data.captcha_verify_url);
          setShowCaptcha(true);
          setError(
            t('login.errorRateLimitCaptcha', {
              default: text(
                'Too many failed attempts. Please complete CAPTCHA to continue. / 失败次数过多，请完成验证以继续。',
              ),
              seconds: retryAfter,
            }),
          );
        } else {
          setError(t('login.errorRateLimit', { seconds: retryAfter }));
        }
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
          <CardContent className="flex flex-col items-center justify-center py-12 gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-primary-600 dark:text-primary-400" />
            <p className="text-sm text-muted-foreground">{t('login.autoLogin')}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-background to-primary-50 dark:from-gray-900 dark:via-background dark:to-gray-900 p-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader className="space-y-2 text-center">
          <div className="mx-auto w-12 h-12 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center mb-2">
            <Shield className="w-6 h-6 text-primary-600 dark:text-primary-400" />
          </div>
          <CardTitle className="text-2xl font-bold">{t('login.title')}</CardTitle>
          <CardDescription>{t('login.description')}</CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {sandbox ? (
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">{t('register.labelEmail')}</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-10"
                    placeholder={t('register.placeholderEmail')}
                    disabled={loading}
                    autoComplete="email"
                    autoFocus
                    required
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">{t('login.labelAccount')}</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    type="text"
                    value={username}
                    className="pl-10 bg-muted/50 cursor-default"
                    readOnly
                    tabIndex={-1}
                  />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">{t('login.labelPassword')}</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 pr-10"
                  placeholder={t('login.placeholderPassword')}
                  disabled={loading}
                  autoComplete="current-password"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3">
                <p className="text-sm text-destructive font-medium">{error}</p>
                {failedAttempts >= 3 && (
                  <p className="text-xs text-destructive/80 mt-1">{t('login.tooManyAttempts')}</p>
                )}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={loading || !password || (sandbox && !email)}>
              <LogIn className="w-4 h-4 mr-2" />
              {loading ? t('login.buttonLoggingIn') : t('login.buttonLogin')}
            </Button>
          </form>

          {sandbox && <OAuthButtons redirectPath={postAuthPath} />}

          {sandbox && (
            <p className="mt-4 text-center text-sm text-muted-foreground">
              {t('login.noAccount')}{' '}
              <Link
                href={
                  postAuthPath !== '/'
                    ? `/auth/register?redirect=${encodeURIComponent(postAuthPath)}`
                    : '/auth/register'
                }
                className="text-primary font-medium hover:underline"
              >
                {t('login.createAccount')}
              </Link>
            </p>
          )}

          <div className="mt-6 pt-6 border-t border-border">
            <p className="text-xs text-center text-muted-foreground">{t('login.footerInfo')}</p>
          </div>
        </CardContent>
      </Card>

      {/* CAPTCHA Modal */}
      <CaptchaModal
        isOpen={showCaptcha}
        onClose={handleCaptchaClose}
        onVerified={handleCaptchaVerified}
        verifyUrl={captchaVerifyUrl}
        siteKey={hcaptchaSiteKey}
      />
    </div>
  );
}
