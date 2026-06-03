'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { LogIn, User, Lock, Eye, EyeOff, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import CaptchaModal from '@/components/auth/CaptchaModal';
import OAuthButtons from '@/components/auth/OAuthButtons';
import { selectLocalizedText } from '@/lib/utils/localeText';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import useAuthStore from '@/store/useAuthStore';

interface SandboxLoginFormProps {
  postAuthPath: string;
}

export default function SandboxLoginForm({ postAuthPath }: SandboxLoginFormProps) {
  const t = useTranslations('auth');
  const locale = useLocale();
  const cpLogin = useAuthStore((s) => s.login);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [showCaptcha, setShowCaptcha] = useState(false);
  const [captchaVerifyUrl, setCaptchaVerifyUrl] = useState('');
  const [hcaptchaSiteKey] = useState(process.env.NEXT_PUBLIC_HCAPTCHA_SITE_KEY || '');

  const text = (value: string) => selectLocalizedText(value, locale);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetch(`${resolveCpBaseUrl()}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 429) {
          const retryAfterHeader = response.headers.get('Retry-After');
          const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : 60;
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
          setError(typeof data.detail === 'string' ? data.detail : t('login.errorGeneric'));
        }
        setFailedAttempts((prev) => prev + 1);
        return;
      }
      await cpLogin(data.token, { id: data.user_id, email: data.email });
      window.location.href = postAuthPath;
    } catch (err) {
      console.error('Login error:', err);
      setError(t('login.errorNetwork'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <CardHeader className="space-y-2 text-center">
        <div className="mx-auto w-12 h-12 bg-primary/15 rounded-full flex items-center justify-center mb-2">
          <Shield className="w-6 h-6 text-primary" />
        </div>
        <CardTitle className="text-2xl font-bold">{t('login.title')}</CardTitle>
        <CardDescription>{t('login.description')}</CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
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

          <Button type="submit" className="w-full" disabled={loading || !password || !email}>
            <LogIn className="w-4 h-4 mr-2" />
            {loading ? t('login.buttonLoggingIn') : t('login.buttonLogin')}
          </Button>
        </form>

        <OAuthButtons redirectPath={postAuthPath} />

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

        <div className="mt-6 pt-6 border-t border-border">
          <p className="text-xs text-center text-muted-foreground">{t('login.footerInfo')}</p>
        </div>
      </CardContent>

      <CaptchaModal
        isOpen={showCaptcha}
        onClose={() => setShowCaptcha(false)}
        onVerified={() => {
          setError('');
          setFailedAttempts(0);
        }}
        verifyUrl={captchaVerifyUrl}
        siteKey={hcaptchaSiteKey}
      />
    </>
  );
}