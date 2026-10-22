/**
 * [INPUT]
 * - @/store/chat/useMessageQueueStore::{QueuedMessage, QueuePauseReason} (POS: 排队消息内存状态源)
 * - ./QueuedMessageItem::QueuedMessageItem (POS: 单条排队消息行)
 * - @/hooks/ui/useDndAccessibility::useDndAccessibility (POS: 屏幕阅读器的本地化说明与播报)
 * - ./useQueueDockCollapsePersistence::useQueueDockCollapsePersistence (POS: 按会话持久化 Dock 折叠态)
 *
 * [OUTPUT]
 * - QueuedMessagesList: 可折叠、按会话持久化、可拖拽排序并支持 Esc 暂停自动展开的排队消息 Dock 列表。
 *
 * [POS]
 * 消息队列可视化与拖拽排序 Dock 栏。对标 Traycer PR #2441 与 Hermes Composer Queue Editing 生产级连续交互心法。
 */

import React, { useCallback, useEffect, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type UniqueIdentifier,
} from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { ArrowClockwise, CaretDown, CaretUp, ClockCountdown, Trash, PauseCircle } from '@phosphor-icons/react';
import type { QueuedMessage, QueuePauseReason } from '@/store/chat/useMessageQueueStore';
import { useDndAccessibility } from '@/hooks/ui/useDndAccessibility';
import { QueuedMessageItem } from './QueuedMessageItem';
import { useQueueDockCollapsePersistence } from './useQueueDockCollapsePersistence';

export interface QueuedMessagesListProps {
  queue: QueuedMessage[];
  pausedReason: QueuePauseReason | null;
  editingId: string | null;
  setEditingId: (id: string | null) => void;
  editMessage: (id: string, text: string) => void;
  removeMessage: (id: string) => void;
  reorder: (oldIndex: number, newIndex: number) => void;
  resume: () => void;
  chatId?: string | null;
  onClearQueue?: () => void;
  onPause?: () => void;
}

function QueueStatusBanner({ reason, onResume }: { reason: QueuePauseReason; onResume: () => void }) {
  const t = useTranslations('chat');
  const isStuck = reason === 'stuck';

  return (
    <output className="flex items-center justify-between gap-3 rounded-lg border border-accent-warm/30 bg-accent-warm/10 px-3 py-2 text-xs text-foreground">
      <span className="min-w-0">{isStuck ? t('queue.stuck') : t('queue.pausedStopped')}</span>
      <button
        type="button"
        onClick={onResume}
        className="inline-flex shrink-0 items-center gap-1 rounded-md border border-accent-warm/40 px-2 py-1 font-medium text-accent-warm transition-colors hover:bg-accent-warm/15 pointer-coarse:min-h-9 pointer-coarse:px-3"
      >
        <ArrowClockwise size={12} weight="bold" aria-hidden />
        {isStuck ? t('queue.retry') : t('queue.resume')}
      </button>
    </output>
  );
}

