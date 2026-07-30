/**
 * [INPUT] @/lib/api::ApiError
 * [OUTPUT] resolveAssessmentImportErrorMessage
 * [POS] 评估导入错误解析：优先结构化字段 import_reason，兜底 message 文案。
 */

import { ApiError } from '@/lib/api';

export type AssessmentImportTranslator = (key: string) => string;

export function resolveAssessmentImportErrorMessage(error: unknown, t: AssessmentImportTranslator): string {
  if (!(error instanceof ApiError)) {
    return t('milestone.importFailed');
  }
  const importReason = error.details
    .find((detail) => detail.field === 'import_reason')
    ?.issue?.trim()
    .toLowerCase();
  if (importReason === 'artifact_version_already_imported') {
    return t('milestone.importDuplicate');
  }
  if (importReason === 'no_actionable_tasks') {
    return t('milestone.importNoActionable');
  }
  if (importReason === 'no_importable_tasks') {
    return t('milestone.importNoTasks');
  }
  if (importReason === 'artifact_not_found') {
    return t('milestone.importArtifactNotFound');
  }
  const message = error.message.toLowerCase();
  if (message.includes('already imported')) {
    return t('milestone.importDuplicate');
  }
  if (message.includes('none are actionable tasks')) {
    return t('milestone.importNoActionable');
  }
  if (message.includes('does not contain importable task list items')) {
    return t('milestone.importNoTasks');
  }
  if (message.includes('artifact not found')) {
    return t('milestone.importArtifactNotFound');
  }
  return t('milestone.importFailed');
}
