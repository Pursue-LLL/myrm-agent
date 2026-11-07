'use client';

/**
 * [INPUT] ./CronDeliveryEditors::EditorProps (POS: 任务详情编辑器共用 props), @/services/cron::updateCronJob (POS: 任务字段更新)
 * [OUTPUT] CooldownEditor / MaxFiresEditor / ExpiresAtEditor / SkipIfActiveEditor / RunRetentionEditor: 冷却时间、最大执行次数、过期时间、重叠跳过与运行记录保留的编辑器
 * [POS] 任务详情里限定执行频率与生命周期的几项高级选项，各自保存到 per-job 字段。
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Timer, Hash, CalendarClock, Archive, ShieldCheck } from 'lucide-react';
import { EditorToggle } from './EditorToggle';
import type { EditorProps } from './CronDeliveryEditors';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import { updateCronJob } from '@/services/cron';

export function CooldownEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [value, setValue] = useState(job.cooldown_seconds);
  const [saving, setSaving] = useState(false);

  useEffect(() => setValue(job.cooldown_seconds), [job.cooldown_seconds]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCronJob(job.id, { cooldown_seconds: value });
      onUpdated();
      toast.success(t('cooldownUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <Timer className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('cooldownLabel')}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('cooldownDesc')}</p>
      <div className="flex items-center gap-2">
        <Input
          type="number"
          min={0}
          max={86400}
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
          className="h-7 text-xs w-24"
        />
        <span className="text-xs text-muted-foreground">s</span>
        <Button size="sm" className="h-7 text-xs ml-auto" onClick={handleSave} disabled={saving}>
          {t('save')}
        </Button>
      </div>
    </div>
  );
}

export function MaxFiresEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [enabled, setEnabled] = useState(job.max_fires != null);
  const [value, setValue] = useState(job.max_fires ?? 100);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setEnabled(job.max_fires != null);
    if (job.max_fires != null) {
      setValue(job.max_fires);
    }
  }, [job.max_fires]);

  const handleToggle = async () => {
    if (enabled) {
      setSaving(true);
      try {
        await updateCronJob(job.id, { max_fires: null });
        setEnabled(false);
        onUpdated();
        toast.success(t('maxFiresCleared'));
      } catch {
        toast.error(t('actionFail'));
      } finally {
        setSaving(false);
      }
    } else {
      setEnabled(true);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCronJob(job.id, { max_fires: value });
      onUpdated();
      toast.success(t('maxFiresUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Hash className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('maxFiresLabel')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} label={t('maxFiresLabel')} disabled={saving} />
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('maxFiresDesc')}</p>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={1}
              value={value}
              onChange={(e) => setValue(Number(e.target.value))}
              className="h-7 text-xs w-24"
            />
            {job.fire_count > 0 && (
              <span className="text-[11px] text-muted-foreground">
                {t('fireCountValue', { count: String(job.fire_count), max: String(value) })}
              </span>
            )}
            <Button size="sm" className="h-7 text-xs ml-auto" onClick={handleSave} disabled={saving}>
              {t('save')}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export function ExpiresAtEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [enabled, setEnabled] = useState(job.expires_at != null);
  const [value, setValue] = useState(job.expires_at?.slice(0, 16) ?? '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setEnabled(job.expires_at != null);
    if (job.expires_at) {
      setValue(job.expires_at.slice(0, 16));
    }
  }, [job.expires_at]);

  const handleToggle = async () => {
    if (enabled) {
      setSaving(true);
      try {
        await updateCronJob(job.id, { expires_at: null });
        setEnabled(false);
        onUpdated();
        toast.success(t('expiresAtCleared'));
      } catch {
        toast.error(t('actionFail'));
      } finally {
        setSaving(false);
      }
    } else {
      setEnabled(true);
    }
  };

  const handleSave = async () => {
    if (!value) {
      return;
    }
    setSaving(true);
    try {
      await updateCronJob(job.id, { expires_at: new Date(value).toISOString() });
      onUpdated();
      toast.success(t('expiresAtUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <CalendarClock className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('expiresAtLabel')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} label={t('expiresAtLabel')} disabled={saving} />
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('expiresAtDesc')}</p>
          <div className="flex items-center gap-2">
            <Input
              type="datetime-local"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="h-7 text-xs flex-1"
            />
            <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving || !value}>
              {t('save')}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export function SkipIfActiveEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [enabled, setEnabled] = useState(job.skip_if_active);
  const [saving, setSaving] = useState(false);

  useEffect(() => setEnabled(job.skip_if_active), [job.skip_if_active]);

  const handleToggle = async () => {
    const next = !enabled;
    setEnabled(next);
    setSaving(true);
    try {
      await updateCronJob(job.id, { skip_if_active: next });
      onUpdated();
      toast.success(t(next ? 'skipIfActiveEnabled' : 'skipIfActiveDisabled'));
    } catch {
      setEnabled(!next);
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('skipIfActiveLabel')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} label={t('skipIfActiveLabel')} disabled={saving} />
      </div>
      <p className="text-[11px] text-muted-foreground">{t('skipIfActiveDesc')}</p>
    </div>
  );
}

export function RunRetentionEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [value, setValue] = useState(job.run_retention_days);
  const [saving, setSaving] = useState(false);

  useEffect(() => setValue(job.run_retention_days), [job.run_retention_days]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCronJob(job.id, { run_retention_days: value });
      onUpdated();
      toast.success(t('runRetentionUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <Archive className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('runRetentionLabel')}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('runRetentionDesc')}</p>
      <div className="flex items-center gap-2">
        {[7, 30, 90].map((days) => (
          <button
            key={days}
            onClick={async () => {
              const prev = value;
              setValue(days);
              setSaving(true);
              try {
                await updateCronJob(job.id, { run_retention_days: days });
                onUpdated();
                toast.success(t('runRetentionUpdated'));
              } catch {
                setValue(prev);
                toast.error(t('actionFail'));
              } finally {
                setSaving(false);
              }
            }}
            disabled={saving}
            className={cn(
              'h-6 px-2 rounded text-xs font-medium transition-colors',
              value === days
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted hover:bg-muted/80 text-muted-foreground',
            )}
          >
            {days}
            {t('daysShort')}
          </button>
        ))}
        <Input
          type="number"
          min={1}
          max={365}
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
          className="h-7 text-xs w-20"
        />
        <Button size="sm" className="h-7 text-xs ml-auto" onClick={handleSave} disabled={saving}>
          {t('save')}
        </Button>
      </div>
    </div>
  );
}
