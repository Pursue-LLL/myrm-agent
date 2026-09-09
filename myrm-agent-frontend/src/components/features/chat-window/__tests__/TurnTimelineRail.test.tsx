// @vitest-environment jsdom
// @bun-test-dom
'use client';

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Message } from '@/store/chat/types';
import type { TurnOutlineItem } from '@/services/chat';
import { TurnTimelineRail, MobileTurnOutlineSheet } from '../TurnTimelineRail';

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => (key: string, params?: Record<string, unknown>) => {
    if (params) {
      let str = `${ns}.${key}`;
      for (const [k, v] of Object.entries(params)) {
        str += `:${k}=${v}`;
      }
      return str;
    }
    return `${ns}.${key}`;
  },
}));

describe('TurnTimelineRail', () => {
  const mockMessages: Message[] = [
    {
      messageId: 'msg-u1',
      chatId: 'c1',
      role: 'user',
      content: 'Hello, help me refactor.',
      createdAt: new Date(),
    },
    {
      messageId: 'msg-a1',
      chatId: 'c1',
      role: 'assistant',
      content: 'Sure, I will assist with refactoring.',
      createdAt: new Date(),
    },
    {
      messageId: 'msg-u2',
      chatId: 'c1',
      role: 'user',
      content: 'Step 2: optimize database.',
      createdAt: new Date(),
    },
    {
      messageId: 'msg-a2',
      chatId: 'c1',
      role: 'assistant',
      content: 'Database indexing applied.',
      createdAt: new Date(),
    },
    {
      messageId: 'msg-u3',
      chatId: 'c1',
      role: 'user',
      content: 'Step 3: add timeline rail.',
      createdAt: new Date(),
    },
  ];

  const mockOutlines: TurnOutlineItem[] = [
    {
      turn_index: 1,
      user_message_id: 'msg-u1',
      assistant_message_id: 'msg-a1',
      prompt_preview: 'Hello, help me refactor.',
      reply_preview: 'Sure, I will assist with refactoring.',
      created_at: new Date().toISOString(),
      message_count: 2,
    },
    {
      turn_index: 2,
      user_message_id: 'msg-u2',
      assistant_message_id: 'msg-a2',
      prompt_preview: 'Step 2: optimize database.',
      reply_preview: 'Database indexing applied.',
      created_at: new Date().toISOString(),
      message_count: 2,
    },
    {
      turn_index: 3,
      user_message_id: 'msg-u3',
      assistant_message_id: null,
      prompt_preview: 'Step 3: add timeline rail.',
      reply_preview: null,
      created_at: new Date().toISOString(),
      message_count: 1,
    },
    {
      turn_index: 4,
      user_message_id: 'msg-u4-unloaded',
      assistant_message_id: 'msg-a4',
      prompt_preview: 'Step 4: historical turn unloaded.',
      reply_preview: 'Executed successfully.',
      created_at: new Date().toISOString(),
      message_count: 2,
    },
  ];

  it('renders nothing when turns count is below 3', () => {
    const { container } = render(
      <TurnTimelineRail
        messages={mockMessages.slice(0, 2)}
        onJump={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders rail ticks from turnOutlines when provided', () => {
    render(
      <TurnTimelineRail
        messages={mockMessages}
        turnOutlines={mockOutlines}
        onJump={vi.fn()}
      />,
    );

    const ticks = screen.getAllByRole('button');
    expect(ticks).toHaveLength(4);
  });

  it('calls onJump when a loaded turn tick is clicked', () => {
    const onJump = vi.fn();
    render(
      <TurnTimelineRail
        messages={mockMessages}
        turnOutlines={mockOutlines}
        onJump={onJump}
      />,
    );

    const ticks = screen.getAllByRole('button');
    // First turn is loaded (msg-u1)
    fireEvent.click(ticks[0]);
    expect(onJump).toHaveBeenCalledWith(0);
  });

  it('calls onLoadThroughTurn and onJumpToMessageId when an unloaded turn tick is clicked', async () => {
    const onJump = vi.fn();
    const onJumpToMessageId = vi.fn();
    const onLoadThroughTurn = vi.fn().mockResolvedValue(undefined);

    render(
      <TurnTimelineRail
        messages={mockMessages}
        turnOutlines={mockOutlines}
        onJump={onJump}
        onJumpToMessageId={onJumpToMessageId}
        onLoadThroughTurn={onLoadThroughTurn}
      />,
    );

    const ticks = screen.getAllByRole('button');
    // 4th turn is unloaded (msg-u4-unloaded)
    fireEvent.click(ticks[3]);

    expect(onLoadThroughTurn).toHaveBeenCalledWith(4);
    await waitFor(() => {
      expect(onJumpToMessageId).toHaveBeenCalledWith('msg-u4-unloaded');
    });
  });

  it('renders mobile sheet with all turns and triggers jump', () => {
    const onJump = vi.fn();
    render(
      <MobileTurnOutlineSheet
        messages={mockMessages}
        turnOutlines={mockOutlines}
        onJump={onJump}
        trigger={<button data-testid="mobile-trigger">Open</button>}
      />,
    );

    const trigger = screen.getByTestId('mobile-trigger');
    expect(trigger).toBeInTheDocument();
    fireEvent.click(trigger);

    expect(screen.getByText('chat.turnRail.title')).toBeInTheDocument();
    expect(screen.getByText('Hello, help me refactor.')).toBeInTheDocument();
  });
});
