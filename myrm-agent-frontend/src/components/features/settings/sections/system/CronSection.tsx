'use client';

import { lazy, Suspense, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconClock } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Skeleton } from '@/components/primitives/skeleton';
import CronJobList from '@/components/features/cron/CronJobList';
import CronRunHistory from '@/components/features/cron/CronRunHistory';
import GlobalRunHistory from '@/components/features/cron/GlobalRunHistory';
import HeartbeatSection from './HeartbeatSection';
import CronEntitlementGate from '@/components/billing/CronEntitlementGate';
import type { CronJob } from '@/services/cron';

const CronUsageStats = lazy(() => import('@/components/features/cron/CronUsageStats'));

type View = 'list' | 'history' | 'global' | 'stats';

const TOP_TABS = ['list', 'global', 'stats'] as const;
const TAB_KEYS: Record<string, string> = {
  list: 'tabJobs',
  global: 'tabAllRuns',
  stats: 'tabStats',
};

export default function CronSection() {
  const t = useTranslations('cron');
  const [view, setView] = useState<View>('list');
  const [selectedJob, setSelectedJob] = useState<CronJob | null>(null);

  const isTopLevel = view !== 'history';

  return (
    <div className="space-y-5">
      <HeartbeatSection />

      <div>
        <div className="flex items-center gap-2 mb-1">
          <IconClock className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-base font-semibold">{t('sectionTitle')}</h2>
        </div>
        <p className="text-sm text-muted-foreground">{t('sectionDesc')}</p>
        <p className="text-sm text-muted-foreground/90 mt-2">{t('agentChatHint')}</p>
      </div>

      {isTopLevel && (
        <CronEntitlementGate>
          <div className="flex gap-1 border-b pb-0">
            {TOP_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setView(tab)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium border-b-2 -mb-px transition-colors',
                  view === tab
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {t(TAB_KEYS[tab])}
              </button>
            ))}
          </div>

          {view === 'list' && (
            <CronJobList
              onSelectJob={(job) => {
                setSelectedJob(job);
                setView('history');
              }}
            />
          )}

          {view === 'global' && <GlobalRunHistory />}

          {view === 'stats' && (
            <Suspense fallback={<Skeleton className="h-96 rounded-lg" />}>
              <CronUsageStats />
            </Suspense>
          )}
        </CronEntitlementGate>
      )}

      {view === 'history' && selectedJob && (
        <CronRunHistory
          job={selectedJob}
          onBack={() => {
            setSelectedJob(null);
            setView('list');
          }}
        />
      )}
    </div>
  );
}
