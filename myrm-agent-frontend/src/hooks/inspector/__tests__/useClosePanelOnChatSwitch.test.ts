import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useClosePanelOnChatSwitch } from '@/hooks/inspector/useClosePanelOnChatSwitch';

describe('useClosePanelOnChatSwitch', () => {
  const closePanel = vi.fn();

  beforeEach(() => {
    closePanel.mockReset();
  });

  it('does not close when chatId is unchanged', () => {
    const { rerender } = renderHook(({ chatId, isOpen }) => useClosePanelOnChatSwitch(chatId, isOpen, closePanel), {
      initialProps: { chatId: 'chat-a', isOpen: false },
    });

    rerender({ chatId: 'chat-a', isOpen: true });
    expect(closePanel).not.toHaveBeenCalled();
  });

  it('closes when chatId changes while panel is open', () => {
    const { rerender } = renderHook(({ chatId, isOpen }) => useClosePanelOnChatSwitch(chatId, isOpen, closePanel), {
      initialProps: { chatId: 'chat-a', isOpen: true },
    });

    rerender({ chatId: 'chat-b', isOpen: true });
    expect(closePanel).toHaveBeenCalledTimes(1);
  });

  it('does not close on chat switch when panel is already closed', () => {
    const { rerender } = renderHook(({ chatId, isOpen }) => useClosePanelOnChatSwitch(chatId, isOpen, closePanel), {
      initialProps: { chatId: 'chat-a', isOpen: false },
    });

    rerender({ chatId: 'chat-b', isOpen: false });
    expect(closePanel).not.toHaveBeenCalled();
  });
});
