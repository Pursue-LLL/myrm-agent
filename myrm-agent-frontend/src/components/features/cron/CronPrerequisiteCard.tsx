'use client';

/**
 * [INPUT] @/services/cron::PrerequisiteCheckResponse (POS: 前置验证查询结果 DTO)
 * [OUTPUT] CronPrerequisiteCard: 前置验证门禁卡——显示手动验证成功次数与门槛，已满足（含已勾选知晓风险）为绿色确认，未满足为琥珀色建议；未满足时提供「已知晓风险，直接创建定时任务」勾选与可展开的「自动化 6 问自检」清单
 * [POS] 创建弹窗 Custom 页签末尾的前置验证门禁卡：只展示父组件传入的查询结果并上报「已知晓风险」勾选；查询与去抖在 create-dialog/useCronPrerequisite，勾选随创建请求以 override_prerequisite 提交。
 */

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldAlert, ShieldCheck, ChevronDown, ChevronUp, CheckCircle2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { PrerequisiteCheckResponse } from '@/services/cron';

interface CronPrerequisiteCardProps {
  stats: PrerequisiteCheckResponse | null;
  loading: boolean;
  override: boolean;
  onOverrideChange: (val: boolean) => void;
}

export const CronPrerequisiteCard = memo<CronPrerequisiteCardProps>(
  ({ stats, loading, override, onOverrideChange }) => {
    const t = useTranslations('cron.prerequisite');
    const [questionsOpen, setQuestionsOpen] = useState(false);

    if (loading) {
      return (
        <div className="rounded-lg border border-border/40 bg-muted/20 px-3 py-2 text-xs text-muted-foreground animate-pulse">
          {t('checkingPrerequisite')}
        </div>
      );
    }

    if (!stats) {
      return null;
    }

    const isSatisfied = stats.is_satisfied || override;

    return (
      <div
        className={cn(
          'rounded-lg border px-3 py-2.5 space-y-2 transition-colors',
          isSatisfied
            ? 'border-green-500/30 bg-green-500/5 dark:bg-green-500/10'
            : 'border-amber-500/30 bg-amber-500/5 dark:bg-amber-500/10',
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            {isSatisfied ? (
              <ShieldCheck className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
            ) : (
              <ShieldAlert className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            )}
            <div className="space-y-0.5">
              <p
                className={cn(
                  'text-xs font-semibold',
                  isSatisfied ? 'text-green-700 dark:text-green-300' : 'text-amber-700 dark:text-amber-300',
                )}
              >
                {isSatisfied
                  ? t('satisfiedTitle', { count: stats.manual_success_count, threshold: stats.threshold })
                  : t('unmetTitle', { count: stats.manual_success_count, threshold: stats.threshold })}
              </p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {isSatisfied ? t('satisfiedDesc') : t('unmetDesc')}
              </p>
            </div>
          </div>
        </div>

        {!stats.is_satisfied && (
          <div className="pt-1 border-t border-border/30 flex items-center justify-between">
            <label className="flex items-center gap-1.5 cursor-pointer text-xs select-none">
              <input
                type="checkbox"
                checked={override}
                onChange={(e) => onOverrideChange(e.target.checked)}
                className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5"
              />
              <span className="text-amber-800 dark:text-amber-200 font-medium">{t('explicitOverrideLabel')}</span>
            </label>

            <button
              type="button"
              onClick={() => setQuestionsOpen(!questionsOpen)}
              className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-0.5"
            >
              {t('checklist6Questions')}
              {questionsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          </div>
        )}

        {questionsOpen && !stats.is_satisfied && (
          <div className="rounded border border-border/40 bg-background/50 p-2 space-y-1 text-[11px] text-muted-foreground">
            <p className="font-semibold text-foreground">{t('checklistTitle')}</p>
            <ul className="list-disc list-inside space-y-0.5 pl-1">
              <li>{t('q1')}</li>
              <li>{t('q2')}</li>
              <li>{t('q3')}</li>
              <li>{t('q4')}</li>
              <li>{t('q5')}</li>
              <li>{t('q6')}</li>
            </ul>
          </div>
        )}
      </div>
    );
  },
);

CronPrerequisiteCard.displayName = 'CronPrerequisiteCard';
