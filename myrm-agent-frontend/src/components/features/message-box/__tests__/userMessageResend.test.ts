/**
 * Resending a user bubble: retrying a failed send and editing a sent message.
 *
 * Real scenarios: the connection drops while sending a message with a PDF attached and the user clicks Retry; the
 * user edits a question after a minute and the request is refused. The retry must carry the PDF the bubble shows
 * (not whatever the user staged for the next message), and a request the agent does not take must hand the text
 * back to the composer instead of losing it together with the replaced bubble. When the user has already started
 * the next message, the composer stays as it is and the text stays reachable through the input history.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { addInputHistory } from '@/hooks/message-input/useInputHistory';
import { truncateAfterMessage } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import type { ChatState, File as ChatFile, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { resendEditedUserMessage, retryFailedUserMessage } from '../userMessageResend';

vi.mock('@/hooks/message-input/useInputHistory', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/message-input/useInputHistory')>();
  return { ...actual, addInputHistory: vi.fn() };
});

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return { ...actual, truncateAfterMessage: vi.fn() };
});

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

const CHAT_ID = 'chat-resend';
const REPORT_PDF: ChatFile = {
  id: 'f-report',
  fileName: 'report.pdf',
  fileExtension: 'pdf',
  fileType: 'uploaded',
  fileUrl: 'https://files.test/f-report',
};
const STAGED_PNG: ChatFile = {
  id: 'f-staged',
  fileName: 'staged.png',
  fileExtension: 'png',
  fileType: 'uploaded',
  fileUrl: 'https://files.test/f-staged',
};

function bubble(role: Message['role'], messageId: string, content: string, extra: Partial<Message> = {}): Message {
  return { messageId, chatId: CHAT_ID, role, content, createdAt: new Date(), ...extra } as Message;
}

const sendMessage = vi.fn<ChatState['sendMessage']>();
const SENT_CONTENT = 0;
const SENT_ATTACHMENTS = 8;

const sentRequest = () => {
  const call = sendMessage.mock.calls[0];
  return { content: call[SENT_CONTENT], attachments: call[SENT_ATTACHMENTS] };
};
const transcript = () => useChatStore.getState().messages.map((m) => m.messageId);
const composer = () => {
  const { inputMessage, files, pendingExplicitSkillActivation } = useChatStore.getState();
  return { inputMessage, files, pendingExplicitSkillActivation };
};
const busyError = () => Object.assign(new Error('Agent is busy'), { name: 'AgentBusyError' });
const agentConfig = (agentId: string) => ({ agentId }) as NonNullable<ChatState['agentConfig']>;

const failedBubble = bubble('user', 'r-2', 'summarize the report\n<current_datetime>2026-10-13</current_datetime>', {
  sendFailed: true,
  files: [REPORT_PDF],
});

beforeEach(() => {
  sendMessage.mockReset();
  sendMessage.mockResolvedValue(true);
  vi.mocked(truncateAfterMessage).mockReset();
  vi.mocked(truncateAfterMessage).mockResolvedValue({} as Awaited<ReturnType<typeof truncateAfterMessage>>);
  vi.mocked(showI18nToast).mockReset();
  vi.mocked(addInputHistory).mockReset();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  useChatStore.setState({
    chatId: CHAT_ID,
    messages: [bubble('user', 'r-1', 'hello'), bubble('assistant', 'r-1', 'hi there'), failedBubble],
    inputMessage: '',
    files: [],
    pendingExplicitSkillActivation: null,
    incognitoMode: false,
    agentConfig: null,
    sendMessage,
  });
});

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

describe('resendEditedUserMessage', () => {
  it('cuts the history at the edited bubble, then sends the edited text like a normal message', async () => {
    const edited = bubble('user', 'r-2', 'summarize the report', { files: [REPORT_PDF] });

    await resendEditedUserMessage(CHAT_ID, edited, 2, 'summarize only chapter 3');

    expect(truncateAfterMessage).toHaveBeenCalledWith(CHAT_ID, 'r-2');
    expect(vi.mocked(truncateAfterMessage).mock.invocationCallOrder[0]).toBeLessThan(
      sendMessage.mock.invocationCallOrder[0],
    );
    expect(transcript()).toEqual(['r-1', 'r-1']);
    // Like any normal send, the request takes the composer's own attachments, not those of the replaced bubble.
    expect(sentRequest()).toEqual({ content: 'summarize only chapter 3', attachments: undefined });
  });

  it('keeps the explicit skill activation of the original message', async () => {
    const edited = bubble('user', 'r-2', '[use writer_skill] [instruction: formal tone] draft the memo');

    await resendEditedUserMessage(CHAT_ID, edited, 2, 'draft the memo for finance');

    expect(sentRequest().content).toBe('[use writer_skill] [instruction: formal tone] draft the memo for finance');
  });

  it('hands the edited text, not the original, and the composer attachments it took back when the agent did not take it', async () => {
    useChatStore.setState({ files: [STAGED_PNG] });
    sendMessage.mockImplementation(async () => {
      // A request that settles without a turn clears the composer attachments it took.
      useChatStore.setState({ files: [] });
      return false;
    });
    const edited = bubble('user', 'r-2', 'summarize the report', { files: [REPORT_PDF] });

    await resendEditedUserMessage(CHAT_ID, edited, 2, 'summarize only chapter 3');

    expect(composer()).toEqual({
      inputMessage: 'summarize only chapter 3',
      files: [STAGED_PNG],
      pendingExplicitSkillActivation: null,
    });
  });

  it('keeps the edited text, without its skill wrapper, in the input history when the composer moved on', async () => {
    sendMessage.mockImplementation(async () => {
      useChatStore.setState({ inputMessage: 'another idea' });
      return false;
    });
    const edited = bubble('user', 'r-2', '[use writer_skill] [instruction: formal tone] draft the memo');

    await resendEditedUserMessage(CHAT_ID, edited, 2, 'draft the memo for finance');

    expect(composer().inputMessage).toBe('another idea');
    expect(addInputHistory).toHaveBeenCalledTimes(1);
    expect(addInputHistory).toHaveBeenCalledWith('draft the memo for finance', undefined);
  });

  describe('when the user opens another chat while the server cuts the history', () => {
    const OTHER_CHAT = [bubble('user', 'o-1', 'other question'), bubble('assistant', 'o-1', 'other answer')];
    const edited = bubble('user', 'r-2', 'summarize the report');

    /** Starts the edit, lets the user open another chat while the cut is in flight, then finishes the cut. */
    const editWhileLeaving = async (otherChat: Partial<ChatState> = {}) => {
      let finishCut: () => void = () => {};
      vi.mocked(truncateAfterMessage).mockReturnValue(
        new Promise((resolve) => {
          finishCut = () => resolve({} as Awaited<ReturnType<typeof truncateAfterMessage>>);
        }),
      );
      const pending = resendEditedUserMessage(CHAT_ID, edited, 2, 'summarize only chapter 3');
      useChatStore.setState({ chatId: 'chat-other', messages: OTHER_CHAT, ...otherChat });
      finishCut();
      await pending;
    };

    it('neither cuts nor sends into that chat and keeps the edited text reachable', async () => {
      useChatStore.setState({ agentConfig: agentConfig('agent-7') });

      await editWhileLeaving({ agentConfig: agentConfig('agent-9') });

      expect(sendMessage).not.toHaveBeenCalled();
      expect(transcript()).toEqual(['o-1', 'o-1']);
      expect(addInputHistory).toHaveBeenCalledTimes(1);
      expect(addInputHistory).toHaveBeenCalledWith('summarize only chapter 3', 'agent-7');
    });

    it('tells the user that the edit was not sent', async () => {
      await editWhileLeaving();

      expect(showI18nToast).toHaveBeenCalledTimes(1);
      expect(showI18nToast).toHaveBeenCalledWith(
        'chat.messageFailed.title',
        undefined,
        expect.objectContaining({ descriptionKey: 'chat.messageFailed.generic', type: 'error' }),
      );
    });

    it('records nothing when the edited chat is incognito', async () => {
      useChatStore.setState({ incognitoMode: true });

      await editWhileLeaving({ incognitoMode: false });

      expect(addInputHistory).not.toHaveBeenCalled();
    });
  });
});
