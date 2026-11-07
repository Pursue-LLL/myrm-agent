'use client';

/**
 * [INPUT] ./useCronCreateForm::CronCreateForm (POS: 表单状态与提交), ./CronCreate{Content,Target,Schedule,Session,Policy}Fields (POS: 各字段区块), ../CronPrerequisiteCard (POS: 前置验证门禁卡)
 * [OUTPUT] CronCreateCustomForm: 自定义创建流程——按“跑什么 → 交给谁 → 何时跑 → 哪个会话 → 怎样算跑完”的顺序组装各区块，末尾是前置验证门禁卡与取消 / 创建按钮
 * [POS] 创建弹窗 Custom 页签的装配层：只组合，不持有状态；门禁卡在已填内容后才出现，创建按钮在内容 / 调度 / 会话 / 时间上限任一不合法或提交中时禁用。
 */

import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { CronPrerequisiteCard } from '../CronPrerequisiteCard';
import { CronCreateContentFields } from './CronCreateContentFields';
import { CronCreatePolicyFields } from './CronCreatePolicyFields';
import { CronCreateScheduleFields } from './CronCreateScheduleFields';
import { CronCreateSessionFields } from './CronCreateSessionFields';
import { CronCreateTargetFields } from './CronCreateTargetFields';
import type { CronCreateForm } from './useCronCreateForm';

interface CronCreateCustomFormProps {
  form: CronCreateForm;
  presetChatId?: string | null;
  presetChatTitle?: string | null;
  onCancel: () => void;
}

export function CronCreateCustomForm({ form, presetChatId, presetChatTitle, onCancel }: CronCreateCustomFormProps) {
  const t = useTranslations('cron');
  const { draft, patch, prerequisite, contentValid, canSubmit, saving, submit } = form;

  return (
    <>
      <CronCreateContentFields form={form} />
      <CronCreateTargetFields form={form} />
      <CronCreateScheduleFields form={form} />
      <CronCreateSessionFields form={form} presetChatId={presetChatId} presetChatTitle={presetChatTitle} />
      <CronCreatePolicyFields form={form} />

      {/* Prerequisite Gate Card */}
      {contentValid && (
        <CronPrerequisiteCard
          stats={prerequisite.stats}
          loading={prerequisite.loading}
          override={draft.overridePrerequisite}
          onOverrideChange={(value) => patch({ overridePrerequisite: value })}
        />
      )}

      {/* Submit */}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          {t('cancel')}
        </Button>
        <Button
          size="sm"
          onClick={() => void submit()}
          disabled={!canSubmit || saving}
          className={cn('gap-1.5', saving && 'opacity-70')}
        >
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {t('createSubmit')}
        </Button>
      </div>
    </>
  );
}
