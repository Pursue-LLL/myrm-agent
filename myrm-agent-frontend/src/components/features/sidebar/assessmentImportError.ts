/**
 * [INPUT] @/lib/api::ApiError
 * [OUTPUT] resolveAssessmentImportFailureReason + resolveAssessmentImportErrorMessage
 * [POS] 评估导入错误解析：优先结构化字段 import_reason，兜底 message 文案。
 */

import { ApiError } from '@/lib/api';

export type AssessmentImportTranslator = (key: string) => string;
export type AssessmentImportFailureReason =
  | 'artifact_version_already_imported'
  | 'no_actionable_tasks'
  | 'no_importable_tasks'
  | 'artifact_not_found'
  | 'project_not_found'
  | 'network_error'
  | 'unknown_error';

function resolveStructuredImportReason(error: ApiError): AssessmentImportFailureReason | null {
  const importReason = error.details
    .find((detail) => detail.field === 'import_reason')
    ?.issue?.trim()
    .toLowerCase();
  if (importReason === 'artifact_version_already_imported') {
    return 'artifact_version_already_imported';
  }
  if (importReason === 'no_actionable_tasks') {
    return 'no_actionable_tasks';
  }
  if (importReason === 'no_importable_tasks') {
    return 'no_importable_tasks';
  }
  if (importReason === 'artifact_not_found') {
    return 'artifact_not_found';
  }
  if (importReason === 'project_not_found') {
    return 'project_not_found';
  }
  return null;
}

function resolveMessageFallbackReason(message: string): AssessmentImportFailureReason | null {
  if (message.includes('already imported')) {
    return 'artifact_version_already_imported';
  }
  if (message.includes('none are actionable tasks')) {
    return 'no_actionable_tasks';
  }
  if (message.includes('does not contain importable task list items')) {
    return 'no_importable_tasks';
  }
  if (message.includes('artifact not found')) {
    return 'artifact_not_found';
  }
  if (message.includes('project not found')) {
    return 'project_not_found';
  }
  if (message.includes('network') || message.includes('fetch') || message.includes('timeout')) {
    return 'network_error';
  }
  return null;
}

export function resolveAssessmentImportFailureReason(error: unknown): AssessmentImportFailureReason {
  if (!(error instanceof ApiError)) {
    return 'unknown_error';
  }
  return resolveStructuredImportReason(error) ?? resolveMessageFallbackReason(error.message.toLowerCase()) ?? 'unknown_error';
}

export function resolveAssessmentImportErrorMessage(error: unknown, t: AssessmentImportTranslator): string {
  const reason = resolveAssessmentImportFailureReason(error);
  if (reason === 'artifact_version_already_imported') {
    return t('milestone.importDuplicate');
  }
  if (reason === 'no_actionable_tasks') {
    return t('milestone.importNoActionable');
  }
  if (reason === 'no_importable_tasks') {
    return t('milestone.importNoTasks');
  }
  if (reason === 'artifact_not_found') {
    return t('milestone.importArtifactNotFound');
  }
  if (reason === 'project_not_found') {
    return t('milestone.importProjectNotFound');
  }
  return t('milestone.importFailed');
}
