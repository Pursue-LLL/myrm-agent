/**
 * [INPUT]
 * - react (POS: UI 组件与交互状态)
 * - lucide-react (POS: 矢量图标库)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - TodoHudPanel: 共享 Todo 计划声明 HUD 监控与管理面板
 * - TodoHudPanelProps: 组件属性契约
 * - TodoItemData: 计划项数据契约
 * - TodoStatus: 计划状态枚举联合
 *
 * [POS]
 * 对话窗口共享 Todo 计划与 HUD 投射面板（SharedTodoStoreAndHudReader）。
 * 明确区分计划声明与执行凭证，支持计划状态流转、双向字符清洗与只读 HUD 紧凑视图。
 */
import React, { useState } from 'react';
import {
  ListTodo,
  CheckCircle2,
  Clock,
  PlayCircle,
  XCircle,
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type TodoStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';

export interface TodoItemData {
  itemId: string;
  title: string;
  description?: string;
  status: TodoStatus;
  assignee?: string;
  createdAt?: number;
  updatedAt?: number;
}

export interface TodoHudPanelProps {
  sessionId?: string;
  items: TodoItemData[];
  semanticContract?: string;
  isLoading?: boolean;
  onRefresh?: () => Promise<void> | void;
  onCreateItem?: (title: string, description?: string, assignee?: string) => Promise<void> | void;
  onUpdateStatus?: (itemId: string, nextStatus: TodoStatus) => Promise<void> | void;
  onRemoveItem?: (itemId: string) => Promise<void> | void;
  onClearAll?: () => Promise<void> | void;
  className?: string;
}

const DEFAULT_SEMANTIC_CONTRACT = 'Todo items are plan declarations, not execution evidence.';

function getStatusIcon(status: TodoStatus): React.ReactElement {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />;
    case 'in_progress':
      return <PlayCircle className="w-4 h-4 text-sky-500 shrink-0 animate-pulse" />;
    case 'cancelled':
      return <XCircle className="w-4 h-4 text-muted-foreground shrink-0" />;
    case 'pending':
    default:
      return <Clock className="w-4 h-4 text-amber-500 shrink-0" />;
  }
}

