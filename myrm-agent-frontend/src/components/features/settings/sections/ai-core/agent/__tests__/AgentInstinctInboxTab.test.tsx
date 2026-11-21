/** @vitest-environment jsdom */
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SkillDraft } from '@/services/skill';

const mockListSkillDrafts = vi.hoisted(() => vi.fn());
const mockApproveSkillDraft = vi.hoisted(() => vi.fn());
const mockRejectSkillDraft = vi.hoisted(() => vi.fn());
const mockToast = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill', () => ({
  listSkillDrafts: (...args: unknown[]) => mockListSkillDrafts(...args),
  approveSkillDraft: (...args: unknown[]) => mockApproveSkillDraft(...args),
  rejectSkillDraft: (...args: unknown[]) => mockRejectSkillDraft(...args),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import { AgentInstinctInboxTab } from '../AgentInstinctInboxTab';

const REFUSAL = "Invalid skill name: '9-unwritable'";

const draft: SkillDraft = {
  id: 'draft-1',
  agent_id: 'agent-1',
  chat_id: null,
  draft_type: 'skill_draft',
  name: '9-unwritable',
  description: 'Summarize the weekly report',
  trigger_condition: null,
  skill_steps: null,
  content: null,
  status: 'PENDING_REVIEW',
  reviewed_at: null,
  created_at: '2026-07-30T00:00:00Z',
};

async function pressApprove() {
  const user = userEvent.setup();
  render(<AgentInstinctInboxTab agentId="agent-1" />);
  await user.click(await screen.findByTestId('instinct-approve-btn'));
}

describe('AgentInstinctInboxTab approval', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListSkillDrafts.mockResolvedValue({ drafts: [draft], total: 1 });
  });

  it('reports success once the server wrote the draft', async () => {
    mockApproveSkillDraft.mockResolvedValue({
      id: 'draft-1',
      status: 'APPROVED',
      materialized: true,
      materialized_type: 'skill',
    });

    await pressApprove();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({ title: 'approveSuccess' });
  });

  it('says why when the server could not write the draft, and lists the draft again', async () => {
    mockApproveSkillDraft.mockResolvedValue({
      id: 'draft-1',
      status: 'APPROVED',
      materialized: false,
      error: REFUSAL,
    });

    await pressApprove();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({
      title: 'approveFailed',
      description: REFUSAL,
      variant: 'destructive',
    });
    await waitFor(() => expect(mockListSkillDrafts).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId('instinct-draft-card')).toBeInTheDocument();
  });

  it('reports a failed request without a reason', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockApproveSkillDraft.mockRejectedValue(new Error('network down'));

    await pressApprove();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({ title: 'approveFailed', variant: 'destructive' });
  });
});

describe('AgentInstinctInboxTab rejection', () => {
  async function pressDismiss() {
    const user = userEvent.setup();
    render(<AgentInstinctInboxTab agentId="agent-1" />);
    await user.click(await screen.findByTestId('instinct-dismiss-btn'));
  }

  beforeEach(() => {
    vi.clearAllMocks();
    mockListSkillDrafts.mockResolvedValue({ drafts: [draft], total: 1 });
  });

  it('dismisses the draft and lists the drafts again', async () => {
    mockRejectSkillDraft.mockResolvedValue({ id: 'draft-1', status: 'REJECTED' });

    await pressDismiss();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockRejectSkillDraft).toHaveBeenCalledWith('draft-1');
    expect(mockToast).toHaveBeenCalledWith({ title: 'rejectSuccess' });
    await waitFor(() => expect(mockListSkillDrafts).toHaveBeenCalledTimes(2));
  });

  it('reports a failed dismissal and keeps the list as it was', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockRejectSkillDraft.mockRejectedValue(new Error('network down'));

    await pressDismiss();

    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
    expect(mockToast).toHaveBeenCalledWith({ title: 'rejectFailed', variant: 'destructive' });
    expect(mockListSkillDrafts).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('instinct-draft-card')).toBeInTheDocument();
  });
});

describe('AgentInstinctInboxTab list loading', () => {
  const neverSettles = () => new Promise(() => undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    mockListSkillDrafts.mockResolvedValue({ drafts: [draft], total: 1 });
  });

  it("opens another agent's inbox on the placeholder instead of the previous agent's drafts", async () => {
    const { rerender } = render(<AgentInstinctInboxTab agentId="agent-1" />);
    expect(await screen.findByTestId('instinct-draft-card')).toBeInTheDocument();

    mockListSkillDrafts.mockImplementation(neverSettles);
    rerender(<AgentInstinctInboxTab agentId="agent-2" />);

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(screen.queryByTestId('instinct-draft-card')).not.toBeInTheDocument();
  });

  it('shows the placeholder while the list is fetched again after an action', async () => {
    mockApproveSkillDraft.mockResolvedValue({ id: 'draft-1', status: 'APPROVED', materialized: true });

    const user = userEvent.setup();
    render(<AgentInstinctInboxTab agentId="agent-1" />);
    const approve = await screen.findByTestId('instinct-approve-btn');
    mockListSkillDrafts.mockImplementation(neverSettles);
    await user.click(approve);

    expect(await screen.findByText('loading')).toBeInTheDocument();
    expect(screen.queryByTestId('instinct-draft-card')).not.toBeInTheDocument();
  });

  it("ignores a slower answer that belongs to the previous agent's request", async () => {
    let answerAgentOne: (value: { drafts: SkillDraft[]; total: number }) => void = () => undefined;
    mockListSkillDrafts.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          answerAgentOne = resolve;
        }),
    );
    const { rerender } = render(<AgentInstinctInboxTab agentId="agent-1" />);

    const agentTwoDraft: SkillDraft = { ...draft, id: 'draft-2', agent_id: 'agent-2', name: 'agent-two-draft' };
    mockListSkillDrafts.mockResolvedValueOnce({ drafts: [agentTwoDraft], total: 1 });
    rerender(<AgentInstinctInboxTab agentId="agent-2" />);
    expect(await screen.findByTestId('instinct-draft-card')).toHaveAttribute('data-draft-name', 'agent-two-draft');

    await act(async () => {
      answerAgentOne({ drafts: [draft], total: 1 });
    });

    expect(screen.getByTestId('instinct-draft-card')).toHaveAttribute('data-draft-name', 'agent-two-draft');
  });
});
