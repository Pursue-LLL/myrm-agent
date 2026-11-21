import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SkillDraft } from '@/services/skill';

const mockApproveSkillDraft = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill', () => ({
  listSkillDrafts: vi.fn(),
  getUnreviewedDraftCount: vi.fn(),
  approveSkillDraft: (...args: unknown[]) => mockApproveSkillDraft(...args),
  rejectSkillDraft: vi.fn(),
}));

import { useSkillDraftStore } from '../useSkillDraftStore';

const REFUSAL = "Invalid skill name: '9-unwritable'";

function draftNamed(id: string, name: string): SkillDraft {
  return {
    id,
    agent_id: 'agent-1',
    chat_id: null,
    draft_type: 'skill_draft',
    name,
    description: 'Summarize the weekly report',
    trigger_condition: null,
    skill_steps: null,
    content: null,
    status: 'PENDING_REVIEW',
    reviewed_at: null,
    created_at: '2026-07-30T00:00:00Z',
  };
}

describe('useSkillDraftStore approveDraft', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSkillDraftStore.setState({
      drafts: [draftNamed('d1', 'writable-skill'), draftNamed('d2', '9-unwritable')],
      unreviewedCount: 2,
      error: null,
    });
  });

  it('drops the draft and lowers the unreviewed count once the server wrote it', async () => {
    mockApproveSkillDraft.mockResolvedValue({
      id: 'd1',
      status: 'APPROVED',
      materialized: true,
      materialized_type: 'skill',
    });

    await useSkillDraftStore.getState().approveDraft('d1', 'writable-skill');

    const { drafts, unreviewedCount } = useSkillDraftStore.getState();
    expect(drafts.map((d) => d.id)).toEqual(['d2']);
    expect(unreviewedCount).toBe(1);
  });

  it('keeps the draft and the count when the server could not write it, and hands the reason back', async () => {
    const refusal = { id: 'd2', status: 'APPROVED', materialized: false, error: REFUSAL };
    mockApproveSkillDraft.mockResolvedValue(refusal);

    const result = await useSkillDraftStore.getState().approveDraft('d2', '9-unwritable');

    expect(result).toEqual(refusal);
    const { drafts, unreviewedCount } = useSkillDraftStore.getState();
    expect(drafts.map((d) => d.id)).toEqual(['d1', 'd2']);
    expect(unreviewedCount).toBe(2);
  });

  it('keeps the draft, records the error and rethrows when the request fails', async () => {
    mockApproveSkillDraft.mockRejectedValue(new Error('network down'));

    await expect(useSkillDraftStore.getState().approveDraft('d1', 'writable-skill')).rejects.toThrow('network down');

    const { drafts, unreviewedCount, error } = useSkillDraftStore.getState();
    expect(drafts).toHaveLength(2);
    expect(unreviewedCount).toBe(2);
    expect(error).toBe('network down');
  });
});
