/**
 * [INPUT]
 * - @/store/chat/useMessageQueueStore::{QueuedMessage, QueuePauseReason} (POS: 排队消息内存状态源)
 * - ./QueuedMessageItem::QueuedMessageItem (POS: 单条排队消息行)
 *
 * [OUTPUT]
 * - QueuedMessagesList: 可拖拽排序的排队消息列表，附带暂停/卡住状态条。
 *
 * [POS]
 * 消息队列可视化与拖拽排序。复用 @dnd-kit 模式与 GoalQueueSection 保持一致。
 * 编辑锁（editingId）属于队列状态而非本组件：列表卸载或切换会话时必须释放，否则队首消息会被永久锁住。
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
} from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { ArrowClockwise } from '@phosphor-icons/react';
import type { QueuedMessage, QueuePauseReason } from '@/store/chat/useMessageQueueStore';
import { QueuedMessageItem } from './QueuedMessageItem';

interface QueuedMessagesListProps {
  queue: QueuedMessage[];
  pausedReason: QueuePauseReason | null;
  editingId: string | null;
  setEditingId: (id: string | null) => void;
  editMessage: (id: string, text: string) => void;
  removeMessage: (id: string) => void;
  reorder: (oldIndex: number, newIndex: number) => void;
  resume: () => void;
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
}: QueuedMessagesListProps) {
  const t = useTranslations('chat');

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const sortableIds = useMemo(() => queue.map((message) => message.id), [queue]);

  useEffect(() => () => setEditingId(null), [setEditingId]);

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

  if (queue.length === 0) {
    return null;
  }

  return (
    <div className="mb-2 flex w-full flex-col gap-2">
      {pausedReason && <QueueStatusBanner reason={pausedReason} onResume={resume} />}
      {/* DndContext renders its screen-reader helpers as siblings, so it must wrap the <ul> rather than sit inside it. */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
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
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </div>
  );
}
