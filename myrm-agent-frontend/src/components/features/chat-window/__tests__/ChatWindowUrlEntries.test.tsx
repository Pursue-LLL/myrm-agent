/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindow (POS: 聊天窗口，会话加载完成后应用 URL 入口参数)
 * - ./chatWindowMocks (POS: 子组件探针与路由替身)
 *
 * [OUTPUT]
 * Vitest: restore_arg 入口应用后把光标放到输入框末尾（地址随后被清掉也照常聚焦；换会话或卸载则取消）；
 * 地址清掉参数后，同一个入口再次使用会重新应用。
 *
 * [POS]
 * 子组件为探针，窗口与聊天 store 为真实实现。
 */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation, openChatInStore } from './chatWindowMocks';
import useChatStore from '@/store/useChatStore';
import ChatWindow from '../ChatWindow';

const CHAT = 'session-url-entries';
const RESTORE_ARG = '.context/chat/result.txt:1-200';
const withRestoreArg = () => new URLSearchParams({ restore_arg: RESTORE_ARG });

describe('ChatWindow restore_arg entry', () => {
  let composer: HTMLTextAreaElement;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    composer = document.createElement('textarea');
    composer.value = 'restore prompt';
    document.body.append(composer);
    navigation.searchParams = withRestoreArg();
    openChatInStore(CHAT);
    useChatStore.setState({ inputMessage: '', pendingArchiveRestoreActions: [] });
  });

  afterEach(() => {
    cleanup();
    composer.remove();
    vi.useRealTimers();
  });

  describe('focus', () => {
    it('puts the caret at the end of the composer shortly after the entry is applied', () => {
      render(<ChatWindow id={CHAT} />);
      expect(document.activeElement).not.toBe(composer);

      act(() => void vi.advanceTimersByTime(99));
      expect(document.activeElement).not.toBe(composer);
      act(() => void vi.advanceTimersByTime(1));

      expect(document.activeElement).toBe(composer);
      expect([composer.selectionStart, composer.selectionEnd]).toEqual([14, 14]);
    });

    it('still focuses when the address loses the parameter before the delay is over', () => {
      const view = render(<ChatWindow id={CHAT} />);

      // Applying the entry rewrites the address, which lands well inside the focus delay.
      navigation.searchParams = new URLSearchParams();
      view.rerender(<ChatWindow id={CHAT} />);
      act(() => void vi.advanceTimersByTime(100));

      expect(document.activeElement).toBe(composer);
      expect([composer.selectionStart, composer.selectionEnd]).toEqual([14, 14]);
    });

    it('does not touch the focus when there is no restore_arg', () => {
      navigation.searchParams = new URLSearchParams();
      render(<ChatWindow id={CHAT} />);

      act(() => void vi.advanceTimersByTime(500));
      expect(document.activeElement).not.toBe(composer);
    });

    it('drops the pending focus when the window moves to another chat', () => {
      const view = render(<ChatWindow id={CHAT} />);

      navigation.searchParams = new URLSearchParams();
      act(() => openChatInStore('session-elsewhere'));
      view.rerender(<ChatWindow id="session-elsewhere" />);
      act(() => void vi.advanceTimersByTime(500));

      expect(document.activeElement).not.toBe(composer);
    });

    it('drops the pending focus when the window is closed', () => {
      const view = render(<ChatWindow id={CHAT} />);

      view.unmount();
      act(() => void vi.advanceTimersByTime(500));

      expect(document.activeElement).not.toBe(composer);
    });

    it('drops every pending focus when the window is closed after the entry was applied twice', () => {
      const view = render(<ChatWindow id={CHAT} />);

      navigation.searchParams = new URLSearchParams();
      view.rerender(<ChatWindow id={CHAT} />);
      act(() => useChatStore.setState({ inputMessage: '', pendingArchiveRestoreActions: [] }));
      navigation.searchParams = withRestoreArg();
      view.rerender(<ChatWindow id={CHAT} />);
      view.unmount();
      act(() => void vi.advanceTimersByTime(500));

      expect(document.activeElement).not.toBe(composer);
    });
  });

  describe('applying', () => {
    it('prefills the restore prompt and queues the restore action once', () => {
      const view = render(<ChatWindow id={CHAT} />);
      expect(useChatStore.getState().inputMessage).toBe('contextHealth.pruning.restorePrompt');
      expect(useChatStore.getState().pendingArchiveRestoreActions).toHaveLength(1);
      expect(navigation.replace).toHaveBeenCalledExactlyOnceWith(`/${CHAT}`, { scroll: false });

      view.rerender(<ChatWindow id={CHAT} />);
      expect(navigation.replace).toHaveBeenCalledOnce();
    });

    it('waits for a conversation: the new-chat page is left alone and the entry applies once a chat exists', () => {
      const view = render(<ChatWindow />);

      expect(useChatStore.getState().inputMessage).toBe('');
      expect(useChatStore.getState().pendingArchiveRestoreActions).toEqual([]);
      expect(navigation.replace).not.toHaveBeenCalled();

      view.rerender(<ChatWindow id={CHAT} />);

      expect(useChatStore.getState().pendingArchiveRestoreActions).toHaveLength(1);
      expect(navigation.replace).toHaveBeenCalledExactlyOnceWith(`/${CHAT}`, { scroll: false });
    });

    it('applies the same restore_arg again when it is used after the address was cleaned', () => {
      const view = render(<ChatWindow id={CHAT} />);
      expect(navigation.replace).toHaveBeenCalledOnce();

      navigation.searchParams = new URLSearchParams();
      view.rerender(<ChatWindow id={CHAT} />);
      act(() => useChatStore.setState({ inputMessage: '', pendingArchiveRestoreActions: [] }));

      navigation.searchParams = withRestoreArg();
      view.rerender(<ChatWindow id={CHAT} />);

      expect(navigation.replace).toHaveBeenCalledTimes(2);
      expect(useChatStore.getState().inputMessage).toBe('contextHealth.pruning.restorePrompt');
      expect(useChatStore.getState().pendingArchiveRestoreActions).toHaveLength(1);
    });
  });
});
