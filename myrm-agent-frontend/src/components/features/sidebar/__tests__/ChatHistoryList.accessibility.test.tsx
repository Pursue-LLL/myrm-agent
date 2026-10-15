import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { expectDefined } from '@/test-utils/expectDefined';
import ChatHistoryList from '../ChatHistoryList';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

const pinnedChat = (id: string, title: string, pinOrder: number): ChatItem => ({
  id,
  title,
  firstMessage: title,
  lastMessage: title,
  updatedAt: new Date('2026-08-01T12:00:00Z'),
  createdAt: new Date('2026-08-01T10:00:00Z'),
  isPinned: true,
  pinOrder,
  actionMode: 'agent',
  source: 'web',
});

/** 列表靠它触发「加载更多」，jsdom 没有。 */
class InertIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('ChatHistoryList pinned chat reordering', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', InertIntersectionObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('announces the chat title instead of the chat id', async () => {
    const user = userEvent.setup();
    // 列表挂载时会先清空再重新加载，所以把「加载」换成直接给出这两条置顶会话。
    const pinned = [pinnedChat('chat-4e8a', '季度复盘', 0), pinnedChat('chat-b27d', '周报草稿', 1)];
    useChatStore.setState({
      loadChatHistory: vi.fn(async () => {
        useChatStore.setState({ chatHistoryItems: pinned, chatHistoryLoading: false });
      }),
    });
    render(<ChatHistoryList isExpanded />);

    const [handle] = await screen.findAllByRole('button', { name: '拖动以调整置顶会话顺序' });
    expectDefined(handle, 'first pinned drag handle');
    expect(handle).toHaveAttribute('aria-roledescription', '可拖动项');

    await act(async () => handle.focus());
    await user.keyboard(' ');

    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toHaveTextContent('已拾起“季度复盘”。');
    expect(liveRegion).not.toHaveTextContent('chat-4e8a');
  });
});
