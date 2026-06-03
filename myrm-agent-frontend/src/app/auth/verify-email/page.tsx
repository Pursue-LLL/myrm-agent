'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import SandboxAuthLayout from '@/components/auth/SandboxAuthLayout';
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
          await login(data.token, userId ? { id: userId, email } : undefined);
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
  }, [token, t, login]);

  return (
    <SandboxAuthLayout>
      <div className="space-y-6 text-center py-2">
        <div className="mx-auto w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
          {status === 'loading' && <Loader2 className="w-6 h-6 animate-spin text-primary" />}
          {status === 'error' && <AlertCircle className="w-6 h-6 text-destructive" />}
          {status === 'success' && (
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_12px_color-mix(in_srgb,#10b981_50%,transparent)]" />
          )}
        </div>
        <header className="space-y-2">
          <h2 className="text-2xl font-semibold tracking-tight text-foreground">{t('title')}</h2>
          <p className="text-sm text-muted-foreground leading-relaxed">{message || t('description')}</p>
        </header>
        {status === 'error' && (
          <Button variant="outline" className="w-full h-11" onClick={() => router.push('/auth/login')}>
            {t('backToLogin')}
          </Button>
        )}
      </div>
    </SandboxAuthLayout>
  );
}
