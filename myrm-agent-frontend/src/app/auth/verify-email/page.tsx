'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Loading03Icon, Mail01Icon, AlertCircleIcon } from 'hugeicons-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import useAuthStore from '@/store/useAuthStore';

export default function VerifyEmailPage() {
  const t = useTranslations('auth.verifyEmail');
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useAuthStore((s) => s.login);
  const token = searchParams.get('token');
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    if (!token) {
      setStatus('error');
      setMessage(t('missingToken'));
      return;
    }
    processedRef.current = true;

    async function verify() {
      try {
        const response = await fetch(
          `${resolveCpBaseUrl()}/api/auth/verify-email?token=${encodeURIComponent(token ?? '')}`,
        );
        const data = await response.json();
        if (!response.ok) {
          setStatus('error');
          setMessage(data.detail || t('failed'));
          return;
        }
        if (data.token) {
          const userId = typeof data.user_id === 'string' ? data.user_id : undefined;
          const email = typeof data.email === 'string' ? data.email : '';
          await login(
            data.token,
            userId ? { id: userId, email } : undefined,
          );
        }
        setStatus('success');
        setMessage(t('success'));
        setTimeout(() => {
          window.location.href = '/';
        }, 1500);
      } catch {
        setStatus('error');
        setMessage(t('failed'));
      }
    }

    void verify();
  }, [token, t, router, login]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-background to-primary-50 dark:from-gray-900 dark:via-background dark:to-gray-900 p-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader className="space-y-2 text-center">
          <div className="mx-auto w-12 h-12 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center mb-2">
            {status === 'loading' && <Loading03Icon className="w-6 h-6 animate-spin text-primary-600" />}
            {status === 'success' && <Mail01Icon className="w-6 h-6 text-emerald-600" />}
            {status === 'error' && <AlertCircleIcon className="w-6 h-6 text-destructive" />}
          </div>
          <CardTitle className="text-2xl font-bold">{t('title')}</CardTitle>
          <CardDescription>{message || t('description')}</CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center">
          {status === 'error' && (
            <Button variant="outline" onClick={() => router.push('/auth/login')}>
              {t('backToLogin')}
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
