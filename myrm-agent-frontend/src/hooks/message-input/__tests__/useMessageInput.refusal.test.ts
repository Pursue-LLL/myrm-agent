import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildChatState,
  chatStoreRef,
  mockEnqueue,
  mockRedirectMessage,
  mockSendMessage,
  mockSetFiles,
  mockSetInputMessage,
  mockSetPendingArchiveRestoreActions,
  mockSteerMessage,
  mockToastInfo,
  resetMessageInputMocks,
} from './messageInputKit';

describe('useMessageInput attachments and refused sends', () => {
  beforeEach(resetMessageInputMocks);

  describe('queue attachments', () => {
    const attachment = { id: 'file-1', name: 'notes.zip', status: 'done' };

    it('moves the staged attachments into the queued message and empties the composer', async () => {
      chatStoreRef.state = buildChatState({ files: [attachment] });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleQueueSubmit();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [attachment], undefined, null);
      expect(mockSetFiles).toHaveBeenCalledWith([]);
    });

    it('queues a busy submit that carries attachments instead of redirecting it as text only', async () => {
      chatStoreRef.state = buildChatState({ loading: true, inputMessage: 'see attached', files: [attachment] });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('see attached', [attachment], undefined, null);
      expect(mockRedirectMessage).not.toHaveBeenCalled();
      expect(mockSteerMessage).not.toHaveBeenCalled();
    });

    it('requeues a busy-refused message with the attachments it was sent with and reports its real position', async () => {
      const busyError = new Error('busy');
      busyError.name = 'AgentBusyError';
      chatStoreRef.state = buildChatState({ files: [attachment] });
      mockSendMessage.mockImplementationOnce(async () => {
        // By the time the refusal reaches the hook the store has already emptied the composer attachments.
        chatStoreRef.state.files = [];
        throw busyError;
      });
      mockEnqueue.mockReturnValue(3);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
        await Promise.resolve();
      });

      expect(mockEnqueue).toHaveBeenCalledWith('hello world', [attachment], undefined, null);
      expect(mockToastInfo).toHaveBeenCalledWith('queue.added_with_position:{"position":3}');
    });

    it('restores the sent attachments when the archive restore action is rejected', async () => {
      const { FatalNetworkError, ARCHIVE_RESTORE_ACTION_INVALID } = await import('@/lib/utils/networkResilience');
      chatStoreRef.state = buildChatState({ files: [attachment] });
      mockSendMessage.mockImplementationOnce(async () => {
        chatStoreRef.state.files = [];
        throw new FatalNetworkError('invalid restore action', {
          status: 400,
          errorCode: ARCHIVE_RESTORE_ACTION_INVALID,
        });
      });
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      await act(async () => {
        await result.current.handleSubmit();
        await Promise.resolve();
      });

      expect(mockSetFiles).toHaveBeenCalledWith([attachment]);
      expect(mockSetInputMessage).toHaveBeenLastCalledWith('hello world');
    });
  });

  describe('a direct send the agent never took', () => {
    const attachment = { id: 'file-1', name: 'notes.zip', status: 'done' };
    const setHideAttachList = vi.fn();

    beforeEach(() => {
      setHideAttachList.mockClear();
      chatStoreRef.state = buildChatState({ files: [attachment], setHideAttachList });
    });

    async function submitDirect() {
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const rendered = renderHook(() => useMessageInput());
      await act(async () => {
        await rendered.result.current.handleSubmit();
        await Promise.resolve();
      });
      return rendered.result;
    }

    it('puts the text and the attachments back when the store refused after it emptied the composer', async () => {
      mockSendMessage.mockImplementationOnce(async () => {
        chatStoreRef.state.files = [];
        return false;
      });

      await submitDirect();

      expect(chatStoreRef.state.inputMessage).toBe('hello world');
      expect(mockSetFiles).toHaveBeenCalledWith([attachment]);
    });

    it('puts the text back and shows the attachment list again when the refusal left the attachments in place', async () => {
      mockSendMessage.mockResolvedValueOnce(false);

      await submitDirect();

      expect(chatStoreRef.state.inputMessage).toBe('hello world');
      expect(setHideAttachList.mock.calls).toEqual([[true], [false]]);
    });

    it('brings back the archive restore actions and the one-turn capability selection with the text', async () => {
      const restoreAction = { type: 'archive_restore' as const, restoreArg: 'range:1-10' };
      const { resolveArchiveRestoreActionsForMessage } = await import('@/store/chat/archiveRestoreActions');
      vi.mocked(resolveArchiveRestoreActionsForMessage).mockReturnValueOnce([restoreAction]);
      const selection = { skillIds: ['skill-b'], mcpNames: null };
      chatStoreRef.state = buildChatState({
        files: [attachment],
        setHideAttachList,
        agentConfig: {
          selectedSkillIds: ['skill-a', 'skill-b'],
          selectedMcpNames: ['mcp-a'],
          systemPrompt: '',
          useGlobalInstruction: true,
        },
      });
      mockSendMessage.mockResolvedValueOnce(false);
      const { useMessageInput } = await import('@/hooks/message-input/useMessageInput');
      const { result } = renderHook(() => useMessageInput());

      act(() => {
        result.current.setTurnCapabilitySelection(selection);
      });
      await act(async () => {
        await result.current.handleSubmit();
        await Promise.resolve();
      });

      expect(mockSetPendingArchiveRestoreActions).toHaveBeenLastCalledWith([restoreAction]);
      expect(result.current.turnCapabilitySelection).toEqual(selection);
    });

    it('keeps what the user typed while the refused send was in flight', async () => {
      mockSendMessage.mockImplementationOnce(async () => {
        chatStoreRef.state.files = [];
        chatStoreRef.state.inputMessage = 'newer thought';
        return false;
      });

      await submitDirect();

      expect(chatStoreRef.state.inputMessage).toBe('newer thought');
      expect(mockSetFiles).not.toHaveBeenCalledWith([attachment]);
    });

    it('keeps the files the user attached while the refusal was in flight', async () => {
      const later = { id: 'file-2', name: 'later.png', status: 'done' };
      mockSendMessage.mockImplementationOnce(async () => {
        chatStoreRef.state.files = [attachment, later];
        return false;
      });

      await submitDirect();

      expect(chatStoreRef.state.inputMessage).toBe('');
      expect(mockSetFiles).not.toHaveBeenCalled();
    });

    it('does not paste the refused text into a chat the user has since switched to', async () => {
      mockSendMessage.mockImplementationOnce(async () => {
        chatStoreRef.state.files = [];
        chatStoreRef.state.chatId = 'chat-other';
        return false;
      });

      await submitDirect();

      expect(chatStoreRef.state.inputMessage).toBe('');
      expect(mockSetFiles).not.toHaveBeenCalled();
    });

    it('leaves the composer empty when the turn was dispatched', async () => {
      await submitDirect();

      expect(chatStoreRef.state.inputMessage).toBe('');
      expect(mockSetFiles).not.toHaveBeenCalled();
    });

    it('does not overwrite newer input when the archive restore action is rejected', async () => {
      const { FatalNetworkError, ARCHIVE_RESTORE_ACTION_INVALID } = await import('@/lib/utils/networkResilience');
      mockSendMessage.mockImplementationOnce(async () => {
        chatStoreRef.state.files = [];
        chatStoreRef.state.inputMessage = 'newer thought';
        throw new FatalNetworkError('invalid restore action', {
          status: 400,
          errorCode: ARCHIVE_RESTORE_ACTION_INVALID,
        });
      });

      await submitDirect();

      expect(chatStoreRef.state.inputMessage).toBe('newer thought');
    });
  });
});
