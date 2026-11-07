/**
 * [INPUT] @/hooks/shared/useToast::toast + @/lib/utils/toast::toast (POS: 提示), ../MigrationWizardReadiness (POS: 导入就绪态文案), @/services/memory/archive::MemoryImportConfirmResponse (POS: 导入确认结果)
 * [OUTPUT] MemoryTranslator / toastFailure / notifyImportOutcome: 记忆面板共用的失败提示与导入结果提示
 * [POS] 记忆面板的提示层（无 React 组件）：失败提示带上错误原文，没有原文时用通用兜底；导入结果按就绪态给出成功 / 警告 / 严重提示，有可跳转的设置入口时附带操作按钮。
 */

import type { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { toast as actionToast } from '@/lib/utils/toast';
import type { MemoryImportConfirmResponse } from '@/services/memory/archive';
import {
  formatReadinessIssue,
  getImportReadinessStatus,
  getReadinessIssueAction,
  type MigrationWizardTranslationFn,
} from '../MigrationWizardReadiness';

export type MemoryTranslator = ReturnType<typeof useTranslations<'memory'>>;

export function toastFailure(t: MemoryTranslator, title: string, error: unknown): void {
  toast({ title, description: error instanceof Error ? error.message : t('unknownError'), variant: 'destructive' });
}

export function notifyImportOutcome(
  result: MemoryImportConfirmResponse,
  t: MemoryTranslator,
  tWizard: MigrationWizardTranslationFn,
): void {
  const readinessStatus = result.readiness ? getImportReadinessStatus(result) : 'ready';
  if (!result.readiness || readinessStatus === 'ready') {
    toast({ title: t('importSuccess'), description: t('importSuccessDesc', { count: result.total_imported }) });
    return;
  }

  const primaryIssue = result.readiness.issues[0];
  const issueText = primaryIssue ? formatReadinessIssue(primaryIssue, tWizard) : tWizard('result.readinessSummary');
  const action = primaryIssue ? getReadinessIssueAction(primaryIssue, tWizard) : null;
  const title = tWizard(`result.readinessStatus.${readinessStatus}`);
  if (action) {
    actionToast.info(title, {
      description: issueText,
      duration: 12000,
      action: { label: action.label, onClick: () => window.location.assign(action.href) },
    });
    return;
  }
  toast({ title, description: issueText, variant: readinessStatus === 'critical' ? 'destructive' : 'default' });
}
