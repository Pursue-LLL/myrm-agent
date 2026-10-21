'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import AppLayout from '@/components/layout/AppLayout';
import EvalLabDashboard from '@/components/features/eval-lab/EvalLabDashboard';

export default function EvalLabPage() {
  const t = useTranslations('evalLab');

  return (
    <AppLayout>
      <div className="h-full flex flex-col p-6 max-w-7xl mx-auto space-y-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">{t('pageTitle')}</h1>
          <p className="text-muted-foreground text-sm">{t('pageDescription')}</p>
        </div>

        <EvalLabDashboard />
      </div>
    </AppLayout>
  );
}
