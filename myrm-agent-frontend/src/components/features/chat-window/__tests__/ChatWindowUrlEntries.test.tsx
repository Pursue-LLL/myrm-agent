/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindow (POS: 聊天窗口，会话加载完成后应用 URL 入口参数)
 * - ./chatWindowMocks (POS: 子组件探针与路由替身)
 *
 * [OUTPUT]
 * Vitest: restore_arg 入口应用后把光标放到输入框末尾。
 *
 * [POS]
 * 子组件为探针，窗口与聊天 store 为真实实现。
 */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation, openChatInStore } from './chatWindowMocks';
import ChatWindow from '../ChatWindow';

const CHAT = 'session-url-entries';

describe('ChatWindow restore_arg focus', () => {
  let composer: HTMLTextAreaElement;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    composer = document.createElement('textarea');
    composer.value = 'restore prompt';
    document.body.append(composer);
    navigation.searchParams = new URLSearchParams('restore_arg=.context%2Fchat%2Fresult.txt%3A1-200');
    openChatInStore(CHAT);
  });

  afterEach(() => {
    cleanup();
    composer.remove();
    vi.useRealTimers();
  });

  it('puts the caret at the end of the composer shortly after the entry is applied', () => {
    render(<ChatWindow id={CHAT} />);
    expect(document.activeElement).not.toBe(composer);

    act(() => void vi.advanceTimersByTime(99));
    expect(document.activeElement).not.toBe(composer);
    act(() => void vi.advanceTimersByTime(1));

    expect(document.activeElement).toBe(composer);
    expect([composer.selectionStart, composer.selectionEnd]).toEqual([14, 14]);
  });

  it('does not touch the focus when there is no restore_arg', () => {
    navigation.searchParams = new URLSearchParams();
    render(<ChatWindow id={CHAT} />);

    act(() => void vi.advanceTimersByTime(500));
    expect(document.activeElement).not.toBe(composer);
  });
});
