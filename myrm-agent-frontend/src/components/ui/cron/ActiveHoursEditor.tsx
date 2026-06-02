'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { SunMoon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import type { ActiveHours, CronJob } from '@/services/cron';
import { updateCronJob } from '@/services/cron';
import useConfigStore from '@/store/useConfigStore';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';

interface ActiveHoursEditorProps {
  job: CronJob;
  onUpdated: () => void;
}

export function ActiveHoursEditor({ job, onUpdated }: ActiveHoursEditorProps) {
  const t = useTranslations('cron');
  const globalTz = useConfigStore((s) => s.personalSettings?.timezone) || getBrowserTimezone();
  const existing = job.active_hours;
  const [enabled, setEnabled] = useState(!!existing);
  const [start, setStart] = useState(existing?.start ?? '09:00');
  const [end, setEnd] = useState(existing?.end ?? '21:00');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setEnabled(!!job.active_hours);
    if (job.active_hours) {
      setStart(job.active_hours.start);
      setEnd(job.active_hours.end);
    }
  }, [job.active_hours]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: ActiveHours | null = enabled ? { start, end, tz: globalTz } : null;
      await updateCronJob(job.id, { active_hours: payload });
      onUpdated();
      toast.success(enabled ? t('activeHoursUpdated') : t('activeHoursCleared'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async () => {
    if (enabled) {
      setSaving(true);
      try {
        await updateCronJob(job.id, { active_hours: null });
        setEnabled(false);
        onUpdated();
        toast.success(t('activeHoursCleared'));
      } catch {
        toast.error(t('actionFail'));
      } finally {
        setSaving(false);
      }
    } else {
      setEnabled(true);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <SunMoon className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('activeHoursLabel')}</span>
        </div>
        <button
          onClick={handleToggle}
          disabled={saving}
          className={cn(
            'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
            enabled ? 'bg-accent-warm' : 'bg-muted',
          )}
        >
          <span
            className={cn(
              'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform',
              enabled ? 'translate-x-4.5' : 'translate-x-0.5',
            )}
          />
        </button>
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('activeHoursDesc')}</p>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1">
              <label className="text-[11px] text-muted-foreground">{t('activeHoursStart')}</label>
              <input
                type="time"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="h-7 rounded-full border bg-background px-2 text-xs"
              />
            </div>
            <span className="text-muted-foreground text-xs">–</span>
            <div className="flex items-center gap-1">
              <label className="text-[11px] text-muted-foreground">{t('activeHoursEnd')}</label>
              <input
                type="time"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="h-7 rounded-full border bg-background px-2 text-xs"
              />
            </div>
            <span className="h-7 rounded-full border bg-muted/50 px-2 text-xs flex items-center text-muted-foreground font-mono">
              {globalTz}
            </span>
            <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
              {t('save')}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
