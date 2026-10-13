/**
 * Retrying a user bubble whose send failed.
 *
 * Real scenario: the connection drops while sending a message with a PDF attached and the user clicks Retry. The
 * retry must carry the PDF the bubble shows (not whatever the user staged for the next message), and a request the
 * agent does not take must hand the text back to the composer instead of losing it together with the replaced
 * bubble. When the user has already started the next message, the composer stays as it is and the text stays
 * reachable through the input history.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { addInputHistory } from '@/hooks/message-input/useInputHistory';
import { showI18nToast } from '@/services/i18nToastService';
import useChatStore from '@/store/useChatStore';
import { retryFailedUserMessage } from '../userMessageResend';
import {
  REPORT_PDF,
  STAGED_PNG,
  agentConfig,
  bubble,
  composer,
  failedBubble,
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

const busyError = () => Object.assign(new Error('Agent is busy'), { name: 'AgentBusyError' });

beforeEach(resetResendWorld);

afterEach(() => {
  vi.restoreAllMocks();
});

describe('retryFailedUserMessage', () => {
  it('replaces the failed bubble and resends its text with its own attachments', async () => {
    await retryFailedUserMessage(failedBubble);

    expect(transcript()).toEqual(['r-1', 'r-1']);
    expect(sentRequest()).toEqual({ content: 'summarize the report', attachments: { files: [REPORT_PDF] } });
  });

  it('keeps files staged for the next message out of the retry', async () => {
    useChatStore.setState({ files: [STAGED_PNG] });

    await retryFailedUserMessage({ ...failedBubble, files: undefined });

    expect(sentRequest().attachments).toEqual({ files: [] });
    expect(composer().files).toEqual([STAGED_PNG]);
  });

  it('leaves the composer alone once the agent took the retry', async () => {
    await retryFailedUserMessage(failedBubble);

    expect(composer()).toEqual({ inputMessage: '', files: [], pendingExplicitSkillActivation: null });
    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('hands the text and attachments back to the composer when the agent did not take it', async () => {
    sendMessage.mockResolvedValue(false);

    await retryFailedUserMessage(failedBubble);

    expect(composer()).toEqual({
      inputMessage: 'summarize the report',
      files: [REPORT_PDF],
      pendingExplicitSkillActivation: null,
    });
    // The store has already told the user why the request was refused.
    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('restores the skill chip and the plain text of a skill-driven message', async () => {
    sendMessage.mockResolvedValue(false);

    await retryFailedUserMessage(
      bubble('user', 'r-2', '[use writer_skill] [instruction: formal tone] draft the memo', { sendFailed: true }),
    );

    expect(composer()).toEqual({
      inputMessage: 'draft the memo',
      files: [],
      pendingExplicitSkillActivation: { skillNames: ['writer_skill'], instruction: 'formal tone' },
    });
  });

  it('never overwrites a composer the user started in the meantime', async () => {
    sendMessage.mockImplementation(async () => {
      useChatStore.setState({ inputMessage: 'another idea' });
      return false;
    });

    await retryFailedUserMessage(failedBubble);

    expect(composer()).toEqual({ inputMessage: 'another idea', files: [], pendingExplicitSkillActivation: null });
  });

  describe('when the composer cannot take the text back', () => {
    const userMovedOn = async () => {
      useChatStore.setState({ inputMessage: 'another idea' });
      return false;
    };

    it('keeps the text in the input history of the current agent, as a direct send does', async () => {
      useChatStore.setState({ agentConfig: agentConfig('agent-7') });
      sendMessage.mockImplementation(userMovedOn);

      await retryFailedUserMessage(failedBubble);

      expect(addInputHistory).toHaveBeenCalledTimes(1);
      expect(addInputHistory).toHaveBeenCalledWith('summarize the report', 'agent-7');
    });

    it('records nothing in an incognito chat, which never persists what the user typed', async () => {
      useChatStore.setState({ incognitoMode: true });
      sendMessage.mockImplementation(userMovedOn);

      await retryFailedUserMessage(failedBubble);

      expect(addInputHistory).not.toHaveBeenCalled();
    });

    it('records nothing when the text went back to the composer', async () => {
      sendMessage.mockResolvedValue(false);

      await retryFailedUserMessage(failedBubble);

      expect(composer().inputMessage).toBe('summarize the report');
      expect(addInputHistory).not.toHaveBeenCalled();
    });

    it('leaves the composer of another open chat alone and files the text under the agent it was sent to', async () => {
      useChatStore.setState({ agentConfig: agentConfig('agent-7') });
      sendMessage.mockImplementation(async () => {
        useChatStore.setState({ chatId: 'chat-other', agentConfig: agentConfig('agent-9') });
        return false;
      });

      await retryFailedUserMessage(failedBubble);

      expect(composer().inputMessage).toBe('');
      expect(addInputHistory).toHaveBeenCalledTimes(1);
      expect(addInputHistory).toHaveBeenCalledWith('summarize the report', 'agent-7');
    });

    it('records nothing for an incognito chat, even when a regular chat is open by then', async () => {
      useChatStore.setState({ incognitoMode: true });
      sendMessage.mockImplementation(async () => {
        useChatStore.setState({ chatId: 'chat-other', incognitoMode: false });
        return false;
      });

      await retryFailedUserMessage(failedBubble);

      expect(addInputHistory).not.toHaveBeenCalled();
    });
  });

  it('restores the text and explains that the agent is busy when the server still runs another turn', async () => {
    sendMessage.mockRejectedValue(busyError());

    await retryFailedUserMessage(failedBubble);

    expect(composer().inputMessage).toBe('summarize the report');
    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.sendBlocked.title',
      undefined,
      expect.objectContaining({ descriptionKey: 'chat.sendBlocked.busyDescription' }),
    );
  });

  it('restores the text and reports a fixed line when the request fails unexpectedly', async () => {
    const failure = new Error('internal: reducer exploded');
    sendMessage.mockRejectedValue(failure);

    await retryFailedUserMessage(failedBubble);

    expect(composer().inputMessage).toBe('summarize the report');
    expect(showI18nToast).toHaveBeenCalledTimes(1);
    const options = vi.mocked(showI18nToast).mock.calls[0][2];
    expect(options).toMatchObject({ descriptionKey: 'chat.messageFailed.generic', type: 'error' });
    expect(options).not.toHaveProperty('descriptionValues');
    expect(console.error).toHaveBeenCalledWith(expect.any(String), failure);
  });
});
