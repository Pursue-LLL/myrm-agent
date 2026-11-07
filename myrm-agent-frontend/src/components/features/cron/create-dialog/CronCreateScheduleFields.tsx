'use client';

/**
 * [INPUT] ./useCronCreateForm::CronCreateForm (POS: 表单状态与派生调度), ../cron-blueprints::{CRON_PRESETS, humanizeSchedule} (POS: 预设与调度文案 SSOT), @/lib/utils/cronEstimate (POS: 月度执行次数展示与频率风险), ../CronDeployModeNotice (POS: 部署感知提示)
 * [OUTPUT] CronCreateScheduleFields: 调度类型与输入（cron 表达式 + 预设 / 间隔分钟 / 单次时间）、人话预览、月度执行估算卡与周期任务的部署提示
 * [POS] 自定义创建流程的“何时跑”区块：切到单次调度会把会话模式重置为独立会话；高频（风险等级 high）时估算卡以琥珀色警示；单次调度不显示部署提示。
 */

import { useLocale, useTranslations } from 'next-intl';
import { CalendarDays, Sparkles } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { formatMonthlyExecutions, getFrequencyRiskLevel } from '@/lib/utils/cronEstimate';
import { cn } from '@/lib/utils/classnameUtils';
import { CRON_PRESETS, humanizeSchedule } from '../cron-blueprints';
import CronDeployModeNotice from '../CronDeployModeNotice';
import { MIN_INTERVAL_MINUTES, type ScheduleKind } from './cronCreateModel';
import type { CronCreateForm } from './useCronCreateForm';

export function CronCreateScheduleFields({ form }: { form: CronCreateForm }) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const { draft, patch, schedule, monthlyExecutions } = form;
  const { scheduleKind, cronExpr, intervalMinutes, onceAt } = draft;
  const highFrequency = monthlyExecutions !== null && getFrequencyRiskLevel(monthlyExecutions) === 'high';

  return (
    <>
      {/* Schedule */}
      <div className="space-y-1.5">
        <Label className="text-xs">{t('createScheduleLabel')}</Label>
        <Select
          value={scheduleKind}
          onValueChange={(v) => {
            const kind = v as ScheduleKind;
            patch(kind === 'once' ? { scheduleKind: kind, sessionTarget: 'isolated' } : { scheduleKind: kind });
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
          <div className="space-y-1.5">
            <Input
              placeholder={t('createCronPlaceholder')}
              value={cronExpr}
              onChange={(e) => patch({ cronExpr: e.target.value })}
              className="h-8 text-sm font-mono"
            />
            <div className="flex flex-wrap gap-1">
              {CRON_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => patch({ cronExpr: p.expr })}
                  className="text-[11px] px-2 py-0.5 rounded-full border border-border bg-muted/50 text-muted-foreground hover:bg-primary/10 hover:text-primary hover:border-primary/40 transition-colors"
                >
                  {t(p.labelKey)}
                </button>
              ))}
            </div>
          </div>
        )}
        {scheduleKind === 'interval' && (
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={MIN_INTERVAL_MINUTES}
              placeholder="30"
              value={intervalMinutes}
              onChange={(e) => patch({ intervalMinutes: e.target.value })}
              className="h-8 text-sm w-24"
            />
            <span className="text-xs text-muted-foreground">{t('createIntervalUnit')}</span>
          </div>
        )}
        {scheduleKind === 'once' && (
          <Input
            type="datetime-local"
            value={onceAt}
            onChange={(e) => patch({ onceAt: e.target.value })}
            className="h-8 text-sm"
          />
        )}

        {schedule && (
          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
            <p className="text-xs text-muted-foreground">
              <Sparkles className="h-3 w-3 inline mr-1" />
              {humanizeSchedule(schedule, t, locale)}
            </p>
          </div>
        )}
      </div>

      {/* Schedule Estimation */}
      {monthlyExecutions !== null && monthlyExecutions > 0 && (
        <div
          className={cn(
            'rounded-full border px-3 py-2.5 flex gap-2',
            highFrequency ? 'border-amber-500/20 bg-amber-500/10' : 'border-border bg-muted/30',
          )}
        >
          <CalendarDays
            className={cn('h-4 w-4 shrink-0 mt-0.5', highFrequency ? 'text-amber-500' : 'text-muted-foreground')}
          />
          <div className="flex-1 space-y-0.5">
            <p className={cn('text-xs', highFrequency ? 'font-bold text-amber-500' : 'text-muted-foreground')}>
              {t('estMonthlyExecutions', { count: formatMonthlyExecutions(monthlyExecutions) })}
            </p>
            {highFrequency && <p className="text-xs text-amber-500/80">{t('estHighFrequencyWarning')}</p>}
          </div>
        </div>
      )}

      {scheduleKind !== 'once' && <CronDeployModeNotice />}
    </>
  );
}
