/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import {
  formatReadinessIssue,
  getImportReadinessStatus,
  getReadinessIssueAction,
  type MigrationWizardTranslationFn,
} from '../MigrationWizardReadiness';
import type { MemoryImportConfirmResponse, MemoryImportReadinessIssue } from '@/services/memory/archive';

const t: MigrationWizardTranslationFn = (key, values) => (values ? `${key}:${JSON.stringify(values)}` : key);

describe('MigrationWizardReadiness', () => {
  describe('getImportReadinessStatus', () => {
    it('returns readiness status directly when available', () => {
      const res = { readiness: { status: 'warning', issues: [] } } as unknown as MemoryImportConfirmResponse;
      expect(getImportReadinessStatus(res)).toBe('warning');
    });

    it('falls back to critical when diagnostic_status is failed/critical', () => {
      const res = { diagnostic_status: 'critical' } as unknown as MemoryImportConfirmResponse;
      expect(getImportReadinessStatus(res)).toBe('critical');
    });

    it('falls back to warning when diagnostic_status is warning/missing', () => {
      const res = { diagnostic_status: 'warning' } as unknown as MemoryImportConfirmResponse;
      expect(getImportReadinessStatus(res)).toBe('warning');
    });

    it('defaults to ready', () => {
      const res = {} as unknown as MemoryImportConfirmResponse;
      expect(getImportReadinessStatus(res)).toBe('ready');
    });
  });

  describe('formatReadinessIssue & getReadinessIssueAction', () => {
    it('handles step_budget_low issue and action correctly', () => {
      const issue: MemoryImportReadinessIssue = {
        code: 'step_budget_low',
        message: 'Step limit is low',
        severity: 'warning',
        settings_path: '/settings?tab=agent',
        params: { count: 2, min_steps: 100 },
      };

      const formatted = formatReadinessIssue(issue, t);
      expect(formatted).toBe('result.readinessIssue.stepBudgetLow:{"count":2,"min":100}');

      const action = getReadinessIssueAction(issue, t);
      expect(action).toEqual({
        href: '/settings?tab=agent',
        label: 'result.readinessAction.configureStepBudget',
      });
    });

    it('handles generic issue fallback', () => {
      const issue: MemoryImportReadinessIssue = {
        code: 'unknown_issue_code',
        message: 'Unknown',
        severity: 'warning',
        settings_path: '',
        params: {},
      };

      const formatted = formatReadinessIssue(issue, t);
      expect(formatted).toBe('result.readinessIssue.generic:{"code":"unknown_issue_code"}');

      const action = getReadinessIssueAction(issue, t);
      expect(action).toBeNull();
    });
  });
});
