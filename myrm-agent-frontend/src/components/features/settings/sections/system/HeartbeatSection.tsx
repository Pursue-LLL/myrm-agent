'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { ConfigLoadError } from '@/components/features/app-shell/config-load-error';
import { Skeleton } from '@/components/primitives/skeleton';
import {
  IconActivity,
  IconAlertCircle,
  IconClock,
  IconGlobe,
  IconMoon,
  IconSun,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import { Bot } from 'lucide-react';
import { toast } from 'sonner';
import { Label } from '@/components/primitives/label';
import { Textarea } from '@/components/primitives/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import Toggle from '@/components/features/settings/common/Toggle';
import SettingsSection from '../SettingsSection';
import { enableHeartbeat, disableHeartbeat, getHeartbeatStatus } from '@/services/heartbeat';
import useAgentStore from '@/store/useAgentStore';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

import type { HeartbeatEnableRequest, HeartbeatStatus, ScheduleKind } from '@/services/heartbeat';

const INTERVAL_OPTIONS = [
  { value: '900000', labelKey: '15min' },
  { value: '1800000', labelKey: '30min' },
  { value: '3600000', labelKey: '1h' },
  { value: '7200000', labelKey: '2h' },
  { value: '14400000', labelKey: '4h' },
] as const;

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: String(i),
  label: String(i).padStart(2, '0'),
}));

const MINUTE_OPTIONS = [
  { value: '0', label: '00' },
  { value: '15', label: '15' },
  { value: '30', label: '30' },
  { value: '45', label: '45' },
];

type DayPreset = 'everyday' | 'weekdays' | 'weekends';

const DAY_PRESETS: DayPreset[] = ['everyday', 'weekdays', 'weekends'];

function dayPresetToCronDow(preset: DayPreset): string {
  switch (preset) {
    case 'everyday':
      return '*';
    case 'weekdays':
      return '1-5';
    case 'weekends':
      return '0,6';
  }
}

function cronDowToPreset(dow: string): DayPreset {
  if (dow === '1-5') return 'weekdays';
  if (dow === '0,6' || dow === '6,0') return 'weekends';
  return 'everyday';
}

function parseCronExpr(expr: string): { hour: string; minute: string; dayPreset: DayPreset } {
  const parts = expr.split(/\s+/);
  if (parts.length < 5) return { hour: '9', minute: '0', dayPreset: 'everyday' };
  return {
    minute: parts[0] ?? '0',
    hour: parts[1] ?? '9',
    dayPreset: cronDowToPreset(parts[4] ?? '*'),
  };
}

function buildCronExpr(hour: string, minute: string, dayPreset: DayPreset): string {
  return `${minute} ${hour} * * ${dayPresetToCronDow(dayPreset)}`;
}

function getSystemTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'UTC';
  }
}

interface RhythmPreset {
  id: 'morning' | 'evening';
  icon: typeof IconSun;
  hour: string;
  minute: string;
  dayPreset: DayPreset;
}

const RHYTHM_PRESETS: RhythmPreset[] = [
  { id: 'morning', icon: IconSun, hour: '9', minute: '0', dayPreset: 'everyday' },
  { id: 'evening', icon: IconMoon, hour: '21', minute: '0', dayPreset: 'everyday' },
];

