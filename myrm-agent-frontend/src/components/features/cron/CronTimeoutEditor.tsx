'use client';

/**
 * [INPUT]
 * @/services/cron::updateCronJob (POS: Frontend Cron API client)
 * ./cron-utils::CRON_TIMEOUT_*, parseTimeoutSeconds (POS: Cron pure helpers; the accepted range mirrors the server schema)
 * ./CronDeliveryEditors::EditorProps (POS: Cron per-job editor shared props)
 *
 * [OUTPUT]
 * TimeoutInput: Whole-seconds input; the accepted range is its hint and its accessible description. Shared by the editor and the create dialog.
 * CronTimeoutEditor: Per-job editor for the run time limit.
 *
 * [POS]
 * CronRunHistory per-job surface. A run over the limit is stopped and not retried, so the limit is the lever
 * for a job that legitimately takes long.
 */

import { useEffect, useId, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Hourglass } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import { updateCronJob } from '@/services/cron';
import {
  CRON_TIMEOUT_DEFAULT_SECONDS,
  CRON_TIMEOUT_MAX_SECONDS,
  CRON_TIMEOUT_MIN_SECONDS,
  parseTimeoutSeconds,
} from './cron-utils';
import type { EditorProps } from './CronDeliveryEditors';

interface TimeoutInputProps {
  value: string;
  onChange: (value: string) => void;
  invalid: boolean;
  disabled?: boolean;
}

export function TimeoutInput({ value, onChange, invalid, disabled }: TimeoutInputProps) {
  const t = useTranslations('cron');
  const hintId = useId();
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Input
          type="number"
          inputMode="numeric"
          min={CRON_TIMEOUT_MIN_SECONDS}
          max={CRON_TIMEOUT_MAX_SECONDS}
          step={1}
          value={value}
          placeholder={String(CRON_TIMEOUT_DEFAULT_SECONDS)}
          onChange={(e) => onChange(e.target.value)}
          aria-label={t('timeoutLabel')}
          aria-invalid={invalid}
          aria-describedby={hintId}
          disabled={disabled}
          className={cn('h-7 text-xs w-24', invalid && 'border-destructive focus-visible:ring-destructive/30')}
        />
        <span className="text-xs text-muted-foreground">s</span>
      </div>
      <p id={hintId} className={cn('text-[11px]', invalid ? 'text-destructive' : 'text-muted-foreground')}>
        {t('timeoutRangeHint', { min: String(CRON_TIMEOUT_MIN_SECONDS), max: String(CRON_TIMEOUT_MAX_SECONDS) })}
      </p>
    </div>
  );
}

export function CronTimeoutEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [value, setValue] = useState(String(job.timeout_seconds));
  const [saving, setSaving] = useState(false);

  useEffect(() => setValue(String(job.timeout_seconds)), [job.timeout_seconds]);

  const seconds = parseTimeoutSeconds(value);
  const canSave = seconds !== null && seconds !== job.timeout_seconds && !saving;

  const handleSave = async () => {
    if (seconds === null) {
      return;
    }
    setSaving(true);
    try {
      await updateCronJob(job.id, { timeout_seconds: seconds });
      onUpdated();
      toast.success(t('timeoutUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <Hourglass className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('timeoutLabel')}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('timeoutDesc')}</p>
      <div className="flex items-start gap-2">
        <TimeoutInput value={value} onChange={setValue} invalid={seconds === null} disabled={saving} />
        <Button size="sm" className="h-7 text-xs ml-auto" onClick={handleSave} disabled={!canSave}>
          {t('save')}
        </Button>
      </div>
    </div>
  );
}
