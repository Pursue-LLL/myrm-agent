/**
 * Editing a sent message: the server history is cut at the edited bubble, then the edited text goes out like a
 * normal message.
 *
 * Real scenarios: the user edits a question while the connection is flaky, opens another chat or starts a turn while
 * the server is still cutting, or submits two edits in a row. An edit sent over a history that was not cut leaves the
 * old turns in the agent's context and brings them back on reload, and an edit that vanishes with its bubble loses the
 * user's words, so an edit that cannot be carried out returns to the composer with the transcript left as it was.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { addInputHistory } from '@/hooks/message-input/useInputHistory';
import { ApiError } from '@/lib/api';
import { truncateAfterMessage, type TruncateResult } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import type { ChatState, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { resendEditedUserMessage } from '../userMessageResend';
import {
  CHAT_ID,
  REPORT_PDF,
  STAGED_PNG,
  agentConfig,
  bubble,
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

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return { ...actual, truncateAfterMessage: vi.fn() };
});

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

const CUT_DONE: TruncateResult = { success: true, deleted_count: 2 };
const NOTHING_TO_CUT: TruncateResult = { success: false, deleted_count: 0 };
const UNTOUCHED_TRANSCRIPT = ['r-1', 'r-1', 'r-2'];

const edited = bubble('user', 'r-2', 'summarize the report', { files: [REPORT_PDF] });

const edit = (message: Message, newContent: string) => resendEditedUserMessage(CHAT_ID, message, newContent);

/** Holds the server's answer to the next cut, so a test can change the world before it arrives. */
function holdNextCut(): () => void {
  let finishCut: () => void = () => {};
  vi.mocked(truncateAfterMessage).mockReturnValueOnce(
    new Promise<TruncateResult>((resolve) => {
      finishCut = () => resolve(CUT_DONE);
    }),
  );
  return () => finishCut();
}

const expectNotSentNotice = () => {
  expect(showI18nToast).toHaveBeenCalledTimes(1);
  expect(showI18nToast).toHaveBeenCalledWith(
    'chat.messageFailed.title',
    undefined,
    expect.objectContaining({ descriptionKey: 'chat.messageFailed.generic', type: 'error' }),
  );
};

const expectProcessingNotice = () => {
  expect(showI18nToast).toHaveBeenCalledWith(
    'chat.sendBlocked.title',
    undefined,
    expect.objectContaining({ descriptionKey: 'chat.sendBlocked.processingDescription', type: 'warning' }),
  );
};

