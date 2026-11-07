'use client';

/**
 * [INPUT] ./useCronCreateForm::CronCreateForm (POS: 表单状态与超时校验), ../CronTimeoutEditor::TimeoutInput (POS: 整数秒输入框), ./cronCreateModel (POS: 验收标准草稿与上限)
 * [OUTPUT] CronCreatePolicyFields: 单次运行时间上限输入与 Agent 任务的验收标准列表编辑
 * [POS] 自定义创建流程的“怎样算跑完”区块：提醒没有时间上限可设；验收标准仅 Agent 类型可编辑，最多 MAX_ACCEPTANCE_CRITERIA 条，空描述的条目不会提交。
 */

import { useTranslations } from 'next-intl';
import { Hourglass, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { TimeoutInput } from '../CronTimeoutEditor';
import { MAX_ACCEPTANCE_CRITERIA, type CriterionDraft } from './cronCreateModel';
import type { CronCreateForm } from './useCronCreateForm';

export function CronCreatePolicyFields({ form }: { form: CronCreateForm }) {
  const t = useTranslations('cron');
  const { draft, patch, timeoutApplies, timeoutValid } = form;
  const { uiMode, timeoutSeconds, acceptanceCriteria } = draft;

  const updateCriterion = (idx: number, changes: Partial<CriterionDraft>) =>
    patch({
      acceptanceCriteria: acceptanceCriteria.map((criterion, i) =>
        i === idx ? { ...criterion, ...changes } : criterion,
      ),
    });

  return (
    <>
      {/* Run time limit */}
      {timeoutApplies && (
        <div className="space-y-1.5">
          <Label className="text-xs flex items-center gap-1">
            <Hourglass className="h-3 w-3" />
            {t('timeoutLabel')}
          </Label>
          <TimeoutInput
            value={timeoutSeconds}
            onChange={(value) => patch({ timeoutSeconds: value })}
            invalid={!timeoutValid}
          />
        </div>
      )}

      {/* Acceptance Criteria */}
      {uiMode === 'agent' && (
        <div className="space-y-1.5">
          <Label className="text-xs flex items-center gap-1">
            <ShieldCheck className="h-3 w-3" />
            {t('acceptanceCriteria')}
          </Label>
          {acceptanceCriteria.map((criterion, idx) => (
            <div key={idx} className="flex items-start gap-1.5">
              <Select value={criterion.type} onValueChange={(v) => updateCriterion(idx, { type: v })}>
                <SelectTrigger className="h-7 text-xs w-24 shrink-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="semantic">{t('criterionSemantic')}</SelectItem>
                  <SelectItem value="shell">{t('criterionShell')}</SelectItem>
                </SelectContent>
              </Select>
              <Input
                placeholder={
                  criterion.type === 'shell' ? t('criterionShellPlaceholder') : t('criterionSemanticPlaceholder')
                }
                value={criterion.description}
                onChange={(e) => updateCriterion(idx, { description: e.target.value })}
                className="h-7 text-xs flex-1"
              />
              <button
                type="button"
                onClick={() => patch({ acceptanceCriteria: acceptanceCriteria.filter((_, i) => i !== idx) })}
                className="h-7 w-7 flex items-center justify-center text-muted-foreground hover:text-destructive-text shrink-0"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          {acceptanceCriteria.length < MAX_ACCEPTANCE_CRITERIA && (
            <button
              type="button"
              onClick={() =>
                patch({ acceptanceCriteria: [...acceptanceCriteria, { type: 'semantic', description: '' }] })
              }
              className="text-[11px] text-muted-foreground hover:text-primary flex items-center gap-1"
            >
              <Plus className="h-3 w-3" />
              {t('addCriterion')}
            </button>
          )}
          {acceptanceCriteria.length === 0 && (
            <p className="text-[11px] text-muted-foreground">{t('acceptanceCriteriaHint')}</p>
          )}
        </div>
      )}
    </>
  );
}
