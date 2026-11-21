import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApproveSkillDraft = vi.hoisted(() => vi.fn());
const mockApiRequest = vi.hoisted(() => vi.fn());

vi.mock('../core', () => ({
  approveSkillDraft: (...args: unknown[]) => mockApproveSkillDraft(...args),
  rejectSkillDraft: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

import { approveSkillGrowthCase, type SkillGrowthCaseSummary } from '../growth';

const REFUSAL = "Invalid skill name: '9-unwritable'";

function growthCase(id: string, source: SkillGrowthCaseSummary['source']): SkillGrowthCaseSummary {
  return {
    id,
    source,
    status: 'PENDING_REVIEW',
    skillName: '9-unwritable',
    skillId: null,
    growthType: 'new_skill',
    title: 'Weekly report',
    summary: 'Summarize the weekly report',
    description: null,
    confidence: null,
    applyStatus: null,
    applyError: null,
    reasonCode: null,
    remediation: null,
    runtimeFailure: null,
    chatId: null,
    hasDiff: false,
    hasTrajectory: false,
    hasTriggerCondition: false,
    hasSkillSteps: false,
    createdAt: '2026-07-30T00:00:00Z',
    impactedDependents: [],
    verificationProof: null,
  };
}

describe('approveSkillGrowthCase', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reports a draft the server could not write as failed, with the server reason, although the response status says approved', async () => {
    mockApproveSkillDraft.mockResolvedValue({ id: 'd1', status: 'APPROVED', materialized: false, error: REFUSAL });

    const result = await approveSkillGrowthCase(growthCase('draft:d1', 'draft'));

    expect(mockApproveSkillDraft).toHaveBeenCalledWith('d1', '9-unwritable');
    expect(result).toEqual({
      status: 'APPROVED',
      skill_id: null,
      apply_status: 'FAILED',
      apply_error: REFUSAL,
      remediation: REFUSAL,
    });
  });

  it('reports a draft the server wrote as applied', async () => {
    mockApproveSkillDraft.mockResolvedValue({
      id: 'd1',
      status: 'APPROVED',
      materialized: true,
      materialized_type: 'skill',
    });

    const result = await approveSkillGrowthCase(growthCase('draft:d1', 'draft'));

    expect(result).toMatchObject({ status: 'APPROVED', apply_status: 'APPLIED', apply_error: null, remediation: null });
  });

  it('sends an evolution proposal to its own approve endpoint', async () => {
    mockApiRequest.mockResolvedValue({ status: 'APPROVED', apply_status: 'APPLIED' });

    await approveSkillGrowthCase(growthCase('evolution:e1', 'evolution'));

    expect(mockApiRequest).toHaveBeenCalledWith('/evolution/pending/e1/approve', { method: 'POST' });
    expect(mockApproveSkillDraft).not.toHaveBeenCalled();
  });
});