beforeEach(() => {
  resetResendWorld();
  vi.mocked(truncateAfterMessage).mockReset();
  vi.mocked(truncateAfterMessage).mockResolvedValue(CUT_DONE);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('resendEditedUserMessage', () => {
  it('cuts the history at the edited bubble, then sends the edited text like a normal message', async () => {
    await edit(edited, 'summarize only chapter 3');

    expect(truncateAfterMessage).toHaveBeenCalledWith(CHAT_ID, 'r-2');
    expect(vi.mocked(truncateAfterMessage).mock.invocationCallOrder[0]).toBeLessThan(
      sendMessage.mock.invocationCallOrder[0],
    );
    expect(transcript()).toEqual(['r-1', 'r-1']);
    // Like any normal send, the request takes the composer's own attachments, not those of the replaced bubble.
    expect(sentRequest()).toEqual({ content: 'summarize only chapter 3', attachments: undefined });
  });

  it('keeps the explicit skill activation of the original message', async () => {
    const skillMessage = bubble('user', 'r-2', '[use writer_skill] [instruction: formal tone] draft the memo');

    await edit(skillMessage, 'draft the memo for finance');

    expect(sentRequest().content).toBe('[use writer_skill] [instruction: formal tone] draft the memo for finance');
  });

  it('hands the edited text, not the original, and the composer attachments it took back when the agent did not take it', async () => {
    useChatStore.setState({ files: [STAGED_PNG] });
    sendMessage.mockImplementation(async () => {
      // A request that settles without a turn clears the composer attachments it took.
      useChatStore.setState({ files: [] });
      return false;
    });

    await edit(edited, 'summarize only chapter 3');

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
    const skillMessage = bubble('user', 'r-2', '[use writer_skill] [instruction: formal tone] draft the memo');

    await edit(skillMessage, 'draft the memo for finance');

    expect(composer().inputMessage).toBe('another idea');
    expect(addInputHistory).toHaveBeenCalledTimes(1);
    expect(addInputHistory).toHaveBeenCalledWith('draft the memo for finance', undefined);
  });

  describe('when the server cannot cut the history', () => {
    it.each([
      ['the connection drops', new TypeError('Failed to fetch')],
      ['the server fails internally', new ApiError('Internal server error', 500, [], undefined, '50001')],
    ])('keeps the transcript and returns the edit to the composer when %s', async (_cause, failure) => {
      vi.mocked(truncateAfterMessage).mockRejectedValue(failure);

      await edit(edited, 'summarize only chapter 3');

      expect(sendMessage).not.toHaveBeenCalled();
      expect(transcript()).toEqual(UNTOUCHED_TRANSCRIPT);
      expect(composer()).toEqual({
        inputMessage: 'summarize only chapter 3',
        files: [],
        pendingExplicitSkillActivation: null,
      });
      expectNotSentNotice();
    });

    it('keeps the edit reachable through the input history when the composer is in use', async () => {
      useChatStore.setState({ inputMessage: 'another idea' });
      vi.mocked(truncateAfterMessage).mockRejectedValue(new TypeError('Failed to fetch'));

      await edit(edited, 'summarize only chapter 3');

      expect(composer().inputMessage).toBe('another idea');
      expect(addInputHistory).toHaveBeenCalledTimes(1);
      expect(addInputHistory).toHaveBeenCalledWith('summarize only chapter 3', undefined);
    });

    it('goes on when the server does not store the chat yet, as there is nothing to cut', async () => {
      vi.mocked(truncateAfterMessage).mockRejectedValue(
        new ApiError('Chat session not found', 404, [], undefined, '40401'),
      );

      await edit(edited, 'summarize only chapter 3');

      expect(sentRequest().content).toBe('summarize only chapter 3');
      expect(transcript()).toEqual(['r-1', 'r-1']);
      expect(showI18nToast).not.toHaveBeenCalled();
    });

    it('goes on when the server holds no such message, as there is nothing to cut', async () => {
      vi.mocked(truncateAfterMessage).mockResolvedValue(NOTHING_TO_CUT);

      await edit(edited, 'summarize only chapter 3');

      expect(sentRequest().content).toBe('summarize only chapter 3');
      expect(transcript()).toEqual(['r-1', 'r-1']);
      expect(showI18nToast).not.toHaveBeenCalled();
    });
  });

  describe('while the server cuts the history', () => {
    it('finds the edited bubble by its id when older messages were loaded above it', async () => {
      const finishCut = holdNextCut();
      const pending = edit(edited, 'summarize only chapter 3');
      const older = [bubble('user', 'o-1', 'older question'), bubble('assistant', 'o-1', 'older answer')];
      useChatStore.setState((state) => ({ messages: [...older, ...state.messages] }));
      finishCut();
      await pending;

      expect(transcript()).toEqual(['o-1', 'o-1', 'r-1', 'r-1']);
      expect(sentRequest().content).toBe('summarize only chapter 3');
    });

    it('abandons the edit when a turn started meanwhile and leaves that turn alone', async () => {
      const finishCut = holdNextCut();
      const pending = edit(edited, 'summarize only chapter 3');
      useChatStore.setState({ loading: true });
      finishCut();
      await pending;

      expect(sendMessage).not.toHaveBeenCalled();
      expect(transcript()).toEqual(UNTOUCHED_TRANSCRIPT);
      expect(composer().inputMessage).toBe('summarize only chapter 3');
      expectNotSentNotice();
    });

    it('abandons the edit when the edited bubble left the transcript meanwhile', async () => {
      const finishCut = holdNextCut();
      const pending = edit(edited, 'summarize only chapter 3');
      useChatStore.setState((state) => ({ messages: state.messages.filter((m) => m.messageId !== 'r-2') }));
      finishCut();
      await pending;

      expect(sendMessage).not.toHaveBeenCalled();
      expect(transcript()).toEqual(['r-1', 'r-1']);
      expect(composer().inputMessage).toBe('summarize only chapter 3');
      expectNotSentNotice();
    });

    it('refuses a second edit and keeps its text, while the first goes through', async () => {
      const finishCut = holdNextCut();
      const first = edit(edited, 'first idea');

      await edit(bubble('user', 'r-1', 'hello'), 'second idea');

      expect(truncateAfterMessage).toHaveBeenCalledTimes(1);
      expect(composer().inputMessage).toBe('second idea');
      expectProcessingNotice();

      finishCut();
      await first;

      expect(sendMessage).toHaveBeenCalledTimes(1);
      expect(sentRequest().content).toBe('first idea');
    });

    it.each([
      ['sent', () => vi.mocked(truncateAfterMessage).mockResolvedValueOnce(CUT_DONE)],
      ['abandoned', () => vi.mocked(truncateAfterMessage).mockRejectedValueOnce(new TypeError('Failed to fetch'))],
    ])('takes the next edit once the previous one was %s', async (_outcome, arrangeFirstCut) => {
      arrangeFirstCut();
      await edit(edited, 'first idea');

      await edit(bubble('user', 'r-1', 'hello'), 'second idea');

      expect(sendMessage.mock.lastCall?.[0]).toBe('second idea');
    });

    describe('and the user opens another chat', () => {
      const OTHER_CHAT = [bubble('user', 'o-1', 'other question'), bubble('assistant', 'o-1', 'other answer')];

      /** Starts the edit, lets the user open another chat while the cut is in flight, then finishes the cut. */
      const editWhileLeaving = async (otherChat: Partial<ChatState> = {}) => {
        const finishCut = holdNextCut();
        const pending = edit(edited, 'summarize only chapter 3');
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

      it('leaves the transcript of that chat alone even when it holds a bubble with the same id', async () => {
        await editWhileLeaving({
          messages: [bubble('user', 'r-2', 'a look-alike'), bubble('assistant', 'r-2', 'its answer')],
        });

        expect(sendMessage).not.toHaveBeenCalled();
        expect(transcript()).toEqual(['r-2', 'r-2']);
      });

      it('tells the user that the edit was not sent', async () => {
        await editWhileLeaving();

        expectNotSentNotice();
      });

      it('records nothing when the edited chat is incognito', async () => {
        useChatStore.setState({ incognitoMode: true });

        await editWhileLeaving({ incognitoMode: false });

        expect(addInputHistory).not.toHaveBeenCalled();
      });
    });
  });

  it('refuses an edit while a turn is running and keeps its text', async () => {
    useChatStore.setState({ loading: true });

    await edit(edited, 'summarize only chapter 3');

    expect(truncateAfterMessage).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
    expect(transcript()).toEqual(UNTOUCHED_TRANSCRIPT);
    expect(composer().inputMessage).toBe('summarize only chapter 3');
    expectProcessingNotice();
  });
});