const HeartbeatSection = memo(() => {
  const t = useTranslations('heartbeat');
  const locale = useLocale();
  const [status, setStatus] = useState<HeartbeatStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [saving, setSaving] = useState(false);

  const [scheduleMode, setScheduleMode] = useState<ScheduleKind>('interval');
  const [intervalMs, setIntervalMs] = useState('1800000');
  const [cronHour, setCronHour] = useState('9');
  const [cronMinute, setCronMinute] = useState('0');
  const [cronDayPreset, setCronDayPreset] = useState<DayPreset>('everyday');
  const [timezone, setTimezone] = useState(getSystemTimezone);
  const [customPrompt, setCustomPrompt] = useState('');
  const [agentId, setAgentId] = useState('__default__');

  const { agents, fetchAgents } = useAgentStore();

  const fetchStatus = useCallback(() => {
    setLoading(true);
    setFetchError(false);
    let cancelled = false;
    getHeartbeatStatus()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
        if (s.schedule_kind === 'cron' && s.cron_expr) {
          setScheduleMode('cron');
          const parsed = parseCronExpr(s.cron_expr);
          setCronHour(parsed.hour);
          setCronMinute(parsed.minute);
          setCronDayPreset(parsed.dayPreset);
          if (s.timezone) setTimezone(s.timezone);
        } else {
          setScheduleMode('interval');
          if (s.interval_ms) setIntervalMs(String(s.interval_ms));
        }
        if (s.prompt) setCustomPrompt(s.prompt);
        setAgentId(s.agent_id ?? '__default__');
      })
      .catch(() => {
        if (!cancelled) setFetchError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchAgents();
  }, [fetchStatus, fetchAgents]);

  const selectedAgent = useMemo(
    () => (agentId !== '__default__' ? agents.find((a) => a.id === agentId) : undefined),
    [agentId, agents],
  );

  const inheritedModel = useMemo(() => {
    const ms = selectedAgent?.model_selection;
    if (!ms?.model) return null;
    return `${ms.providerId}/${ms.model}`;
  }, [selectedAgent]);

  const buildEnableParams = useCallback((): HeartbeatEnableRequest => {
    const agentParam = agentId !== '__default__' ? agentId : undefined;
    if (scheduleMode === 'cron') {
      return {
        schedule_kind: 'cron',
        cron_expr: buildCronExpr(cronHour, cronMinute, cronDayPreset),
        timezone,
        prompt: customPrompt || undefined,
        agent_id: agentParam,
      };
    }
    return {
      interval_ms: Number(intervalMs),
      prompt: customPrompt || undefined,
      agent_id: agentParam,
    };
  }, [scheduleMode, cronHour, cronMinute, cronDayPreset, timezone, intervalMs, customPrompt, agentId]);

  const handleToggle = useCallback(async () => {
    if (!status) return;
    setToggling(true);
    try {
      const result = status.enabled ? await disableHeartbeat() : await enableHeartbeat(buildEnableParams());
      setStatus(result);
      toast.success(t(result.enabled ? 'enabled' : 'disabled'));
    } catch {
      toast.error(t('toggleError'));
    } finally {
      setToggling(false);
    }
  }, [status, buildEnableParams, t]);

  const handleSaveConfig = useCallback(async () => {
    if (!status?.enabled) return;
    setSaving(true);
    try {
      const result = await enableHeartbeat(buildEnableParams());
      setStatus(result);
      toast.success(t('configSaved'));
    } catch {
      toast.error(t('saveError'));
    } finally {
      setSaving(false);
    }
  }, [status, buildEnableParams, t]);

  const handlePresetClick = useCallback(
    (preset: RhythmPreset) => {
      setScheduleMode('cron');
      setCronHour(preset.hour);
      setCronMinute(preset.minute);
      setCronDayPreset(preset.dayPreset);
      setCustomPrompt(t(`presets.${preset.id}Prompt`));
    },
    [t],
  );

  const isDisabled = !status?.enabled;
  const dailyChecks = Math.round(86_400_000 / Number(intervalMs));

  if (loading) {
    return (
      <SettingsSection title={t('title')}>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-6 w-10 rounded-full" />
            </div>
          ))}
        </div>
      </SettingsSection>
    );
  }

  if (fetchError) {
    return (
      <SettingsSection title={t('title')}>
        <ConfigLoadError onRetry={fetchStatus} />
      </SettingsSection>
    );
  }

  return (
    <SettingsSection
      title={
        <span className="flex items-center gap-2">
          <IconActivity className="h-5 w-5 text-primary" />
          {t('title')}
        </span>
      }
      description={t('description')}
    >
      {/* Enable/Disable Toggle */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label className="text-sm font-medium">{t('toggleLabel')}</Label>
          <p className="text-xs text-muted-foreground">{t('toggleDesc')}</p>
        </div>
        <Toggle checked={status?.enabled ?? false} isLoading={toggling} onChange={handleToggle} />
      </div>

      {/* Schedule Mode Toggle */}
      <div className="space-y-2">
        <Label className="text-sm font-medium flex items-center gap-1.5">
          <IconClock className="h-3.5 w-3.5" />
          {t('scheduleMode')}
        </Label>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={isDisabled}
            onClick={() => setScheduleMode('interval')}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              scheduleMode === 'interval'
                ? 'bg-primary/10 border-primary/30 text-primary font-medium'
                : 'bg-background border-border/50 text-muted-foreground hover:bg-muted/50'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {t('modeInterval')}
          </button>
          <button
            type="button"
            disabled={isDisabled}
            onClick={() => setScheduleMode('cron')}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              scheduleMode === 'cron'
                ? 'bg-primary/10 border-primary/30 text-primary font-medium'
                : 'bg-background border-border/50 text-muted-foreground hover:bg-muted/50'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {t('modeCron')}
          </button>
        </div>
      </div>

      {/* Interval Selection (interval mode) */}
      {scheduleMode === 'interval' && (
        <div className="space-y-2">
          <Label className="text-sm font-medium">{t('intervalLabel')}</Label>
          <Select value={intervalMs} onValueChange={setIntervalMs} disabled={isDisabled}>
            <SelectTrigger className="w-full sm:w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INTERVAL_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {t(`intervals.${opt.labelKey}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {Number(intervalMs) < 3_600_000 && (
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <IconAlertCircle className="h-3 w-3 shrink-0" />
              {t('intervalCostHint', { count: dailyChecks })}
            </p>
          )}
        </div>
      )}

      {/* Cron Configuration (cron mode) */}
      {scheduleMode === 'cron' && (
        <div className="space-y-4">
          {/* Rhythm Presets */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('presetLabel')}</Label>
            <div className="flex gap-2 flex-wrap">
              {RHYTHM_PRESETS.map((preset) => {
                const Icon = preset.icon;
                return (
                  <button
                    key={preset.id}
                    type="button"
                    disabled={isDisabled}
                    onClick={() => handlePresetClick(preset)}
                    className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-border/50 bg-background hover:bg-muted/50 hover:border-primary/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Icon className="h-4 w-4 text-amber-500" />
                    <div className="text-left">
                      <div className="font-medium text-foreground">{t(`presets.${preset.id}`)}</div>
                      <div className="text-xs text-muted-foreground">{t(`presets.${preset.id}Desc`)}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Time Selector */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('cronTimeLabel')}</Label>
            <div className="flex items-center gap-2">
              <Select value={cronHour} onValueChange={setCronHour} disabled={isDisabled}>
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HOUR_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-sm font-medium text-muted-foreground">:</span>
              <Select value={cronMinute} onValueChange={setCronMinute} disabled={isDisabled}>
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MINUTE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Day Selector */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t('cronDaysLabel')}</Label>
            <Select value={cronDayPreset} onValueChange={(v) => setCronDayPreset(v as DayPreset)} disabled={isDisabled}>
              <SelectTrigger className="w-full sm:w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DAY_PRESETS.map((preset) => (
                  <SelectItem key={preset} value={preset}>
                    {t(`cronDays.${preset}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Timezone */}
          <div className="space-y-2">
            <Label className="text-sm font-medium flex items-center gap-1.5">
              <IconGlobe className="h-3.5 w-3.5" />
              {t('timezoneLabel')}
            </Label>
            <div className="text-sm text-muted-foreground bg-muted/30 px-3 py-2 rounded-lg border border-border/50">
              {timezone}
            </div>
          </div>
        </div>
      )}

      {/* Agent Binding */}
      {agents.length > 0 && (
        <div className="space-y-2">
          <Label className="text-sm font-medium flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5" />
            {t('agentLabel')}
          </Label>
          <Select value={agentId} onValueChange={setAgentId} disabled={isDisabled}>
            <SelectTrigger className="w-full sm:w-56">
              <SelectValue placeholder={t('agentDefault')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__default__">{t('agentDefault')}</SelectItem>
              {agents.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {getBuiltinAgentName(a.id, a.name, locale)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {inheritedModel && (
            <p className="text-xs text-muted-foreground">
              {t('agentModelHint', { model: inheritedModel })}
            </p>
          )}
        </div>
      )}

      {/* Custom Prompt */}
      <div className="space-y-2">
        <Label className="text-sm font-medium flex items-center gap-1.5">
          <IconZap className="h-3.5 w-3.5" />
          {t('promptLabel')}
        </Label>
        <p className="text-xs text-muted-foreground">{t('promptDesc')}</p>
        <Textarea
          value={customPrompt}
          onChange={(e) => setCustomPrompt(e.target.value)}
          placeholder={t('promptPlaceholder')}
          disabled={isDisabled}
          rows={4}
          className="resize-none text-sm"
        />
      </div>

      {/* Save button */}
      {status?.enabled && (
        <button
          onClick={handleSaveConfig}
          disabled={saving}
          className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? t('saving') : t('saveConfig')}
        </button>
      )}

      {/* Schedule Description + Status Info */}
      {status?.enabled && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-muted/50 border border-border/50">
          <IconAlertCircle className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
          <div className="text-xs text-muted-foreground space-y-0.5">
            {status.schedule_description && (
              <p className="font-medium text-foreground/70">
                {t('scheduleDescription')}: {status.schedule_description}
              </p>
            )}
            {status.last_run_at && (
              <p>
                {t('lastRun')}: {new Date(status.last_run_at).toLocaleString()}
                {status.last_status && (
                  <span
                    className={
                      status.last_status === 'ok' ? 'text-green-600 dark:text-green-400 ml-2' : 'text-red-500 ml-2'
                    }
                  >
                    ({status.last_status})
                  </span>
                )}
              </p>
            )}
            {status.next_run_at && (
              <p>
                {t('nextRun')}: {new Date(status.next_run_at).toLocaleString()}
              </p>
            )}
            <p>
              {t('totalRuns')}: {status.fire_count}
            </p>
          </div>
        </div>
      )}
    </SettingsSection>
  );
});

HeartbeatSection.displayName = 'HeartbeatSection';

export default HeartbeatSection;
