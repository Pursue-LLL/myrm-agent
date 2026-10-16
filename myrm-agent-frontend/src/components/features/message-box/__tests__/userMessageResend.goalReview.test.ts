/**
 * Sending the feedback of a rejected goal review.
 *
 * Real scenario: a long-running goal ends in human review, the user types "use the staging database" and clicks
 * Reject & Retry. The goal is active again by then and the panel is gone, so the feedback goes out as the next
 * message of that chat: it must not take (or consume) files the user staged for something else, it must not land in
 * a chat the user opened while the reject request was out, and a feedback the agent does not take must come back to
 * the user instead of vanishing with the panel.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { addInputHistory } from '@/hooks/message-input/useInputHistory';
import { showI18nToast } from '@/services/i18nToastService';
import useChatStore from '@/store/useChatStore';
import { readSendOrigin, sendGoalReviewFeedback } from '../userMessageResend';
import {
  STAGED_PNG,
  agentConfig,
  composer,
  resetResendWorld,
  sendMessage,
  sentRequest,
  transcript,
} from './userMessageResendTestKit';

vi.mock('@/hooks/message-input/useInputHistory', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/message-input/useInputHistory')>();
  return { ...actual, addInputHistory: vi.fn() };
});

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

const FEEDBACK = 'use the staging database';
const busyError = () => Object.assign(new Error('Agent is busy'), { name: 'AgentBusyError' });

beforeEach(() => {
  resetResendWorld();
  useChatStore.setState({ agentConfig: agentConfig('agent-7') });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('sendGoalReviewFeedback', () => {
  it('sends the feedback as the next message of the chat, leaving the transcript as it is', async () => {
    await sendGoalReviewFeedback(readSendOrigin(), FEEDBACK);

    expect(sentRequest().content).toBe(FEEDBACK);
    expect(transcript()).toEqual(['r-1', 'r-1', 'r-2']);
  });

  it('carries no file and leaves the ones staged for the next message in the composer', async () => {
    useChatStore.setState({ files: [STAGED_PNG] });

    await sendGoalReviewFeedback(readSendOrigin(), FEEDBACK);

    expect(sentRequest().attachments).toEqual({ files: [] });
    expect(composer().files).toEqual([STAGED_PNG]);
  });

  it('leaves the composer and the notices alone once the agent took the feedback', async () => {
    await sendGoalReviewFeedback(readSendOrigin(), FEEDBACK);

    expect(composer()).toEqual({ inputMessage: '', files: [], pendingExplicitSkillActivation: null });
    expect(showI18nToast).not.toHaveBeenCalled();
    expect(addInputHistory).not.toHaveBeenCalled();
  });

  it('hands the feedback back to an empty composer when the agent did not take it', async () => {
    sendMessage.mockResolvedValue(false);

    await sendGoalReviewFeedback(readSendOrigin(), FEEDBACK);

    expect(composer().inputMessage).toBe(FEEDBACK);
    // The store has already told the user why the request was refused.
    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('keeps a message the user is writing and files the feedback under the input history instead', async () => {
    useChatStore.setState({ inputMessage: 'something else I was writing' });
    sendMessage.mockResolvedValue(false);

    await sendGoalReviewFeedback(readSendOrigin(), FEEDBACK);

    expect(composer().inputMessage).toBe('something else I was writing');
    expect(addInputHistory).toHaveBeenCalledWith(FEEDBACK, 'agent-7');
  });

  it('explains that the agent is busy and returns the feedback when the server still runs another turn', async () => {
    sendMessage.mockRejectedValue(busyError());

    await sendGoalReviewFeedback(readSendOrigin(), FEEDBACK);

    expect(composer().inputMessage).toBe(FEEDBACK);
    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.sendBlocked.title',
      undefined,
      expect.objectContaining({ descriptionKey: 'chat.sendBlocked.busyDescription' }),
    );
  });

  it('returns the feedback and reports a fixed line when the request fails unexpectedly', async () => {
    const failure = new Error('internal: reducer exploded');
    sendMessage.mockRejectedValue(failure);

    await sendGoalReviewFeedback(readSendOrigin(), FEEDBACK);

    expect(composer().inputMessage).toBe(FEEDBACK);
    const options = vi.mocked(showI18nToast).mock.calls[0][2];
    expect(options).toMatchObject({ descriptionKey: 'chat.messageFailed.generic', type: 'error' });
    expect(options).not.toHaveProperty('descriptionValues');
    expect(console.error).toHaveBeenCalledWith(expect.any(String), failure);
  });

  describe('when another chat was opened while the reject request was out', () => {
    const openAnotherChat = () =>
      useChatStore.setState({ chatId: 'chat-other', agentConfig: agentConfig('agent-9'), inputMessage: '' });

    it('sends nothing into it', async () => {
      const origin = readSendOrigin();
      openAnotherChat();

      await sendGoalReviewFeedback(origin, FEEDBACK);

      expect(sendMessage).not.toHaveBeenCalled();
      expect(composer().inputMessage).toBe('');
    });

    it('files the feedback under the agent of the review chat and tells the user it was not sent', async () => {
      const origin = readSendOrigin();
      openAnotherChat();

      await sendGoalReviewFeedback(origin, FEEDBACK);

      expect(addInputHistory).toHaveBeenCalledWith(FEEDBACK, 'agent-7');
      expect(showI18nToast).toHaveBeenCalledWith(
        'chat.messageFailed.title',
        undefined,
        expect.objectContaining({ descriptionKey: 'chat.messageFailed.generic', type: 'error' }),
      );
    });

    it('records nothing for an incognito review chat, which never persists what the user typed', async () => {
      useChatStore.setState({ incognitoMode: true });
      const origin = readSendOrigin();
      openAnotherChat();

      await sendGoalReviewFeedback(origin, FEEDBACK);

      expect(addInputHistory).not.toHaveBeenCalled();
    });
  });
});