export const TodoHudPanel: React.FC<TodoHudPanelProps> = ({
  sessionId = 'default',
  items,
  semanticContract = DEFAULT_SEMANTIC_CONTRACT,
  isLoading = false,
  onRefresh,
  onCreateItem,
  onUpdateStatus,
  onRemoveItem,
  onClearAll,
  className,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newAssignee, setNewAssignee] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const totalCount = items.length;
  const completedCount = items.filter((i) => i.status === 'completed').length;
  const inProgressCount = items.filter((i) => i.status === 'in_progress').length;
  const pendingCount = items.filter((i) => i.status === 'pending').length;
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const handleCreate = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    const cleanTitle = newTitle.trim();
    if (!cleanTitle || !onCreateItem) {
      return;
    }

    setIsSubmitting(true);
    try {
      await onCreateItem(cleanTitle, '', newAssignee.trim());
      setNewTitle('');
      setNewAssignee('');
    } finally {
      setIsSubmitting(false);
    }
  };

  const cycleStatus = (item: TodoItemData): void => {
    if (!onUpdateStatus) {
      return;
    }
    const flow: Record<TodoStatus, TodoStatus> = {
      pending: 'in_progress',
      in_progress: 'completed',
      completed: 'pending',
      cancelled: 'pending',
    };
    const next = flow[item.status] || 'pending';
    void onUpdateStatus(item.itemId, next);
  };

  return (
    <div
      data-testid="todo-hud-panel"
      className={cn(
        'rounded-xl border border-border bg-card p-4 shadow-sm space-y-3 transition-all',
        className
      )}
    >
      {/* HUD Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <ListTodo className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">计划声明 HUD (Plan HUD)</h3>
              <span className="text-xs text-muted-foreground font-mono">[{sessionId}]</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span>完成度 {progressPct}%</span>
              <span>•</span>
              <span className="text-emerald-600 dark:text-emerald-400">已完 {completedCount}</span>
              <span>•</span>
              <span className="text-sky-600 dark:text-sky-400">进行中 {inProgressCount}</span>
              <span>•</span>
              <span className="text-amber-600 dark:text-amber-400">待办 {pendingCount}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {onRefresh && (
            <button
              type="button"
              data-testid="refresh-todo-btn"
              disabled={isLoading}
              onClick={() => void onRefresh()}
              className="p-1.5 text-muted-foreground hover:text-foreground transition-colors rounded-lg hover:bg-muted"
              title="刷新计划"
            >
              <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
            </button>
          )}
          {onClearAll && totalCount > 0 && (
            <button
              type="button"
              data-testid="clear-all-todo-btn"
              onClick={() => void onClearAll()}
              className="px-2 py-1 text-xs text-muted-foreground hover:text-destructive transition-colors rounded hover:bg-destructive/10"
              title="清空所有计划项"
            >
              清空
            </button>
          )}
          <button
            type="button"
            data-testid="toggle-expand-btn"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="p-1.5 text-muted-foreground hover:text-foreground transition-colors rounded-lg hover:bg-muted"
            title={isExpanded ? '折叠列表' : '展开列表'}
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-muted/60 h-1.5 rounded-full overflow-hidden">
        <div
          data-testid="progress-bar-fill"
          className="bg-primary h-full transition-all duration-300"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Semantic Contract Disclaimer */}
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-muted/40 border border-border/50 text-[11px] text-muted-foreground">
        <ShieldAlert className="w-3.5 h-3.5 text-primary/70 shrink-0" />
        <span className="line-clamp-1">{semanticContract}</span>
      </div>

      {/* Expandable List Area */}
      {isExpanded && (
        <div className="space-y-3 pt-1">
          {totalCount === 0 ? (
            <div
              data-testid="empty-todo-state"
              className="text-center py-6 px-4 rounded-lg border border-dashed border-border"
            >
              <ListTodo className="w-7 h-7 text-muted-foreground/60 mx-auto mb-1.5" />
              <p className="text-xs font-medium text-foreground">暂无活跃计划声明</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                添加计划条目可与协同 Agent 共享目标预期
              </p>
            </div>
          ) : (
            <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1" data-testid="todo-items-list">
              {items.map((item, index) => (
                <div
                  key={item.itemId}
                  data-testid={`todo-item-${item.itemId}`}
                  className="flex items-center justify-between gap-2 p-2 rounded-lg bg-background/60 border border-border/60 hover:border-primary/40 transition-colors text-xs"
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <button
                      type="button"
                      data-testid={`cycle-status-btn-${item.itemId}`}
                      onClick={() => cycleStatus(item)}
                      title="点击切换状态"
                      className="p-0.5 hover:scale-110 transition-transform"
                    >
                      {getStatusIcon(item.status)}
                    </button>
                    <span className="text-muted-foreground font-mono text-[11px]">
                      {index + 1}.
                    </span>
                    <span
                      className={cn(
                        'truncate font-medium text-foreground',
                        item.status === 'completed' && 'line-through text-muted-foreground',
                        item.status === 'cancelled' && 'line-through text-muted-foreground/60'
                      )}
                    >
                      {item.title}
                    </span>
                    {item.assignee && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 shrink-0">
                        @{item.assignee}
                      </span>
                    )}
                  </div>

                  {onRemoveItem && (
                    <button
                      type="button"
                      data-testid={`remove-todo-${item.itemId}`}
                      onClick={() => void onRemoveItem(item.itemId)}
                      className="p-1 text-muted-foreground hover:text-destructive transition-colors rounded"
                      title="删除条目"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Quick Add Form */}
          {onCreateItem && (
            <form onSubmit={(e) => void handleCreate(e)} className="flex items-center gap-2 pt-1">
              <input
                type="text"
                data-testid="new-todo-title-input"
                placeholder="添加新计划项 (最大 80 字符)..."
                maxLength={80}
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="flex-1 px-2.5 py-1.5 text-xs rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <input
                type="text"
                data-testid="new-todo-assignee-input"
                placeholder="指派 (如 coder)..."
                maxLength={40}
                value={newAssignee}
                onChange={(e) => setNewAssignee(e.target.value)}
                className="w-24 px-2 py-1.5 text-xs font-mono rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                type="submit"
                data-testid="add-todo-btn"
                disabled={isSubmitting || !newTitle.trim()}
                className="px-3 py-1.5 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-1 shrink-0"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>添加</span>
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
};
