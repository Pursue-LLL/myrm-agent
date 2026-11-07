/**
 * [INPUT] ./cronCreateModel (POS: 草稿形状 / 校验 / 请求体), ./useCronCreateOptions (POS: 服务端选项), ./useCronPrerequisite (POS: 前置验证门禁), @/store/useCronStore::createJob (POS: 创建任务), @/lib/cron/cronCreateAuditGate (POS: 创建后审计门禁), @/services/riskHeldToast::isRiskHeldError (POS: 风控拦截判定)
 * [OUTPUT] useCronCreateForm / CronCreateForm: 创建弹窗唯一状态源——单个 draft + patch、由草稿派生的调度 / 估算 / 校验、提交与重置
 * [POS] 创建弹窗的状态层：所有可重置字段集中在一个 draft（reset 只需一次覆盖）；提交前若所选工作流模板有占位符且未填则先弹参数对话框；创建成功后进入审计面板，被风控拦下时 apiRequest 已提示，表单保留已填内容。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { prepareJobForSettingsAudit } from '@/lib/cron/cronCreateAuditGate';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import { isRiskHeldError } from '@/services/riskHeldToast';
import useConfigStore from '@/store/useConfigStore';
import useCronStore from '@/store/useCronStore';
import {
  appliesTimeout,
  buildCreatePayload,
  buildSchedule,
  estimateMonthlyExecutions,
  hasContent,
  initialDraft,
  isSessionValid,
  isTimeoutInputValid,
  prerequisiteQuery,
  type CronCreateDraft,
} from './cronCreateModel';
import { useCronCreateOptions } from './useCronCreateOptions';
import { useCronPrerequisite } from './useCronPrerequisite';

interface CronCreateFormParams {
  open: boolean;
  presetChatId?: string | null;
}

export function useCronCreateForm({ open, presetChatId }: CronCreateFormParams) {
  const t = useTranslations('cron');
  const { createJob } = useCronStore();
  const userTz = useConfigStore((s) => s.personalSettings?.timezone) || getBrowserTimezone();

  const [draft, setDraft] = useState(() => initialDraft(presetChatId));
  const [saving, setSaving] = useState(false);
  const patch = useCallback(
    (changes: Partial<CronCreateDraft>) => setDraft((previous) => ({ ...previous, ...changes })),
    [],
  );

  const options = useCronCreateOptions(open, draft.uiMode);
  const chatId = presetChatId || draft.selectedChatId || null;
  const prerequisite = useCronPrerequisite({
    enabled: open,
    ...prerequisiteQuery(draft),
    agentId: draft.agentId,
    workflowTemplateId: draft.workflowTemplateId,
    chatId,
  });
  const { clear: clearPrerequisite } = prerequisite;

  useEffect(() => {
    if (open && presetChatId) {
      patch({ sessionTarget: 'main' });
    }
  }, [open, presetChatId, patch]);

  const { scheduleKind, cronExpr, intervalMinutes, onceAt } = draft;
  const schedule = useMemo(
    () => buildSchedule({ scheduleKind, cronExpr, intervalMinutes, onceAt }, userTz),
    [scheduleKind, cronExpr, intervalMinutes, onceAt, userTz],
  );
  const monthlyExecutions = useMemo(
    () => estimateMonthlyExecutions({ scheduleKind, cronExpr, intervalMinutes }),
    [scheduleKind, cronExpr, intervalMinutes],
  );
  const selectedWorkflowTemplate = useMemo(
    () => options.workflowTemplates.find((template) => template.template_id === draft.workflowTemplateId) ?? null,
    [options.workflowTemplates, draft.workflowTemplateId],
  );

  const contentValid = hasContent(draft);
  const timeoutApplies = appliesTimeout(draft.uiMode);
  const timeoutValid = isTimeoutInputValid(draft.uiMode, draft.timeoutSeconds);
  const canSubmit = contentValid && schedule !== null && isSessionValid(draft.sessionTarget, chatId) && timeoutValid;

  const reset = useCallback(() => {
    setDraft(initialDraft(presetChatId));
    clearPrerequisite();
  }, [presetChatId, clearPrerequisite]);

  const create = useCallback(
    async (workflowArgs: Record<string, string> | null) => {
      if (!canSubmit || !schedule) {
        return;
      }
      setSaving(true);
      try {
        const job = await createJob(buildCreatePayload({ draft, schedule, chatId, workflowArgs }));
        try {
          patch({ createdJob: await prepareJobForSettingsAudit(job) });
          toast.success(t('createSuccess'));
        } catch {
          toast.error(t('auditPauseFail'));
        }
      } catch (error) {
        // `apiRequest` has already shown the notice for a held prompt or criteria; the form keeps the text.
        if (!isRiskHeldError(error)) {
          toast.error(t('actionFail'));
        }
      } finally {
        setSaving(false);
      }
    },
    [canSubmit, schedule, draft, chatId, createJob, patch, t],
  );

  const submit = useCallback(async () => {
    const needsWorkflowArgs =
      draft.uiMode === 'agent' &&
      selectedWorkflowTemplate !== null &&
      selectedWorkflowTemplate.placeholders.length > 0 &&
      !draft.workflowTemplateArgs;
    if (needsWorkflowArgs) {
      patch({ workflowArgsDialogOpen: true });
      return;
    }
    await create(draft.workflowTemplateArgs);
  }, [create, draft.uiMode, draft.workflowTemplateArgs, selectedWorkflowTemplate, patch]);

  const confirmWorkflowArgs = useCallback(
    (args: Record<string, string>) => {
      patch({ workflowTemplateArgs: args });
      void create(args);
    },
    [create, patch],
  );

  return {
    draft,
    patch,
    reset,
    saving,
    options,
    prerequisite,
    schedule,
    monthlyExecutions,
    selectedWorkflowTemplate,
    contentValid,
    timeoutApplies,
    timeoutValid,
    canSubmit,
    submit,
    confirmWorkflowArgs,
  };
}

export type CronCreateForm = ReturnType<typeof useCronCreateForm>;
