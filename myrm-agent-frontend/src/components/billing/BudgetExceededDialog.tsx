'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Button } from '@/components/primitives/button';
import { useBudgetExceededStore } from '@/store/useBudgetExceededStore';
import { isSandbox } from '@/lib/deploy-mode';
import useAuthStore from '@/store/useAuthStore';
import { useSubscription } from '@/hooks/useSubscription';
import { toast } from '@/lib/utils/toast';

export default function BudgetExceededDialog() {
  const t = useTranslations('billing.exceeded');
  const pricingT = useTranslations('billing.pricing');
  const { open, requiredWu, availableWu, close } = useBudgetExceededStore();
  const { token } = useAuthStore();
  const { isPaidPlan } = useSubscription();
  const [topupLoading, setTopupLoading] = useState(false);

  if (!isSandbox()) {
    return null;
  }

  const handleTopup = async () => {
    setTopupLoading(true);
    try {
      const authToken = token || localStorage.getItem('auth_token');
      const response = await fetch('/api/topup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ amount_usd: 5 }),
      });
      if (!response.ok) {
        toast.error(pricingT('checkoutFailed'));
        return;
      }
      const data = (await response.json()) as { checkoutUrl?: string };
      if (data.checkoutUrl) {
        window.location.href = data.checkoutUrl;
      }
    } catch {
      toast.error(pricingT('checkoutFailed'));
    } finally {
      setTopupLoading(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={(next) => (!next ? close() : undefined)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('description', {
              required: requiredWu ?? 0,
              available: availableWu ?? 0,
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('dismiss')}</AlertDialogCancel>
          {isPaidPlan && (
            <Button variant="outline" disabled={topupLoading} onClick={handleTopup}>
              {topupLoading ? pricingT('processing') : t('topup')}
            </Button>
          )}
          <AlertDialogAction asChild>
            <Link href="/pricing" onClick={close}>
              {t('upgrade')}
            </Link>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
