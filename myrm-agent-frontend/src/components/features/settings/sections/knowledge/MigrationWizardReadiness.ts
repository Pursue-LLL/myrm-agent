/**
 * [INPUT]
 * @/services/memoryArchive::MemoryImportConfirmResponse (POS: Frontend Memory Archive and import API client. Owns typed HTTP contracts for archive restore, rollback, and import governance.)
 *
 * [OUTPUT]
 * Import readiness status/style helpers and issue formatter for migration result UI.
 *
 * [POS]
 * Migration Wizard 就绪态展示辅助层。将后端 readiness 合同映射为 UI 状态与可读文案。
 */

import type { MemoryImportConfirmResponse, MemoryImportReadinessIssue } from '@/services/memoryArchive';

export interface MigrationWizardTranslationFn {
  (key: string, values?: Record<string, string | number>): string;
}

export type ImportReadinessStatus = 'ready' | 'warning' | 'critical';

export const IMPORT_READINESS_STYLES: Record<ImportReadinessStatus, string> = {
  ready: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  critical: 'border-destructive/30 bg-destructive/10 text-destructive',
};

export function getImportReadinessStatus(result: MemoryImportConfirmResponse): ImportReadinessStatus {
  const status = result.readiness?.status;
  if (status === 'ready' || status === 'warning' || status === 'critical') {
    return status;
  }
  if (result.diagnostic_status === 'critical' || result.diagnostic_status === 'failed') {
    return 'critical';
  }
  if (result.diagnostic_status === 'warning' || result.diagnostic_status === 'missing') {
    return 'warning';
  }
  return 'ready';
}

export function formatReadinessIssue(issue: MemoryImportReadinessIssue, t: MigrationWizardTranslationFn): string {
  switch (issue.code) {
    case 'providers_not_configured':
      return t('result.readinessIssue.providersNotConfigured');
    case 'post_import_diagnostics_critical':
      return t('result.readinessIssue.postImportDiagnosticsCritical', {
        count: Number(issue.params.count ?? issue.params.failed_count ?? 0),
      });
    case 'post_import_diagnostics_warning':
      return t('result.readinessIssue.postImportDiagnosticsWarning', {
        count: Number(issue.params.count ?? issue.params.failed_count ?? 0),
      });
    case 'mcp_servers_imported_disabled':
      return t('result.readinessIssue.mcpServersImportedDisabled', {
        count: Number(issue.params.count ?? 0),
      });
    case 'workspace_rules_skipped':
      return t('result.readinessIssue.workspaceRulesSkipped', {
        count: Number(issue.params.count ?? 0),
      });
    default:
      return t('result.readinessIssue.generic', { code: issue.code });
  }
}

export interface ReadinessIssueAction {
  href: string;
  label: string;
}

export function getReadinessIssueAction(
  issue: MemoryImportReadinessIssue,
  t: MigrationWizardTranslationFn,
): ReadinessIssueAction | null {
  switch (issue.code) {
    case 'providers_not_configured':
      return {
        href: '/settings/models',
        label: t('result.readinessAction.configureProviders'),
      };
    case 'post_import_diagnostics_critical':
    case 'post_import_diagnostics_warning':
      return {
        href: '/settings/memory',
        label: t('result.readinessAction.openMemoryCenter'),
      };
    case 'mcp_servers_imported_disabled':
      return {
        href: '/settings/mcp',
        label: t('result.readinessAction.configureMcp'),
      };
    case 'workspace_rules_skipped':
      return {
        href: '/settings/memory?sub=migration',
        label: t('result.readinessAction.reviewMigrationRules'),
      };
    default:
      return null;
  }
}
