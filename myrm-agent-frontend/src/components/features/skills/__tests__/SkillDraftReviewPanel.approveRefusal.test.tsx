/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApproveDraft = vi.hoisted(() => vi.fn());
const mockToast = vi.hoisted(() => vi.fn());

const storeState = vi.hoisted(() => ({
  drafts: [{ id: 'd1', name: 'my-skill', draft_type: 'skill_draft', created_at: '2026-07-30T00:00:00Z' }],
  unreviewedCount: 1,
  isLoading: false,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}));

vi.mock('@/store/useAuthStore', () => ({
  default: () => ({ user: { id: 'user-1' } }),
}));

vi.mock('@/store/skill/useSkillDraftStore', () => ({
  useSkillDraftStore: () => ({
    drafts: storeState.drafts,
    unreviewedCount: storeState.unreviewedCount,
    isLoading: storeState.isLoading,
    fetchDrafts: vi.fn(),
    approveDraft: mockApproveDraft,
    rejectDraft: vi.fn(),
  }),
}));

const stableT = (key: string, values?: Record<string, string>) => (values?.name ? `${key}:${values.name}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/primitives/collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import SkillDraftReviewPanel from '../SkillDraftReviewPanel';

const REFUSAL = "Invalid skill name: '9-unwritable'";

async function pressApprove() {
  const user = userEvent.setup();
  render(<SkillDraftReviewPanel />);
  await user.click(screen.getByRole('button', { name: 'draft.approveAction' }));
}

describe('SkillDraftReviewPanel refused approval', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('says why when the server could not write the draft and offers no invoke guide', async () => {
    mockApproveDraft.mockResolvedValue({ id: 'd1', status: 'APPROVED', materialized: false, error: REFUSAL });

    await pressApprove();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({
      title: 'draft.approveFailed',
      description: REFUSAL,
      variant: 'destructive',
    });
    expect(screen.queryByText('draft.invokeGuideTitle')).not.toBeInTheDocument();
  });

  it('names the draft when the refusal carries no reason', async () => {
    mockApproveDraft.mockResolvedValue({ id: 'd1', status: 'APPROVED', materialized: false });

    await pressApprove();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({
      title: 'draft.approveFailed',
      description: 'my-skill',
      variant: 'destructive',
    });
  });

  it('reports a failed request without a reason', async () => {
    mockApproveDraft.mockRejectedValue(new Error('network down'));

    await pressApprove();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({ title: 'draft.approveFailed', variant: 'destructive' });
  });
});
