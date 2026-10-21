'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';

export default function PaymentCancelPage() {
  const t = useTranslations('pricing.payment.cancel');

  return (
    <div className="flex min-h-screen items-center justify-center px-6" style={{ background: 'var(--background)' }}>
      <div className="mx-auto max-w-md text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <svg className="h-8 w-8 text-destructive" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="mt-3 text-sm text-muted-foreground">{t('description')}</p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Button asChild className="rounded-full">
            <Link href="/pricing">{t('tryAgain')}</Link>
          </Button>
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/">{t('backToHome')}</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
