'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Monitor, Bell, Link2, X, Code } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { EditorToggle } from './EditorToggle';
import type { EditorProps } from './CronDeliveryEditors';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { toast } from 'sonner';
import type { SessionTarget } from '@/services/cron';
import { updateCronJob } from '@/services/cron';
import useCronStore from '@/store/useCronStore';
import useChatStoreHook from '@/store/useChatStore';

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
        ...(target !== 'main' ? { chat_id: null } : {}),
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
          <SelectItem value="daily">{t('sessionTargetDaily')}</SelectItem>
          <SelectItem value="main">{t('sessionTargetMain')}</SelectItem>
        </SelectContent>
      </Select>
      <p className="text-[11px] text-muted-foreground">
        {value === 'daily'
          ? t('sessionTargetDailyDesc')
          : value === 'main'
            ? t('sessionTargetMainDesc')
            : t('sessionTargetIsolatedDesc')}
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
        <EditorToggle enabled={enabled} onToggle={handleToggle} label={t('failureAlertLabel')} disabled={saving} />
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
              <button onClick={() => handleRemove(id)} className="hover:text-destructive-text transition-colors">
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

  useEffect(() => {
    setEnabled(job.pre_condition_script != null);
    if (job.pre_condition_script != null) {
      setValue(job.pre_condition_script);
    }
  }, [job.pre_condition_script]);

  const handleToggle = async () => {
    if (enabled) {
      setSaving(true);
      try {
        await updateCronJob(job.id, { pre_condition_script: null });
        setEnabled(false);
        onUpdated();
        toast.success(t('preflightDisabled'));
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
      toast.success(t('preflightUpdated'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  const handleInsertTemplate = () => {
    setValue(
      `import requests\nimport json\n\n# Example: Fetch data and skip if unchanged\n# response = requests.get("https://api.example.com/data")\n# if response.json().get("status") == "unchanged":\n#     print("[SKIP]")\n# else:\n#     print(response.text)`,
    );
    toast.success(t('preflightTemplateInserted'));
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Code className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">{t('preflightProbe')}</span>
        </div>
        <EditorToggle enabled={enabled} onToggle={handleToggle} label={t('preflightProbe')} disabled={saving} />
      </div>
      {enabled && (
        <>
          <p className="text-[11px] text-muted-foreground">
            {t.rich('preflightDesc', {
              skip: () => <code>[SKIP]</code>,
              action: () => <code>{'{"action": "skip"}'}</code>,
            })}
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
                onClick={handleInsertTemplate}
                disabled={saving}
              >
                <IconGlow className="h-3 w-3 text-amber-500" />
                {t('preflightInsertTemplate')}
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
