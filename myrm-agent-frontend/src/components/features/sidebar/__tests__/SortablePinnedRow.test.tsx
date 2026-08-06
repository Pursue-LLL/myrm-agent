import { DndContext } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import { SortablePinnedRow } from '../ChatHistoryRow';

const chat: ChatItem = {
  id: 'pinned-chat-1',
  title: 'Pinned Alpha',
  lastMessage: 'Last message',
  updatedAt: new Date('2026-08-01T12:00:00Z'),
  createdAt: new Date('2026-08-01T10:00:00Z'),
  isPinned: true,
  actionMode: 'agent',
  source: 'web',
};

const t = ((key: string) => key) as ReturnType<typeof import('next-intl').useTranslations>;

const baseProps = {
  pinIndex: 1,
  isMobile: false,
  isActive: false,
  renameId: null,
  renameValue: '',
  exportingId: null,
  formatTime: () => 'Aug 1',
  onRename: vi.fn(),
  onRenameSubmit: vi.fn(),
  onRenameCancel: vi.fn(),
  onRenameValueChange: vi.fn(),
  onDelete: vi.fn(),
  onExport: vi.fn(),
  onPin: vi.fn(),
  onUnpin: vi.fn(),
  sessionDragEnabled: true,
  onSessionDragStart: vi.fn(),
  t,
};

describe('SortablePinnedRow', () => {
  it('exposes pin reorder handle and enables session cite drag on the row link', () => {
    render(
      <DndContext onDragEnd={vi.fn()}>
        <SortableContext items={[chat.id]} strategy={verticalListSortingStrategy}>
          <SortablePinnedRow chat={chat} {...baseProps} />
        </SortableContext>
      </DndContext>,
    );

    expect(screen.getByRole('button', { name: 'chat.pin.reorderHandle' })).toBeInTheDocument();
    const rowLink = screen.getByRole('link', { name: /Pinned Alpha/i });
    expect(rowLink).toHaveAttribute('draggable', 'true');
  });

  it('keeps session cite drag disabled when sessionDragEnabled is false', () => {
    render(
      <DndContext onDragEnd={vi.fn()}>
        <SortableContext items={[chat.id]} strategy={verticalListSortingStrategy}>
          <SortablePinnedRow chat={chat} {...baseProps} sessionDragEnabled={false} />
        </SortableContext>
      </DndContext>,
    );

    const rowLink = screen.getByRole('link', { name: /Pinned Alpha/i });
    expect(rowLink).toHaveAttribute('draggable', 'false');
  });
});
