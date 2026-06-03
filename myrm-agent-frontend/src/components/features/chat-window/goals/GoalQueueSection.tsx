import React, { useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
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

function QueueItem({
  goal,
  index,
  onCancel,
  onDragStart,
  onDragOver,
  onDrop,
}: {
  goal: QueuedGoal;
  index: number;
  onCancel: (goalId: string) => void;
  onDragStart: (e: React.DragEvent, index: number) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent, index: number) => void;
}) {
  const t = useTranslations('Goal');

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, index)}
      onDragOver={onDragOver}
      onDrop={(e) => onDrop(e, index)}
      className="flex items-center gap-2 p-2 rounded-full border bg-card/60 hover:bg-card transition-colors cursor-grab active:cursor-grabbing group"
    >
      <GripVerticalIcon className="w-3 h-3 text-muted-foreground/50 group-hover:text-muted-foreground shrink-0" />
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

  useEffect(() => {
    if (chatId) fetchQueue(chatId);
  }, [chatId, fetchQueue, activeGoal?.status]);

  const handleCancel = useCallback(
    (goalId: string) => {
      if (chatId) cancelQueuedGoal(chatId, goalId);
    },
    [chatId, cancelQueuedGoal],
  );

  const handleDragStart = useCallback((e: React.DragEvent, index: number) => {
    e.dataTransfer.setData('text/plain', String(index));
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent, dropIndex: number) => {
      e.preventDefault();
      const dragIndex = Number(e.dataTransfer.getData('text/plain'));
      if (dragIndex === dropIndex || !chatId) return;

      const reordered = [...queuedGoals];
      const [moved] = reordered.splice(dragIndex, 1);
      reordered.splice(dropIndex, 0, moved);

      useGoalStore.setState({ queuedGoals: reordered });
      reorderQueue(
        chatId,
        reordered.map((g) => g.goal_id),
      );
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
      <div className="space-y-1.5">
        {queuedGoals.map((goal, idx) => (
          <QueueItem
            key={goal.goal_id}
            goal={goal}
            index={idx}
            onCancel={handleCancel}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          />
        ))}
      </div>
    </div>
  );
}
