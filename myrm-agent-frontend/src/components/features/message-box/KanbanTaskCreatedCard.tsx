'use client';

/**
 * [INPUT]
 * - @/lib/kanban/kanbanChatBoard::buildKanbanBoardDeepLink (POS: Chat ↔ Settings 看板深链 SSOT)
 * - @/components/primitives/button::Button (POS: 通用按钮 primitive)
 *
 * [OUTPUT]
 * - KanbanTaskCreatedCard: Chat 内 kanban_add_task 成功后的任务确认卡片
 * - KanbanTaskCreatedResult: 卡片 payload 类型
 * - data-testid: `kanban-task-created-card-{task_id}` / `kanban-task-created-open-board-{task_id}`（Chrome E2E 钩子，非用户文案）
 *
 * [POS]
 * Chat 消息流中的 Kanban 任务创建反馈 UI；由 MessageBox 在 metadata.kanban_tasks_created 存在时渲染。
 */

import { memo } from 'react';
import { useRouter } from 'next/navigation';
import { CheckCircle2, LayoutGrid } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { useTranslations } from 'next-intl';
import { buildKanbanBoardDeepLink } from '@/lib/kanban/kanbanChatBoard';

export interface KanbanTaskCreatedResult {
  task_id: string;
  title: string;
  board_id: string;
}

type KanbanTaskCreatedCardProps = {
  result: KanbanTaskCreatedResult;
  chatId: string;
};

export const KanbanTaskCreatedCard = memo<KanbanTaskCreatedCardProps>(({ result, chatId }) => {
  const t = useTranslations('kanban');
  const router = useRouter();

  const boardHref =
    result.board_id && chatId
      ? buildKanbanBoardDeepLink({ sourceChatId: chatId, boardId: result.board_id })
      : '/settings/kanban';

  return (
    <div
      className="mt-3 mb-1 w-full max-w-md overflow-hidden rounded-xl border border-border/60 bg-card text-card-foreground shadow-sm"
      data-testid={`kanban-task-created-card-${result.task_id}`}
    >
      <div className="flex items-center gap-2 border-b border-border/40 bg-muted/40 px-4 py-2.5">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary/10 text-[10px] font-bold text-primary">
          K
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{t('chatTaskCreatedTitle')}</span>
        <div className="ml-auto flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="h-3 w-3" />
          <span>{t('chatTaskCreatedSuccess')}</span>
        </div>
      </div>

      <div className="px-4 py-3">
        <p className="text-sm font-medium leading-snug break-words">{result.title}</p>
      </div>

      <div className="flex items-center justify-end border-t border-border/40 bg-muted/20 px-4 py-2.5">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1 text-xs"
          data-testid={`kanban-task-created-open-board-${result.task_id}`}
          onClick={() => router.push(boardHref)}
        >
          <LayoutGrid className="h-3 w-3" />
          {t('chatTaskCreatedOpenBoard')}
        </Button>
      </div>
    </div>
  );
});

KanbanTaskCreatedCard.displayName = 'KanbanTaskCreatedCard';