export function QueuedMessagesList({
  queue,
  pausedReason,
  editingId,
  setEditingId,
  editMessage,
  removeMessage,
  reorder,
  resume,
  chatId,
  onClearQueue,
  onPause,
}: QueuedMessagesListProps) {
  const t = useTranslations('chat');
  const { isCollapsed, setCollapsed, toggleCollapsed } = useQueueDockCollapsePersistence(chatId, false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const sortableIds = useMemo(() => queue.map((message) => message.id), [queue]);
  // 排队消息没有标题，播报念它在队列里的序号（与行内「排队中 (n/总数)」一致）。
  const positionLabel = useCallback(
    (id: UniqueIdentifier) => {
      const index = queue.findIndex((message) => message.id === id);
      return index === -1 ? undefined : t('queue.queued', { index: String(index + 1), total: String(queue.length) });
    },
    [queue, t],
  );
  const accessibility = useDndAccessibility(positionLabel);

  useEffect(() => () => setEditingId(null), [setEditingId]);

  // Global Escape handling: when queue is non-empty and user presses Escape (outside inline editor),
  // pause the queue (if onPause provided) and expand the dock to reveal queued tasks.
  useEffect(() => {
    if (queue.length === 0 || editingId !== null) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) {
        if (pausedReason === null && onPause) {
          onPause();
        }
        setCollapsed(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [queue.length, editingId, pausedReason, onPause, setCollapsed]);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) {
        return;
      }

      const oldIndex = queue.findIndex((message) => message.id === active.id);
      const newIndex = queue.findIndex((message) => message.id === over.id);
      if (oldIndex === -1 || newIndex === -1) {
        return;
      }

      reorder(oldIndex, newIndex);
    },
    [queue, reorder],
  );

  const handleSaveEdit = useCallback(
    (id: string, text: string) => {
      editMessage(id, text);
      setEditingId(null);
    },
    [editMessage, setEditingId],
  );

  const handleCancelEdit = useCallback(() => setEditingId(null), [setEditingId]);

  const handleMoveToTop = useCallback(
    (index: number) => {
      if (index > 0 && index < queue.length) {
        reorder(index, 0);
      }
    },
    [queue.length, reorder],
  );

  if (queue.length === 0) {
    return null;
  }

  const headMessage = queue[0];
  const nextPreviewText = headMessage
    ? headMessage.text.trim() || t('queue.attachments', { count: headMessage.files.length })
    : '';

  return (
    <div className="mb-2 flex w-full flex-col gap-1.5" data-testid="queued-messages-container">
      {/* Dock Bar Header Handle */}
      <div
        data-testid="queue-dock-header"
        className="flex items-center justify-between gap-2 rounded-lg border border-accent-warm/30 bg-accent-warm/10 px-3 py-1.5 text-xs text-foreground shadow-sm"
      >
        <button
          type="button"
          onClick={toggleCollapsed}
          data-testid="queue-dock-toggle"
          className="flex min-w-0 flex-1 items-center gap-2 text-left transition-colors hover:text-accent-warm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? 'Expand queued messages' : 'Collapse queued messages'}
        >
          {isCollapsed ? (
            <CaretDown size={14} weight="bold" className="shrink-0 text-accent-warm" />
          ) : (
            <CaretUp size={14} weight="bold" className="shrink-0 text-accent-warm" />
          )}

          <div className="flex shrink-0 items-center gap-1.5 font-semibold text-accent-warm">
            <ClockCountdown size={14} className="shrink-0 animate-pulse" aria-hidden />
            <span>Queued ({queue.length})</span>
          </div>

          {pausedReason && (
            <span
              data-testid="queue-paused-badge"
              className="inline-flex shrink-0 items-center gap-1 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400"
            >
              <PauseCircle size={11} weight="fill" />
              <span>Paused</span>
            </span>
          )}

          {isCollapsed && nextPreviewText && (
            <span
              data-testid="queue-collapsed-preview"
              className="truncate text-[11px] text-muted-foreground"
              title={nextPreviewText}
            >
              Next: &quot;{nextPreviewText}&quot;
            </span>
          )}
        </button>

        <div className="flex shrink-0 items-center gap-1.5">
          {onClearQueue && (
            <button
              type="button"
              onClick={onClearQueue}
              data-testid="queue-clear-all"
              className="p-1 text-muted-foreground transition-colors hover:text-destructive"
              title="Clear entire queue"
              aria-label="Clear entire queue"
            >
              <Trash size={13} />
            </button>
          )}

          <button
            type="button"
            onClick={toggleCollapsed}
            className="text-[11px] text-muted-foreground hover:text-foreground"
          >
            {isCollapsed ? 'Expand' : 'Collapse'}
          </button>
        </div>
      </div>

      {/* Expanded Details Body */}
      {!isCollapsed && (
        <div className="flex flex-col gap-2 animate-in fade-in zoom-in-95 duration-150">
          {pausedReason && <QueueStatusBanner reason={pausedReason} onResume={resume} />}

          {/* DndContext renders its screen-reader helpers as siblings, so it must wrap the <ul> rather than sit inside it. */}
          <DndContext
            sensors={sensors}
            accessibility={accessibility}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
              <ul aria-label={t('queue.listLabel')} className="flex flex-col gap-2">
                {queue.map((message, index) => (
                  <QueuedMessageItem
                    key={message.id}
                    message={message}
                    index={index}
                    total={queue.length}
                    isEditing={editingId === message.id}
                    onStartEdit={setEditingId}
                    onSaveEdit={handleSaveEdit}
                    onCancelEdit={handleCancelEdit}
                    onRemove={removeMessage}
                    onMoveToTop={handleMoveToTop}
                  />
                ))}
              </ul>
            </SortableContext>
          </DndContext>
        </div>
      )}
    </div>
  );
}
