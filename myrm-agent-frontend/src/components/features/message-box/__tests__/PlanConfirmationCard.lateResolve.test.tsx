/**
 * The plan card is marked resolved only when the plan it answered is still the one on its row.
 *
 * Real scenario: the user confirms a plan; the resumed run streams to its end before the card learns the outcome, and
 * the run may raise a fresh plan on the same row. Stamping the old answer onto that fresh plan would show an unreviewed
 * plan as already confirmed. A resume that cannot be sent reports a failure instead of marking the plan confirmed.
 * A plan another client answered first (HTTP 409) settles as handled elsewhere, never as a failed submit.
 * Runs the real card against the real store, replacing only the chat services.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { resumePlanConfirmStream } from '@/services/chat';
import type { Message } from '@/store/chat/types';
import { ApprovalAlreadyResolvedError } from '@/store/chat/streamErrors';
import useChatStore from '@/store/useChatStore';

import PlanConfirmationCard from '../PlanConfirmationCard';

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/services/chat', () => ({
  submitPlanConfirmResponse: vi.fn(),
  resumePlanConfirmStream: vi.fn(),
}));

const MESSAGE_ID = 'msg-plan-1';
const planItems = [{ id: 'task-1', content: 'Collect the figures' }];

const waitingPlan: Message = {
  messageId: MESSAGE_ID,
  chatId: 'chat-1',
  createdAt: new Date(),
  content: '',
  role: 'assistant',
  planConfirmation: { plan: '1. Collect the figures', status: 'waiting', source: 'general_agent', planItems },
};

const planStatus = () => useChatStore.getState().messages[0]?.planConfirmation?.status;

function answerPlan(button: 'confirm' | 'skip'): void {
  render(
    <PlanConfirmationCard
      messageId={MESSAGE_ID}
      plan="1. Collect the figures"
      status="waiting"
      planItems={planItems}
      source="general_agent"
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: button }));
}

const confirmPlan = () => answerPlan('confirm');

beforeEach(() => {
  vi.mocked(resumePlanConfirmStream).mockReset();
  vi.mocked(toast.error).mockClear();
  useChatStore.setState({ chatId: 'chat-1', messages: [structuredClone(waitingPlan)] });
});

describe('PlanConfirmationCard resume', () => {
  it('marks the plan confirmed once the resumed run has ended', async () => {
    vi.mocked(resumePlanConfirmStream).mockResolvedValue(undefined);

    confirmPlan();

    await waitFor(() => expect(planStatus()).toBe('confirmed'));
    expect(resumePlanConfirmStream).toHaveBeenCalledWith(MESSAGE_ID, { action: 'confirm' });
  });

  it('leaves a second plan the resumed run raised on the same row waiting', async () => {
    vi.mocked(resumePlanConfirmStream).mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].planConfirmation = {
          plan: '1. Publish the report',
          status: 'waiting',
          source: 'general_agent',
          planItems: [{ id: 'task-2', content: 'Publish the report' }],
        };
      });
    });

    confirmPlan();

    await waitFor(() => expect(screen.getByRole('button', { name: 'confirm' })).toBeEnabled());
    expect(planStatus()).toBe('waiting');
    expect(useChatStore.getState().messages[0].planConfirmation?.plan).toBe('1. Publish the report');
  });

  it('shows the choice the user made when the stream already marked the same plan confirmed', async () => {
    vi.mocked(resumePlanConfirmStream).mockImplementation(async () => {
      useChatStore.setState((state) => {
        const plan = state.messages[0].planConfirmation;
        if (plan) {
          plan.status = 'confirmed';
        }
      });
    });

    answerPlan('skip');

    await waitFor(() => expect(planStatus()).toBe('skipped'));
  });

  it('keeps the plan waiting and reports the failure when the resume cannot be sent', async () => {
    vi.mocked(resumePlanConfirmStream).mockRejectedValue(new Error('Plan confirm resume needs an open chat'));

    confirmPlan();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('submitFailed'));
    expect(planStatus()).toBe('waiting');
  });

  it.each(['confirm', 'skip'] as const)(
    'settles the plan as handled elsewhere, without a failure notice, when %s finds it already answered',
    async (button) => {
      vi.mocked(resumePlanConfirmStream).mockRejectedValue(new ApprovalAlreadyResolvedError());

      answerPlan(button);

      await waitFor(() => expect(planStatus()).toBe('handled'));
      expect(toast.error).not.toHaveBeenCalled();
    },
  );

  it('leaves a newer plan on the row waiting when the answered plan was already handled elsewhere', async () => {
    vi.mocked(resumePlanConfirmStream).mockImplementation(async () => {
      useChatStore.setState((state) => {
        state.messages[0].planConfirmation = {
          plan: '1. Publish the report',
          status: 'waiting',
          source: 'general_agent',
          planItems: [{ id: 'task-2', content: 'Publish the report' }],
        };
      });
      throw new ApprovalAlreadyResolvedError();
    });

    confirmPlan();

    await waitFor(() => expect(screen.getByRole('button', { name: 'confirm' })).toBeEnabled());
    expect(planStatus()).toBe('waiting');
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('shows a settled note with no actions for a plan handled elsewhere', () => {
    render(<PlanConfirmationCard messageId={MESSAGE_ID} plan="1. Collect the figures" status="handled" />);

    const note = screen.getByText('handledElsewhere');
    expect(note).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    // The answer is unknown, so the note must not borrow the success look of a confirmed plan.
    expect(note.parentElement?.className).not.toContain('emerald');
  });
});
