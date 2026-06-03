'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BarChart3, RotateCcw, Info } from 'lucide-react';
import { EditorToggle } from './EditorToggle';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import type { CronJob } from '@/services/cron';
import { updateCronJob, resetMonitorBaseline } from '@/services/cron';

interface EditorProps {
  job: CronJob;
  onUpdated: () => void;
}

export function IncrementalMonitorEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const existing = job.monitor_config;
  const [enabled, setEnabled] = useState(existing?.enabled ?? false);
  const [ttlDays, setTtlDays] = useState(existing?.ttl_days ?? 30);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    if (job.monitor_config) {
      setEnabled(job.monitor_config.enabled ?? false);
      setTtlDays(job.monitor_config.ttl_days ?? 30);
    }
  }, [job.monitor_config]);

  const isRecentReset = useMemo(() => {
    if (!job.monitor_config?.last_reset_at) return false;
    const resetTime = new Date(job.monitor_config.last_reset_at).getTime();
    const now = Date.now();
    return now - resetTime < 3600000;
  }, [job.monitor_config?.last_reset_at]);

  const handleToggle = async () => {
    setSaving(true);
    try {
      if (enabled) {
        await updateCronJob(job.id, { monitor_config: null });
        setEnabled(false);
        toast.success(t('monitorDisabled'));
      } else {
        await updateCronJob(job.id, {
          monitor_config: { monitor_type: 'set', ttl_days: ttlDays, enabled: true },
        });
        setEnabled(true);
        toast.success(t('monitorEnabled'));
      }
      onUpdated();
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  const handleTtlSave = async () => {
    if (!enabled) return;
    setSaving(true);
    try {
      await updateCronJob(job.id, {
        monitor_config: { monitor_type: 'set', ttl_days: ttlDays, enabled: true },
      });
      onUpdated();
      toast.success(t('monitorTtlUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      await resetMonitorBaseline(job.id);
      onUpdated();
      toast.success(t('monitorBaselineReset'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <BarChart3 className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('incrementalMonitorLabel')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} disabled={saving} />
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('incrementalMonitorDesc')}</p>
          {isRecentReset && job.monitor_config?.last_reset_reason && (
            <div className="rounded-full bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-900 p-2 text-xs flex items-start gap-1.5">
              <Info className="h-3 w-3 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
              <span className="text-blue-900 dark:text-blue-100">
                {t('baselineAutoReset', {
                  reason: t(`resetReason.${job.monitor_config.last_reset_reason}`),
                })}
              </span>
            </div>
          )}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              {[7, 30, 90].map((days) => (
                <button
                  key={days}
                  onClick={async () => {
                    const prevTtl = ttlDays;
                    setTtlDays(days);
                    setSaving(true);
                    try {
                      await updateCronJob(job.id, {
                        monitor_config: { monitor_type: 'set', ttl_days: days, enabled: true },
                      });
                      onUpdated();
                      toast.success(t('monitorTtlUpdated'));
                    } catch {
                      setTtlDays(prevTtl);
                      toast.error(t('actionFail'));
                    } finally {
                      setSaving(false);
                    }
                  }}
                  disabled={saving}
                  className={cn(
                    'h-6 px-2 rounded text-xs font-medium transition-colors',
                    ttlDays === days
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted hover:bg-muted/80 text-muted-foreground',
                  )}
                >
                  {days}
                  {t('daysShort')}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground whitespace-nowrap">{t('monitorTtlLabel')}</span>
              <Input
                type="number"
                min={1}
                max={365}
                value={ttlDays}
                onChange={(e) => setTtlDays(Number(e.target.value))}
                className="h-7 text-xs w-20"
              />
              <span className="text-xs text-muted-foreground">{t('days')}</span>
              <Button size="sm" className="h-7 text-xs ml-auto" onClick={handleTtlSave} disabled={saving}>
                {t('save')}
              </Button>
            </div>
          </div>
          <Button size="sm" variant="outline" className="h-7 text-xs w-full" onClick={handleReset} disabled={resetting}>
            <RotateCcw className="h-3 w-3 mr-1" />
            {t('resetBaseline')}
          </Button>
        </>
      )}
    </div>
  );
}
