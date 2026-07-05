import React, { useEffect, useCallback, useMemo } from 'react';
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
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '@/components/primitives/button';
import useChatStore from '@/store/useChatStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import type { QueuedGoal } from '@/store/chat/goals/useGoalStore';

const QueueIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M3 6h18" />
    <path d="M3 12h18" />
    <path d="M3 18h18" />
  </svg>
);

const XIcon = ({ className = 'w-3 h-3' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </svg>
);

const GripVerticalIcon = ({ className = 'w-3 h-3' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="9" cy="12" r="1" />
    <circle cx="9" cy="5" r="1" />
    <circle cx="9" cy="19" r="1" />
    <circle cx="15" cy="12" r="1" />
    <circle cx="15" cy="5" r="1" />
    <circle cx="15" cy="19" r="1" />
  </svg>
);

function SortableQueueItem({ goal, index, onCancel }: { goal: QueuedGoal; index: number; onCancel: (id: string) => void }) {
  const t = useTranslations('Goal');
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: goal.goal_id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-2 p-2 rounded-full border bg-card/60 hover:bg-card transition-colors group touch-none"
    >
      <div {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing shrink-0">
        <GripVerticalIcon className="w-3 h-3 text-muted-foreground/50 group-hover:text-muted-foreground" />
      </div>
      <span className="text-xs text-muted-foreground/60 font-mono w-4 shrink-0">{index + 1}</span>
      <span className="text-xs text-foreground flex-1 truncate" title={goal.objective}>
        {goal.objective}
      </span>
      <Button
        variant="ghost"
        size="sm"
        className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={() => onCancel(goal.goal_id)}
        title={t('cancelQueued')}
      >
        <XIcon className="w-3 h-3 text-muted-foreground hover:text-destructive" />
      </Button>
    </div>
  );
}

export function GoalQueueSection() {
  const t = useTranslations('Goal');
  const chatId = useChatStore((s) => s.chatId);
  const queuedGoals = useGoalStore((s) => s.queuedGoals);
  const fetchQueue = useGoalStore((s) => s.fetchQueue);
  const cancelQueuedGoal = useGoalStore((s) => s.cancelQueuedGoal);
  const reorderQueue = useGoalStore((s) => s.reorderQueue);
  const activeGoal = useGoalStore((s) => s.activeGoal);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const sortableIds = useMemo(() => queuedGoals.map((g) => g.goal_id), [queuedGoals]);

  useEffect(() => {
    if (chatId) fetchQueue(chatId);
  }, [chatId, fetchQueue, activeGoal?.status]);

  const handleCancel = useCallback(
    (goalId: string) => {
      if (chatId) cancelQueuedGoal(chatId, goalId);
    },
    [chatId, cancelQueuedGoal],
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id || !chatId) return;

      const oldIndex = queuedGoals.findIndex((g) => g.goal_id === active.id);
      const newIndex = queuedGoals.findIndex((g) => g.goal_id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;

      const reordered = arrayMove(queuedGoals, oldIndex, newIndex);
      useGoalStore.setState({ queuedGoals: reordered });
      reorderQueue(chatId, reordered.map((g) => g.goal_id));
    },
    [chatId, queuedGoals, reorderQueue],
  );

  if (queuedGoals.length === 0) return null;

  return (
    <div className="mt-4 p-3 rounded-lg border bg-muted/30 border-border/60">
      <div className="flex items-center gap-2 mb-2">
        <QueueIcon className="w-4 h-4 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">
          {t('queueTitle')} ({queuedGoals.length})
        </span>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
          <div className="space-y-1.5">
            {queuedGoals.map((goal, idx) => (
              <SortableQueueItem key={goal.goal_id} goal={goal} index={idx} onCancel={handleCancel} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
