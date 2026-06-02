'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { Bot, Terminal, Plus, Loader2, Waypoints, Info, CalendarDays, Cpu, MessageCircle } from 'lucide-react';
import useAgentStore from '@/store/useAgentStore';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import useCronStore from '@/store/useCronStore';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import type { CronSchedule } from '@/services/cron';
import {
  estimateCronMonthlyExecutions,
  estimateIntervalMonthlyExecutions,
  formatMonthlyExecutions,
  getFrequencyRiskLevel,
} from '@/lib/utils/cronEstimate';

type JobType = 'agent' | 'shell' | 'router';
type ScheduleKind = 'cron' | 'interval' | 'once';

const TOGGLE_CLS =
  'gap-1.5 text-xs h-8 px-3 rounded-full border border-border bg-muted/50 data-[state=on]:bg-primary/10 data-[state=on]:text-primary data-[state=on]:border-primary/40';

interface CronJobCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  presetChatId?: string | null;
  presetChatTitle?: string | null;
}

export default function CronJobCreateDialog({
  open,
  onOpenChange,
  presetChatId,
  presetChatTitle,
}: CronJobCreateDialogProps) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const { createJob } = useCronStore();
  const userTz = useConfigStore((s) => s.personalSettings?.timezone) || getBrowserTimezone();

  const { agents, fetchAgents } = useAgentStore();
  const { defaultModelConfig } = useProviderStore();

  const [jobType, setJobType] = useState<JobType>('agent');
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [command, setCommand] = useState('');
  const [agentId, setAgentId] = useState('__default__');
  const [scheduleKind, setScheduleKind] = useState<ScheduleKind>('cron');
  const [cronExpr, setCronExpr] = useState('');
  const [intervalMinutes, setIntervalMinutes] = useState('');
  const [onceAt, setOnceAt] = useState('');
  const [saving, setSaving] = useState(false);
  const [sessionTarget, setSessionTarget] = useState<'isolated' | 'main'>(presetChatId ? 'main' : 'isolated');
  const [selectedChatId, setSelectedChatId] = useState<string>('');
  const chatHistoryItems = useChatStore((s) => s.chatHistoryItems);

  useEffect(() => {
    if (open) {
      fetchAgents();
      if (presetChatId) setSessionTarget('main');
    }
  }, [open, fetchAgents, presetChatId]);

  const reset = useCallback(() => {
    setJobType('agent');
    setName('');
    setPrompt('');
    setCommand('');
    setAgentId('__default__');
    setScheduleKind('cron');
    setCronExpr('');
    setIntervalMinutes('');
    setOnceAt('');
    setSessionTarget(presetChatId ? 'main' : 'isolated');
    setSelectedChatId('');
  }, [presetChatId]);

  const schedule = useMemo((): CronSchedule | null => {
    if (scheduleKind === 'cron') {
      const expr = cronExpr.trim();
      if (!expr) return null;
      return { kind: 'cron', expr, tz: userTz };
    }
    if (scheduleKind === 'interval') {
      const mins = parseInt(intervalMinutes, 10);
      if (!mins || mins < 5) return null;
      return { kind: 'interval', interval_ms: mins * 60_000, tz: userTz };
    }
    if (scheduleKind === 'once') {
      const at = onceAt.trim();
      if (!at) return null;
      const d = new Date(at);
      if (isNaN(d.getTime())) return null;
      return { kind: 'once', run_at: d.toISOString() };
    }
    return null;
  }, [scheduleKind, cronExpr, intervalMinutes, onceAt, userTz]);

  const monthlyExecutions = useMemo(() => {
    if (scheduleKind === 'cron') {
      const expr = cronExpr.trim();
      if (!expr) return null;
      return estimateCronMonthlyExecutions(expr);
    }
    if (scheduleKind === 'interval') {
      const mins = parseInt(intervalMinutes, 10);
      if (!mins || mins < 5) return null;
      return estimateIntervalMonthlyExecutions(mins * 60_000);
    }
    if (scheduleKind === 'once') {
      return 1;
    }
    return null;
  }, [scheduleKind, cronExpr, intervalMinutes]);

  const defaultModel = useMemo(() => {
    const primary = defaultModelConfig.baseModel.primary;
    if (!primary) return null;
    return { providerId: primary.providerId, model: primary.model };
  }, [defaultModelConfig]);

  const effectiveChatId = presetChatId || selectedChatId || null;
  const contentValid =
    jobType === 'agent' ? prompt.trim().length > 0 : jobType === 'shell' ? command.trim().length > 0 : true;
  const sessionValid = sessionTarget === 'isolated' || effectiveChatId !== null;
  const canSubmit = contentValid && schedule !== null && sessionValid;

  const handleSubmit = useCallback(async () => {
    if (!canSubmit || !schedule) return;
    setSaving(true);
    try {
      const taskName = name.trim() || (jobType === 'agent' ? prompt.trim().slice(0, 30) : command.trim().slice(0, 30));
      await createJob({
        name: taskName,
        job_type: jobType,
        schedule,
        ...(jobType === 'agent' ? { prompt: prompt.trim() } : { command: command.trim() }),
        ...(jobType === 'agent' && agentId !== '__default__' ? { agent_id: agentId } : {}),
        session_target: sessionTarget,
        ...(sessionTarget === 'main' && effectiveChatId ? { chat_id: effectiveChatId } : {}),
      });
      toast.success(t('createSuccess'));
      reset();
      onOpenChange(false);
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  }, [
    canSubmit,
    schedule,
    name,
    jobType,
    prompt,
    command,
    agentId,
    sessionTarget,
    effectiveChatId,
    createJob,
    t,
    reset,
    onOpenChange,
  ]);

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            {t('createTitle')}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* Job Type */}
          <div className="space-y-1.5">
            <Label className="text-xs">{t('createTypeLabel')}</Label>
            <ToggleGroup
              type="single"
              value={jobType}
              onValueChange={(v) => v && setJobType(v as JobType)}
              className="justify-start"
            >
              <ToggleGroupItem value="agent" className={TOGGLE_CLS}>
                <Bot className="h-3.5 w-3.5" />
                {t('jobTypeAgent')}
              </ToggleGroupItem>
              <ToggleGroupItem value="shell" className={TOGGLE_CLS}>
                <Terminal className="h-3.5 w-3.5" />
                {t('jobTypeShell')}
              </ToggleGroupItem>
              <ToggleGroupItem value="router" className={TOGGLE_CLS}>
                <Waypoints className="h-3.5 w-3.5" />
                Router
              </ToggleGroupItem>
            </ToggleGroup>
          </div>

          {/* Name */}
          <div className="space-y-1.5">
            <Label className="text-xs">{t('createNameLabel')}</Label>
            <Input
              placeholder={t('createNamePlaceholder')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-8 text-sm"
            />
          </div>

          {/* Content */}
          {jobType !== 'router' && (
            <div className="space-y-1.5">
              <Label className="text-xs">
                {jobType === 'agent' ? t('createPromptLabel') : t('createCommandLabel')}
              </Label>
              {jobType === 'agent' ? (
                <Textarea
                  placeholder={t('createPromptPlaceholder')}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="min-h-[80px] text-sm resize-none"
                />
              ) : (
                <Input
                  placeholder={t('createCommandPlaceholder')}
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  className="h-8 text-sm font-mono"
                />
              )}
            </div>
          )}

          {/* Router Info */}
          {jobType === 'router' && (
            <div className="rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-2.5 flex gap-2">
              <Info className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
              <p className="text-xs text-blue-600 dark:text-blue-400 leading-relaxed">
                Router mode is a zero-LLM passthrough. Data from the trigger (e.g., Webhook) will be sent directly to
                the delivery channel. Configure a <strong>Pre-flight Probe</strong> after creation to format the data
                with Python.
              </p>
            </div>
          )}

          {/* Agent Binding */}
          {jobType === 'agent' && agents.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs">{t('createAgentLabel')}</Label>
              <Select value={agentId} onValueChange={setAgentId}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder={t('createAgentDefault')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__default__">{t('createAgentDefault')}</SelectItem>
                  {agents.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {getBuiltinAgentName(a.id, a.name, locale)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Schedule */}
          <div className="space-y-1.5">
            <Label className="text-xs">{t('createScheduleLabel')}</Label>
            <Select
              value={scheduleKind}
              onValueChange={(v) => {
                const kind = v as ScheduleKind;
                setScheduleKind(kind);
                if (kind === 'once') setSessionTarget('isolated');
              }}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="cron">{t('createScheduleCron')}</SelectItem>
                <SelectItem value="interval">{t('createScheduleInterval')}</SelectItem>
                <SelectItem value="once">{t('createScheduleOnce')}</SelectItem>
              </SelectContent>
            </Select>

            {scheduleKind === 'cron' && (
              <Input
                placeholder={t('createCronPlaceholder')}
                value={cronExpr}
                onChange={(e) => setCronExpr(e.target.value)}
                className="h-8 text-sm font-mono"
              />
            )}
            {scheduleKind === 'interval' && (
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={5}
                  placeholder="30"
                  value={intervalMinutes}
                  onChange={(e) => setIntervalMinutes(e.target.value)}
                  className="h-8 text-sm w-24"
                />
                <span className="text-xs text-muted-foreground">{t('createIntervalUnit')}</span>
              </div>
            )}
            {scheduleKind === 'once' && (
              <Input
                type="datetime-local"
                value={onceAt}
                onChange={(e) => setOnceAt(e.target.value)}
                className="h-8 text-sm"
              />
            )}
          </div>

          {/* Schedule Estimation */}
          {monthlyExecutions !== null && monthlyExecutions > 0 && (
            <div
              className={cn(
                'rounded-full border px-3 py-2.5 flex gap-2',
                getFrequencyRiskLevel(monthlyExecutions) === 'high'
                  ? 'border-amber-500/20 bg-amber-500/10'
                  : 'border-border bg-muted/30',
              )}
            >
              <CalendarDays
                className={cn(
                  'h-4 w-4 shrink-0 mt-0.5',
                  getFrequencyRiskLevel(monthlyExecutions) === 'high' ? 'text-amber-500' : 'text-muted-foreground',
                )}
              />
              <div className="flex-1 space-y-0.5">
                <p
                  className={cn(
                    'text-xs',
                    getFrequencyRiskLevel(monthlyExecutions) === 'high'
                      ? 'font-bold text-amber-500'
                      : 'text-muted-foreground',
                  )}
                >
                  {t('estMonthlyExecutions', { count: formatMonthlyExecutions(monthlyExecutions) })}
                </p>
                {getFrequencyRiskLevel(monthlyExecutions) === 'high' && (
                  <p className="text-xs text-amber-500/80">{t('estHighFrequencyWarning')}</p>
                )}
              </div>
            </div>
          )}

          {/* Session Mode — only for recurring schedules */}
          {jobType === 'agent' && scheduleKind !== 'once' && (
            <div className="space-y-1.5">
              <Label className="text-xs">{t('createSessionModeLabel')}</Label>
              <Select value={sessionTarget} onValueChange={(v) => setSessionTarget(v as 'isolated' | 'main')}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="isolated">{t('createSessionIsolated')}</SelectItem>
                  <SelectItem value="main">{t('createSessionThread')}</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">
                {sessionTarget === 'isolated' ? t('createSessionIsolatedDesc') : t('createSessionThreadDesc')}
              </p>
              {sessionTarget === 'main' && presetChatId && presetChatTitle && (
                <div className="rounded-full border border-primary/20 bg-primary/5 px-3 py-2 flex items-center gap-2">
                  <MessageCircle className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span className="text-xs text-primary truncate">{presetChatTitle}</span>
                </div>
              )}
              {sessionTarget === 'main' && !presetChatId && (
                <Select value={selectedChatId} onValueChange={setSelectedChatId}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue placeholder={t('createSessionSelectChat')} />
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
          )}

          {/* Default Model Info */}
          {jobType === 'agent' && agentId === '__default__' && defaultModel && (
            <div className="rounded-full border border-border bg-muted/30 px-3 py-2.5 flex gap-2">
              <Cpu className="h-4 w-4 shrink-0 mt-0.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">
                {t('estDefaultModel', {
                  provider: defaultModel.providerId,
                  model: defaultModel.model,
                })}
              </p>
            </div>
          )}

          {/* Submit */}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                reset();
                onOpenChange(false);
              }}
              disabled={saving}
            >
              {t('cancel')}
            </Button>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={!canSubmit || saving}
              className={cn('gap-1.5', saving && 'opacity-70')}
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {t('createSubmit')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
