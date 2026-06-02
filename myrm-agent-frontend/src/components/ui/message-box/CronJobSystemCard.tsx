'use client';

import { memo } from 'react';
import { useRouter } from 'next/navigation';
import { Timer, CheckCircle2, Clock, Cpu, Calendar, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslations } from 'next-intl';

export interface CronJobResult {
  status: string;
  action: 'add' | 'update';
  job_id: string;
  name: string;
  job_type: string;
  model: string | null;
  schedule: string;
  next_run: string;
}

function InfoRow({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 text-sm">
      <span className="text-muted-foreground shrink-0">{icon}</span>
      <span className="text-muted-foreground shrink-0 w-16">{label}</span>
      <span className="font-medium truncate">{children}</span>
    </div>
  );
}

export const CronJobSystemCard = memo<{ result: CronJobResult }>(({ result }) => {
  const t = useTranslations('cron');
  const router = useRouter();

  return (
    <div className="mt-3 mb-1 overflow-hidden rounded-xl border bg-card text-card-foreground max-w-md">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-4 py-2.5">
        <Timer className="h-4 w-4 text-primary" />
        <span className="font-semibold text-sm">{result.action === 'add' ? t('taskCreated') : t('taskUpdated')}</span>
        <div className="ml-auto flex items-center gap-1 text-[11px] text-green-600 dark:text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full">
          <CheckCircle2 className="h-3 w-3" />
          <span>{t('success')}</span>
        </div>
      </div>

      <div className="px-4 py-3 space-y-2">
        <InfoRow icon={<Timer className="h-3.5 w-3.5" />} label={t('taskName')}>
          {result.name}
        </InfoRow>
        <InfoRow icon={<Calendar className="h-3.5 w-3.5" />} label={t('schedule')}>
          <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">{result.schedule}</code>
        </InfoRow>
        <InfoRow icon={<Clock className="h-3.5 w-3.5" />} label={t('nextRun')}>
          {result.next_run}
        </InfoRow>
        {result.model && (
          <InfoRow icon={<Cpu className="h-3.5 w-3.5" />} label={t('columnModel')}>
            <span className="text-xs bg-muted px-1.5 py-0.5 rounded">{result.model.split('/').pop()}</span>
          </InfoRow>
        )}
      </div>

      <div className="border-t bg-muted/20 px-4 py-2.5 flex items-center justify-end">
        <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" onClick={() => router.push('/settings/cron')}>
          <Settings2 className="h-3 w-3" />
          {t('openDashboard')}
        </Button>
      </div>
    </div>
  );
});

CronJobSystemCard.displayName = 'CronJobSystemCard';
