import { getMigrationSourceDisplayName, PASTED_MEMORY_COMPETITOR_ID } from '@/services/migrationDiscovery';

/** Translator contract shared by every wizard step: steps stay testable without a real intl provider. */
export interface TranslationFn {
  (key: string, values?: Record<string, string | number>): string;
}

/**
 * Coverage labels the backend may send as an i18n key; anything else is rendered
 * verbatim. Mirrors the label vocabulary of build_coverage_items.
 */
export const COVERAGE_LABEL_KEYS = [
  'instruction_lane',
  'memory_lane',
  'session_lane',
  'memory_persona',
  'skills_review',
  'api_keys_manual',
  'mcp_ready',
  'mcp_manual',
  'channels_manual',
  'agent_config_manual',
  'no_importable_data',
  'cron_lane',
  'kanban_not_migrated',
  'credential_pool_migration',
] as const;

/** Cron skip reasons with dedicated copy; unknown reasons fall back to the generic line. */
export const CRON_SKIP_REASON_KEYS = new Set([
  'no_agent_script',
  'missing_prompt',
  'invalid_schedule',
  'prompt_injection',
  'unsupported_job_type',
]);

export function resolveSourceDisplayName(competitor: string, t: TranslationFn): string {
  return competitor === PASTED_MEMORY_COMPETITOR_ID ? t('paste.sourceName') : getMigrationSourceDisplayName(competitor);
}

export function formatCronSkippedReason(t: TranslationFn, reason: string): string {
  const key = CRON_SKIP_REASON_KEYS.has(reason) ? reason : 'unsupported_job_type';
  return t(`preview.cronSkippedReason.${key}`);
}
