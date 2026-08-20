/**
 * [INPUT]
 * - @/hooks/message-input/useMessageQueue::QueuedMessage (POS: 消息排队状态机)
 *
 * [OUTPUT]
 * - QueuedMessagesList: 可拖拽排序的排队消息列表组件。
 *
 * [POS]
 * 消息队列可视化与拖拽排序。复用 @dnd-kit 模式与 GoalQueueSection 保持一致。
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
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
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Clock, Pencil, X, Check, GripVertical } from 'lucide-react';
import type { QueuedMessage } from '@/hooks/message-input/useMessageQueue';

interface QueuedMessagesListProps {
  queue: QueuedMessage[];
  editMessage: (id: string, text: string) => void;
  removeMessage: (id: string) => void;
  reorder: (oldIndex: number, newIndex: number) => void;
}

function SortableQueueItem({
  msg,
  index,
  total,
  isEditing,
  editText,
  onEditTextChange,
  onStartEdit,
  onConfirmEdit,
  onCancelEdit,
  onRemove,
}: {
  msg: QueuedMessage;
  index: number;
  total: number;
  isEditing: boolean;
  editText: string;
  onEditTextChange: (text: string) => void;
  onStartEdit: () => void;
  onConfirmEdit: () => void;
  onCancelEdit: () => void;
  onRemove: () => void;
}) {
  const t = useTranslations('chat');
  const editInputRef = useRef<HTMLInputElement>(null);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: msg.id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  };

  const handleStartEdit = useCallback(() => {
    onStartEdit();
    requestAnimationFrame(() => editInputRef.current?.focus());
  }, [onStartEdit]);

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="group/queue flex items-center justify-between bg-primary/8 border border-accent-warm/25 rounded-lg px-3 py-2 text-sm shadow-brand touch-none"
    >
      {isEditing ? (
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Clock size={14} className="text-accent-warm flex-shrink-0" />
          <input
            ref={editInputRef}
            type="text"
            value={editText}
            onChange={(e) => onEditTextChange(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') {
                e.preventDefault();
                onConfirmEdit();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                onCancelEdit();
              }
            }}
            className="flex-1 min-w-0 bg-transparent text-sm text-foreground outline-none border-b border-accent-warm/50 focus:border-accent-warm"
          />
          <button
            type="button"
            onClick={onConfirmEdit}
            className="text-accent-warm hover:text-accent-warm/80 transition-colors p-1"
            title={t('queue.saveEdit')}
          >
            <Check size={14} />
          </button>
          <button
            type="button"
            onClick={onCancelEdit}
            className="text-muted-foreground hover:text-foreground transition-colors p-1"
            title={t('queue.cancelEdit')}
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 overflow-hidden flex-1 min-w-0">
            <div
              {...attributes}
              {...listeners}
              className="cursor-grab active:cursor-grabbing shrink-0 text-muted-foreground/50 group-hover/queue:text-muted-foreground transition-colors"
            >
              <GripVertical size={14} />
            </div>
            <Clock size={14} className="text-accent-warm flex-shrink-0 animate-pulse" />
            <span className="text-accent-warm font-medium flex-shrink-0">
              {t('queue.queued', { index: String(index + 1), total: String(total) })}
            </span>
            <span className="text-muted-foreground truncate">{msg.text}</span>
          </div>
          <div className="flex items-center gap-0.5 sm:opacity-0 sm:group-hover/queue:opacity-100 transition-opacity">
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                handleStartEdit();
              }}
              className="text-muted-foreground hover:text-foreground transition-colors p-1"
              title={t('queue.edit')}
            >
              <Pencil size={14} />
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                onRemove();
              }}
              className="text-muted-foreground hover:text-destructive transition-colors p-1"
              title={t('queue.cancel')}
            >
              <X size={14} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function QueuedMessagesList({ queue, editMessage, removeMessage, reorder }: QueuedMessagesListProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const sortableIds = useMemo(() => queue.map((m) => m.id), [queue]);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) {
        return;
      }

      const oldIndex = queue.findIndex((m) => m.id === active.id);
      const newIndex = queue.findIndex((m) => m.id === over.id);
      if (oldIndex === -1 || newIndex === -1) {
        return;
      }

      reorder(oldIndex, newIndex);
    },
    [queue, reorder],
  );

  const confirmEdit = useCallback(() => {
    if (editingId && editingText.trim()) {
      editMessage(editingId, editingText.trim());
    }
    setEditingId(null);
    setEditingText('');
  }, [editingId, editingText, editMessage]);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditingText('');
  }, []);

  if (queue.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2 mb-2 w-full">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
          {queue.map((msg, index) => (
            <SortableQueueItem
              key={msg.id}
              msg={msg}
              index={index}
              total={queue.length}
              isEditing={editingId === msg.id}
              editText={editingText}
              onEditTextChange={setEditingText}
              onStartEdit={() => {
                setEditingId(msg.id);
                setEditingText(msg.text);
              }}
              onConfirmEdit={confirmEdit}
              onCancelEdit={cancelEdit}
              onRemove={() => removeMessage(msg.id)}
            />
          ))}
        </SortableContext>
      </DndContext>
    </div>
  );
}
