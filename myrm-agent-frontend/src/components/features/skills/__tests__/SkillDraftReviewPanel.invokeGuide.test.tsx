/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApproveDraft = vi.fn();
const mockFetchDrafts = vi.fn();
const mockToast = vi.hoisted(() => vi.fn());

const storeState = vi.hoisted(() => ({
  drafts: [
    {
      id: 'd1',
      name: 'my-skill',
      draft_type: 'skill_draft',
      created_at: '2026-07-30T00:00:00Z',
    },
  ] as Array<{
    id: string;
    name: string;
    draft_type: string;
    created_at: string;
  }>,
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
    fetchDrafts: mockFetchDrafts,
    approveDraft: mockApproveDraft,
    rejectDraft: vi.fn(),
  }),
}));

const stableT = (key: string, values?: Record<string, string>) => {
  if (values?.name) return `${key}:${values.name}`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/primitives/collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

Object.assign(navigator, {
  clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
});

import SkillDraftReviewPanel from '../SkillDraftReviewPanel';

describe('SkillDraftReviewPanel invoke guide', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.drafts = [
      {
        id: 'd1',
        name: 'my-skill',
        draft_type: 'skill_draft',
        created_at: '2026-07-30T00:00:00Z',
      },
    ];
    storeState.unreviewedCount = 1;
    storeState.isLoading = false;
    mockApproveDraft.mockImplementation(async () => {
      storeState.unreviewedCount = 0;
      storeState.drafts = [];
      return {
        materialized: true,
        materialized_type: 'skill',
        skill_name: 'my-skill',
      };
    });
  });

  it('keeps invoke guide visible after the last draft is approved', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<SkillDraftReviewPanel />);

    await user.click(screen.getByRole('button', { name: 'draft.approveAction' }));

    await waitFor(() => {
      expect(mockApproveDraft).toHaveBeenCalled();
    });

    rerender(<SkillDraftReviewPanel />);

    expect(screen.getByText('draft.invokeGuideTitle')).toBeInTheDocument();
    expect(screen.getByText('[use my-skill]')).toBeInTheDocument();
  });
});
