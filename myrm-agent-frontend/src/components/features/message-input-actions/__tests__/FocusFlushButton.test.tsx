/** @vitest-environment jsdom */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import FocusFlushButton from '../FocusFlushButton';

// 命名空间回显：断言既覆盖键名，也覆盖所用命名空间。按命名空间缓存以保持引用稳定。
const translators = new Map<string, ((key: string) => string) & { rich: (key: string) => string }>();
const translatorFor = (namespace: string) => {
  let t = translators.get(namespace);
  if (!t) {
    t = Object.assign((key: string) => `${namespace}.${key}`, { rich: (key: string) => `${namespace}.${key}` });
    translators.set(namespace, t);
  }
  return t;
};

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => translatorFor(namespace),
}));

const toastMock = vi.hoisted(() => ({ loading: vi.fn(() => 'toast-1'), success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMock }));

const focusFlushChat = vi.hoisted(() => vi.fn());
vi.mock('@/services/chat', () => ({ focusFlushChat }));

const storeState = vi.hoisted(() => ({
  chatId: 'chat-1' as string | null,
  resetSessionState: vi.fn(),
  loadMessages: vi.fn().mockResolvedValue(undefined),
  stopMessage: vi.fn(),
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof storeState) => unknown) => selector(storeState),
}));

describe('FocusFlushButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.chatId = 'chat-1';
  });

  it('renders nothing without an active chat', () => {
    storeState.chatId = null;

    const { container } = render(<FocusFlushButton />);

    expect(container).toBeEmptyDOMElement();
  });

  it('labels the trigger and confirmation dialog through the chat.focusFlush namespace', () => {
    render(<FocusFlushButton />);

    const trigger = screen.getByRole('button', { name: 'chat.focusFlush.ariaLabel' });
    expect(trigger).toHaveAttribute('title', 'chat.focusFlush.tooltip');

    fireEvent.click(trigger);

    expect(screen.getByText('chat.focusFlush.dialogTitle')).toBeInTheDocument();
    expect(screen.getByText('chat.focusFlush.dialogQuestion')).toBeInTheDocument();
    expect(screen.getByText('chat.focusFlush.dialogDetail')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.focusFlush.confirm' })).toBeInTheDocument();
  });

  it('flushes the chat, reloads messages and reuses the shared toast copy on success', async () => {
    focusFlushChat.mockResolvedValue({ cleared: true });
    render(<FocusFlushButton />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.focusFlush.ariaLabel' }));
    fireEvent.click(screen.getByRole('button', { name: 'chat.focusFlush.confirm' }));

    await waitFor(() => expect(toastMock.success).toHaveBeenCalled());
    expect(toastMock.loading).toHaveBeenCalledWith('commands.builtin.focusFlushing');
    expect(toastMock.success).toHaveBeenCalledWith('commands.builtin.focusSuccess', { id: 'toast-1' });
    expect(storeState.stopMessage).toHaveBeenCalledTimes(1);
    expect(focusFlushChat).toHaveBeenCalledWith('chat-1');
    expect(storeState.resetSessionState).toHaveBeenCalledTimes(1);
    expect(storeState.loadMessages).toHaveBeenCalledWith('chat-1');
  });

  it('reports a translated error when the flush request fails', async () => {
    focusFlushChat.mockRejectedValue(new Error('boom'));
    render(<FocusFlushButton />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.focusFlush.ariaLabel' }));
    fireEvent.click(screen.getByRole('button', { name: 'chat.focusFlush.confirm' }));

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith('commands.builtin.focusFailed', { id: 'toast-1' }),
    );
    expect(storeState.resetSessionState).not.toHaveBeenCalled();
  });
});
