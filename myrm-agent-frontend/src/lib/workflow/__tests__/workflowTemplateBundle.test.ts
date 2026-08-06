import { describe, expect, it } from 'vitest';

import {
  buildWorkflowTemplateBundle,
  isValidTemplateId,
  normalizeTemplateId,
  parseWorkflowTemplateBundle,
  serializeWorkflowTemplateBundle,
  workflowTemplateExportFilename,
} from '@/lib/workflow/workflowTemplateBundle';
import type { WorkflowTemplateDetailResponse } from '@/services/workflowTemplates';

const SAMPLE_DETAIL: WorkflowTemplateDetailResponse = {
  template: {
    template_id: 'daily-report',
    display_name: 'Daily Report',
    script_hash: 'abc',
    trust_latch: true,
    required_agent_types: ['generalPurpose'],
    placeholders: ['topic'],
    created_at: '2026-08-06T00:00:00.000Z',
    updated_at: '2026-08-06T00:00:00.000Z',
  },
  script_code: 'import myrm_tools\nmyrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="hello", readonly=True)',
  bound_cron_count: 0,
};

describe('workflowTemplateBundle', () => {
  it('builds and parses a version-1 bundle', () => {
    const bundle = buildWorkflowTemplateBundle(SAMPLE_DETAIL);
    const parsed = parseWorkflowTemplateBundle(serializeWorkflowTemplateBundle(bundle));
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(parsed.value.templateId).toBe('daily-report');
      expect(parsed.value.displayName).toBe('Daily Report');
      expect(parsed.value.trustLatch).toBe(true);
      expect(parsed.value.scriptCode).toContain('spawn_subagent');
    }
  });

  it('rejects unsupported bundle versions', () => {
    const parsed = parseWorkflowTemplateBundle(
      JSON.stringify({
        version: '99',
        template: {
          templateId: 'x',
          displayName: 'X',
          scriptCode: 'print(1)',
          trustLatch: false,
        },
      }),
    );
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) {
      expect(parsed.error).toBe('unsupported_version');
    }
  });

  it('rejects invalid bundle shape', () => {
    const parsed = parseWorkflowTemplateBundle(JSON.stringify({ version: '1' }));
    expect(parsed.ok).toBe(false);
  });

  it('builds safe export filenames', () => {
    expect(workflowTemplateExportFilename('daily-report')).toBe('daily-report.myrm-workflow.json');
    expect(workflowTemplateExportFilename('  weird/id!! ')).toBe('weird-id.myrm-workflow.json');
  });

  it('normalizes template ids like the server store', () => {
    expect(normalizeTemplateId('Daily_Report')).toBe('daily-report');
    expect(isValidTemplateId('daily-report')).toBe(true);
    expect(isValidTemplateId('-bad-')).toBe(false);
  });

  it('rejects invalid template ids in bundles', () => {
    const parsed = parseWorkflowTemplateBundle(
      JSON.stringify({
        version: '1',
        template: {
          templateId: '!!!',
          displayName: 'X',
          scriptCode: 'print(1)',
          trustLatch: false,
        },
      }),
    );
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) {
      expect(parsed.error).toBe('invalid_template_id');
    }
  });
});
