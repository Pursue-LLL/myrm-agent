'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Loader2, Shield } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { sanitizeAuthRedirectPath } from '@/lib/auth-redirect';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import useAuthStore from '@/store/useAuthStore';

export default function OAuthCallbackPage() {
  const t = useTranslations('auth.oauth');
  const router = useRouter();
  const searchParams = useSearchParams();
  const cpLogin = useAuthStore((s) => s.login);

  const [error, setError] = useState('');

  useEffect(() => {
    const oauthError = searchParams.get('error');
    if (oauthError) {
      setError(oauthError);
      return;
    }

    const exchange = searchParams.get('exchange');
    const postAuthPath = sanitizeAuthRedirectPath(searchParams.get('redirect')) ?? '/';

    if (!exchange) {
      setError(t('missingToken'));
      return;
    }

    void (async () => {
      try {
        const response = await fetch(`${resolveCpBaseUrl()}/api/auth/oauth/exchange`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ exchange }),
        });
        const data = await response.json();
        if (!response.ok) {
          setError(typeof data.detail === 'string' ? data.detail : t('failed'));
          return;
        }
        await cpLogin(data.token, { id: data.user_id, email: data.email });
        window.location.href = postAuthPath;
      } catch {
        setError(t('failed'));
      }
    })();
  }, [cpLogin, router, searchParams, t]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-background to-primary-50 dark:from-gray-900 dark:via-background dark:to-gray-900 p-4">
      <Card className="w-full max-w-md shadow-2xl border-border/60 backdrop-blur-sm">
        <CardHeader className="space-y-2 text-center">
          <div className="mx-auto w-12 h-12 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center mb-2">
            <Shield className="w-6 h-6 text-primary-600 dark:text-primary-400" />
          </div>
          <CardTitle className="text-2xl font-bold">{t('title')}</CardTitle>
          <CardDescription>{error ? t('failed') : t('description')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4 py-6">
          {error ? (
            <>
              <p className="text-sm text-destructive text-center px-2">{error}</p>
              <Button asChild variant="outline" className="w-full sm:w-auto">
                <Link href="/auth/login">{t('backToLogin')}</Link>
              </Button>
            </>
          ) : (
            <Loader2 className="w-8 h-8 animate-spin text-primary-600 dark:text-primary-400" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
