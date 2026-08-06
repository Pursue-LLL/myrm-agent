import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PRIOR_CHAT_DRAG_MIME, encodePriorChatDragPayload } from '@/lib/chat/priorChatDrag';
import useChatStore from '@/store/useChatStore';

const { toastInfo } = vi.hoisted(() => ({
  toastInfo: vi.fn(),
}));

const mockSonnerToast = vi.hoisted(() => {
  const fn = vi.fn();
  return Object.assign(fn, {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: (...args: unknown[]) => toastInfo(...args),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  });
});

vi.mock('sonner', () => ({
  toast: mockSonnerToast,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

import { usePriorChatComposerDrop } from '../usePriorChatComposerDrop';

describe('usePriorChatComposerDrop', () => {
  beforeEach(() => {
    toastInfo.mockReset();
    useChatStore.setState({
      chatId: 'composer-1',
      mentionReferences: [],
    });
  });

  it('adds prior_chat mention on drop', () => {
    const { result } = renderHook(() => usePriorChatComposerDrop());
    const payload = encodePriorChatDragPayload({ chatId: 'chat-2', title: 'Beta plan' });
    const dataTransfer = {
      types: [PRIOR_CHAT_DRAG_MIME],
      dropEffect: 'copy',
      getData: (type: string) => (type === PRIOR_CHAT_DRAG_MIME ? payload : ''),
    };

    act(() => {
      result.current.dragHandlers.onDrop({
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
        dataTransfer,
      } as unknown as React.DragEvent);
    });

    const mentions = useChatStore.getState().mentionReferences;
    expect(mentions).toHaveLength(1);
    expect(mentions[0]?.type).toBe('prior_chat');
    expect(mentions[0]?.path).toBe('chat-2');
  });

  it('blocks citing the active composer chat', () => {
    useChatStore.setState({ chatId: 'chat-2' });
    const { result } = renderHook(() => usePriorChatComposerDrop());
    const payload = encodePriorChatDragPayload({ chatId: 'chat-2', title: 'Same' });

    act(() => {
      result.current.dragHandlers.onDrop({
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
        dataTransfer: {
          types: [PRIOR_CHAT_DRAG_MIME],
          getData: () => payload,
        },
      } as unknown as React.DragEvent);
    });

    expect(useChatStore.getState().mentionReferences).toHaveLength(0);
    expect(toastInfo).toHaveBeenCalledWith('citeSameChat');
  });
});
