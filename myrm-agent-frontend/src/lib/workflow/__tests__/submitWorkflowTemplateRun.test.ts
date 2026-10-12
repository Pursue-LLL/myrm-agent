import { beforeEach, describe, expect, it, vi } from 'vitest';
import useChatStore from '@/store/useChatStore';
import { submitWorkflowTemplateRun } from '../submitWorkflowTemplateRun';

vi.mock('@/lib/chat/ensureActiveChatId', () => ({
  ensureActiveChatId: vi.fn(async () => 'chat-1'),
}));

const RUN = { templateId: 'tpl-1', query: 'run it', displayName: 'Tpl' };

function stubChat(outcome: () => Promise<boolean>, { loading = false }: { loading?: boolean } = {}) {
  const sendMessage = vi.fn(outcome);
  useChatStore.setState({ sendMessage, loading });
  return sendMessage;
}

describe('submitWorkflowTemplateRun', () => {
  beforeEach(() => {
    useChatStore.getState().clearPendingWorkflowTemplate();
    useChatStore.getState().setIsWorkflowMode(false);
  });

  it('reports the run as started once the chat took the turn, and leaves arming to the chat', async () => {
    const sendMessage = stubChat(async () => true);

    await expect(submitWorkflowTemplateRun(RUN)).resolves.toEqual({ ok: true, chatId: 'chat-1' });

    expect(sendMessage).toHaveBeenCalledWith('run it');
    // A newer arming made while the turn streamed must survive, so a settled turn is never disarmed here.
    expect(useChatStore.getState().pendingWorkflowTemplateId).toBe('tpl-1');
  });

  it('reports a refused send and disarms, so the next ordinary message is not sent as a workflow run', async () => {
    stubChat(async () => false);

    await expect(submitWorkflowTemplateRun(RUN)).resolves.toEqual({ ok: false, reason: 'refused' });

    const state = useChatStore.getState();
    expect(state.pendingWorkflowTemplateId).toBeNull();
    expect(state.isWorkflowMode).toBe(false);
  });

  it('reports an error and disarms when the send throws', async () => {
    stubChat(async () => {
      throw new Error('boom');
    });

    await expect(submitWorkflowTemplateRun(RUN)).resolves.toEqual({ ok: false, reason: 'error' });

    const state = useChatStore.getState();
    expect(state.pendingWorkflowTemplateId).toBeNull();
    expect(state.isWorkflowMode).toBe(false);
  });

  it('does not arm or send while the chat is still loading', async () => {
    const sendMessage = stubChat(async () => true, { loading: true });

    await expect(submitWorkflowTemplateRun(RUN)).resolves.toEqual({ ok: false, reason: 'busy' });

    expect(sendMessage).not.toHaveBeenCalled();
    expect(useChatStore.getState().pendingWorkflowTemplateId).toBeNull();
  });
});
