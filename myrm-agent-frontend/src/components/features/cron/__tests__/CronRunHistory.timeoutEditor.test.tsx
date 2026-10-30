// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { CronJob } from '@/services/cron.types';

const { stableT } = vi.hoisted(() => ({ stableT: (key: string) => key }));

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const cronStoreState = vi.hoisted(() => ({
  runs: [] as never[],
  runsLoading: false,
  runsHasMore: false,
  runsTotal: 0,
  runsStatusFilter: null,
  fetchRuns: vi.fn(),
  fetchJobs: vi.fn(),
  setRunsStatusFilter: vi.fn(),
}));

vi.mock('@/store/useCronStore', () => ({
  default: Object.assign(() => cronStoreState, { getState: () => ({ jobs: [] }) }),
}));

// Every sibling surface of the detail view is replaced by an empty stand-in: only what this view mounts is under test.
vi.mock('../CronTimeoutEditor', () => ({ CronTimeoutEditor: () => <div data-testid="timeout-editor" /> }));
vi.mock('../CronRunItem', () => ({ default: () => null }));
vi.mock('../CronJobAuditPanel', () => ({ CronJobAuditPanel: () => null }));
vi.mock('../CronAcceptanceCriteriaEditor', () => ({ AcceptanceCriteriaEditor: () => null }));
vi.mock('../CronDeliveryEditors', () => ({ DeliveryEditor: () => null, FailureDeliveryEditor: () => null }));
vi.mock('../CronMonitorEditors', () => ({ IncrementalMonitorEditor: () => null }));
vi.mock('../CronAdvancedEditors', () => ({
  CooldownEditor: () => null,
  MaxFiresEditor: () => null,
  ExpiresAtEditor: () => null,
  SessionTargetEditor: () => null,
  FailureAlertEditor: () => null,
  RunRetentionEditor: () => null,
  SkipIfActiveEditor: () => null,
  ContextFromEditor: () => null,
  PreConditionEditor: () => null,
}));
vi.mock('../ActiveHoursEditor', () => ({ ActiveHoursEditor: () => null }));
vi.mock('../CapabilityEditor', () => ({ CapabilityEditor: () => null }));
vi.mock('../AllowedRootsEditor', () => ({ AllowedRootsEditor: () => null }));
vi.mock('../CronTriggerEditor', () => ({ TriggerEditor: () => null }));
vi.mock('../CronWorkflowTemplateBinding', () => ({ CronWorkflowTemplateDetail: () => null }));
vi.mock('../WorkflowTemplateEditor', () => ({ WorkflowTemplateEditor: () => null }));
vi.mock('@/components/features/memory/shared-context/SharedContextTargetBinding', () => ({
  SharedContextTargetBinding: () => null,
}));
vi.mock('@/lib/cron/cronCreateAuditGate', () => ({ needsSettingsAuditGate: () => false }));

import CronRunHistory from '../CronRunHistory';

const jobOfType = (jobType: CronJob['job_type']): CronJob =>
  ({ id: 'job-1', name: 'Nightly', job_type: jobType, status: 'active', timeout_seconds: 300 }) as unknown as CronJob;

describe('the job detail view and the run time limit editor', () => {
  it.each(['agent', 'shell', 'router'] as const)('offers the limit of a %s job', (jobType) => {
    render(<CronRunHistory job={jobOfType(jobType)} onBack={vi.fn()} />);

    expect(screen.getByTestId('timeout-editor')).toBeDefined();
  });

  it('offers no limit for a reminder, which is delivered at once', () => {
    render(<CronRunHistory job={jobOfType('reminder')} onBack={vi.fn()} />);

    expect(screen.queryByTestId('timeout-editor')).toBeNull();
  });
});
