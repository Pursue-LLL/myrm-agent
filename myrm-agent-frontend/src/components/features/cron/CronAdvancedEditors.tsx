'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Timer, Hash, CalendarClock, Monitor, Bell, Archive, ShieldCheck, Link2, X, Code } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { EditorToggle } from './EditorToggle';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import type { CronJob, SessionTarget } from '@/services/cron';
import { updateCronJob } from '@/services/cron';
import useCronStore from '@/store/useCronStore';
import useChatStoreHook from '@/store/useChatStore';

interface EditorProps {
  job: CronJob;
  onUpdated: () => void;
}

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
    if (job.max_fires != null) setValue(job.max_fires);
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
        <EditorToggle enabled={enabled} onToggle={handleToggle} disabled={saving} />
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
    if (job.expires_at) setValue(job.expires_at.slice(0, 16));
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
    if (!value) return;
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
        <EditorToggle enabled={enabled} onToggle={handleToggle} disabled={saving} />
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

export function SessionTargetEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const chatHistoryItems = useChatStoreHook((s) => s.chatHistoryItems);
  const [value, setValue] = useState<SessionTarget>(job.session_target);
  const [chatId, setChatId] = useState(job.chat_id ?? '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setValue(job.session_target);
    setChatId(job.chat_id ?? '');
  }, [job.session_target, job.chat_id]);

  const handleTargetChange = async (v: string) => {
    const target = v as SessionTarget;
    setValue(target);
    setSaving(true);
    try {
      await updateCronJob(job.id, {
        session_target: target,
        ...(target === 'isolated' ? { chat_id: null } : {}),
      });
      onUpdated();
      toast.success(t('sessionTargetUpdated'));
    } catch {
      toast.error(t('actionFail'));
      setValue(job.session_target);
    } finally {
      setSaving(false);
    }
  };

  const handleChatChange = async (newChatId: string) => {
    setChatId(newChatId);
    setSaving(true);
    try {
      await updateCronJob(job.id, { chat_id: newChatId });
      onUpdated();
      toast.success(t('sessionTargetUpdated'));
    } catch {
      toast.error(t('actionFail'));
      setChatId(job.chat_id ?? '');
    } finally {
      setSaving(false);
    }
  };

  const boundChat = chatHistoryItems.find((c) => c.id === chatId);

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <Monitor className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('sessionTargetLabel')}</span>
      </div>
      <Select value={value} onValueChange={handleTargetChange} disabled={saving}>
        <SelectTrigger className="h-7 text-xs w-56">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="isolated">{t('sessionTargetIsolated')}</SelectItem>
          <SelectItem value="main">{t('sessionTargetMain')}</SelectItem>
        </SelectContent>
      </Select>
      <p className="text-[11px] text-muted-foreground">
        {value === 'isolated' ? t('sessionTargetIsolatedDesc') : t('sessionTargetMainDesc')}
      </p>
      {value === 'main' && (
        <Select value={chatId} onValueChange={handleChatChange} disabled={saving}>
          <SelectTrigger className="h-7 text-xs">
            <SelectValue placeholder={t('sessionTargetSelectChat')}>
              {boundChat ? boundChat.title : chatId ? chatId.slice(0, 12) : t('sessionTargetSelectChat')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent className="max-h-[200px]">
            {chatHistoryItems.map((chat) => (
              <SelectItem key={chat.id} value={chat.id}>
                <span className="truncate">{chat.title}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}

export function FailureAlertEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const existing = job.failure_alert;
  const isEnabled = existing !== false && existing !== null && existing !== undefined;
  const [enabled, setEnabled] = useState(isEnabled);
  const [after, setAfter] = useState(isEnabled && existing ? existing.after : 3);
  const [cooldown, setCooldown] = useState(isEnabled && existing ? existing.cooldown_seconds : 3600);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const on = job.failure_alert !== false && job.failure_alert != null;
    setEnabled(on);
    if (on && job.failure_alert && typeof job.failure_alert === 'object') {
      setAfter(job.failure_alert.after);
      setCooldown(job.failure_alert.cooldown_seconds);
    }
  }, [job.failure_alert]);

  const handleToggle = async () => {
    if (enabled) {
      setSaving(true);
      try {
        await updateCronJob(job.id, { failure_alert: false });
        setEnabled(false);
        onUpdated();
        toast.success(t('failureAlertCleared'));
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
      await updateCronJob(job.id, {
        failure_alert: { enabled: true, after, cooldown_seconds: cooldown },
      });
      onUpdated();
      toast.success(t('failureAlertUpdated'));
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
          <Bell className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('failureAlertLabel')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} disabled={saving} />
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">{t('failureAlertDesc')}</p>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground whitespace-nowrap">{t('failureAlertAfter')}</span>
              <Input
                type="number"
                min={1}
                max={100}
                value={after}
                onChange={(e) => setAfter(Number(e.target.value))}
                className="h-7 text-xs w-16"
              />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground whitespace-nowrap">{t('failureAlertCooldown')}</span>
              <Input
                type="number"
                min={0}
                value={cooldown}
                onChange={(e) => setCooldown(Number(e.target.value))}
                className="h-7 text-xs w-20"
              />
            </div>
            <Button size="sm" className="h-7 text-xs ml-auto" onClick={handleSave} disabled={saving}>
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
        <EditorToggle enabled={enabled} onToggle={handleToggle} disabled={saving} />
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

export function ContextFromEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const allJobs = useCronStore((s) => s.jobs);
  const [selected, setSelected] = useState<string[]>(job.context_from ?? []);
  const [saving, setSaving] = useState(false);

  useEffect(() => setSelected(job.context_from ?? []), [job.context_from]);

  const candidates = allJobs.filter((j) => j.id !== job.id && !selected.includes(j.id));

  const handleAdd = (id: string) => setSelected((prev) => [...prev, id]);
  const handleRemove = (id: string) => setSelected((prev) => prev.filter((x) => x !== id));

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCronJob(job.id, { context_from: selected });
      onUpdated();
      toast.success(t('contextFromUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  const nameOf = (id: string) => allJobs.find((j) => j.id === id)?.name ?? id;

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <Link2 className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('contextFromLabel')}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('contextFromDesc')}</p>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-300 border-teal-200 dark:border-teal-800"
            >
              {nameOf(id)}
              <button onClick={() => handleRemove(id)} className="hover:text-destructive transition-colors">
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        {candidates.length > 0 && (
          <Select onValueChange={handleAdd} value="">
            <SelectTrigger className="h-7 text-xs flex-1">
              <SelectValue placeholder={t('contextFromSelectPlaceholder')} />
            </SelectTrigger>
            <SelectContent>
              {candidates.map((j) => (
                <SelectItem key={j.id} value={j.id}>
                  {j.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Button size="sm" className="h-7 text-xs ml-auto" onClick={handleSave} disabled={saving}>
          {t('save')}
        </Button>
      </div>
    </div>
  );
}

export function PreConditionEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [enabled, setEnabled] = useState(job.pre_condition_script != null);
  const [value, setValue] = useState(job.pre_condition_script ?? '');
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    setEnabled(job.pre_condition_script != null);
    if (job.pre_condition_script != null) setValue(job.pre_condition_script);
  }, [job.pre_condition_script]);

  const handleToggle = async () => {
    if (enabled) {
      setSaving(true);
      try {
        await updateCronJob(job.id, { pre_condition_script: null });
        setEnabled(false);
        onUpdated();
        toast.success('Pre-flight probe disabled');
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
      await updateCronJob(job.id, { pre_condition_script: value });
      onUpdated();
      toast.success('Pre-flight probe updated');
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      // In a real implementation, this would call an AI endpoint.
      // For now, we provide a template.
      setValue(
        `import requests\nimport json\n\n# Example: Fetch data and skip if unchanged\n# response = requests.get("https://api.example.com/data")\n# if response.json().get("status") == "unchanged":\n#     print("[SKIP]")\n# else:\n#     print(response.text)`,
      );
      toast.success('Template generated');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Code className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">Pre-flight Probe (Python)</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} disabled={saving} />
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">
            Execute a sandboxed Python script before the job runs. Print <code>[SKIP]</code> or{' '}
            <code>&#123;"action": "skip"&#125;</code> to abort execution and save tokens. Other outputs will be injected
            as context.
          </p>
          <div className="space-y-2">
            <div className="relative">
              <Textarea
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="min-h-[120px] font-mono text-[11px] resize-y bg-muted/30"
                placeholder="import requests..."
              />
              <Button
                size="sm"
                variant="secondary"
                className="absolute top-2 right-2 h-6 px-2 text-[10px] gap-1 bg-background/80 backdrop-blur-sm"
                onClick={handleGenerate}
                disabled={generating || saving}
              >
                <IconGlow className="h-3 w-3 text-amber-500" />
                AI Generate
              </Button>
            </div>
            <div className="flex justify-end">
              <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
                {t('save')}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
