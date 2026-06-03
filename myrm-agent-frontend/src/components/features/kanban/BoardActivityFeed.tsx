/**
 * [INPUT]
 * - @/services/kanban::listBoardEvents (POS: 看板 API 层)
 * - ./kanban-styles::EVENT_KIND_STYLES, formatTime (POS: 共享样式常量)
 *
 * [OUTPUT]
 * - BoardActivityFeed: Board 级活动流组件（filter pills + auto-follow + 实时追加）
 *
 * [POS]
 * Board 级事件活动流。聚合展示看板全部任务事件，支持 kind 过滤、自动跟踪新事件、点击跳转任务详情。
 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { BoardEvent } from '@/services/kanban';
import { listBoardEvents } from '@/services/kanban';
import { EVENT_KIND_STYLES, formatTime } from './kanban-styles';

const VISIBLE_KINDS = [
  'created',
  'claimed',
  'completed',
  'failed',
  'blocked',
  'unblocked',
  'retrying',
  'promoted',
  'reclaimed',
  'archived',
  'user_comment',
  'verification_failed',
  'timed_out',
  'decomposed',
  'specified',
  'branch_switched',
] as const;

interface BoardActivityFeedProps {
  boardId: string;
  onTaskClick?: (taskId: string) => void;
}

export default function BoardActivityFeed({ boardId, onTaskClick }: BoardActivityFeedProps) {
  const t = useTranslations('kanban');
  const [events, setEvents] = useState<BoardEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeKinds, setActiveKinds] = useState<Set<string>>(() => new Set(VISIBLE_KINDS));
  const [newCount, setNewCount] = useState(0);
  const [autoFollow, setAutoFollow] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const scrolledRef = useRef(false);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await listBoardEvents(boardId, { limit: 100 });
      setEvents(resp.items);
    } finally {
      setLoading(false);
    }
  }, [boardId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    const onEvent = (e: Event) => {
      const detail = (e as CustomEvent).detail as
        | { board_id?: string; task_id?: string; action?: string; title?: string }
        | undefined;
      if (!detail?.board_id || detail.board_id !== boardId) return;

      const newEntry: BoardEvent = {
        event_id: Date.now(),
        task_id: detail.task_id || '',
        task_title: detail.title || '',
        task_assignee: '',
        kind: detail.action || 'updated',
        payload: null,
        run_id: null,
        created_at: new Date().toISOString(),
      };
      setEvents((prev) => [newEntry, ...prev.slice(0, 199)]);
      if (scrolledRef.current && !autoFollow) {
        setNewCount((n) => n + 1);
      }
    };
    window.addEventListener('kanban-task-updated', onEvent);
    return () => window.removeEventListener('kanban-task-updated', onEvent);
  }, [boardId, autoFollow]);

  const filtered = useMemo(() => events.filter((ev) => activeKinds.has(ev.kind)), [events, activeKinds]);

  const toggleKind = useCallback((kind: string) => {
    setActiveKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }, []);

  const handleScroll = useCallback(() => {
    if (!listRef.current) return;
    const { scrollTop } = listRef.current;
    scrolledRef.current = scrollTop > 60;
    if (!scrolledRef.current) setNewCount(0);
  }, []);

  const scrollToTop = useCallback(() => {
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    setNewCount(0);
  }, []);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Filter pills */}
      <div className="flex flex-wrap gap-1 px-2 py-1.5 border-b border-border/50 shrink-0">
        {VISIBLE_KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => toggleKind(kind)}
            className={cn(
              'px-1.5 py-0.5 rounded text-[9px] font-medium transition-opacity',
              EVENT_KIND_STYLES[kind] ?? 'bg-muted text-muted-foreground',
              !activeKinds.has(kind) && 'opacity-30',
            )}
          >
            {t(`eventKind.${kind}` as Parameters<typeof t>[0])}
          </button>
        ))}
      </div>

      {/* New events indicator */}
      {newCount > 0 && (
        <button
          type="button"
          onClick={scrollToTop}
          className="sticky top-0 z-10 w-full px-2 py-1 text-[10px] font-medium text-center bg-primary/10 text-primary border-b border-primary/20 hover:bg-primary/20 transition-colors"
        >
          {t('newActivityCount', { count: newCount })}
        </button>
      )}

      {/* Event list */}
      <div ref={listRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-2 py-1.5 space-y-1 min-h-0">
        {loading ? (
          <div className="space-y-2 py-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-6 rounded bg-muted/30 animate-pulse" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <p className="text-[10px] text-muted-foreground py-4 text-center">{t('noEvents')}</p>
        ) : (
          filtered.map((ev) => (
            <div key={`${ev.event_id}-${ev.task_id}`} className="text-[10px] group">
              <div className="flex items-center gap-1.5">
                <span className="text-muted-foreground shrink-0 tabular-nums">{formatTime(ev.created_at)}</span>
                <span
                  className={cn(
                    'px-1 py-0.5 rounded text-[9px] font-medium shrink-0',
                    EVENT_KIND_STYLES[ev.kind] ?? 'bg-muted text-muted-foreground',
                  )}
                >
                  {t(`eventKind.${ev.kind}` as Parameters<typeof t>[0])}
                </span>
                {ev.task_title && (
                  <button
                    type="button"
                    onClick={() => onTaskClick?.(ev.task_id)}
                    className="truncate text-foreground/80 hover:text-primary hover:underline transition-colors max-w-[120px] sm:max-w-[200px]"
                    title={ev.task_title}
                  >
                    {ev.task_title}
                  </button>
                )}
                {ev.task_assignee && (
                  <span
                    className="text-muted-foreground/60 text-[9px] truncate max-w-[60px] sm:max-w-[100px]"
                    title={ev.task_assignee}
                  >
                    @{ev.task_assignee.slice(0, 12)}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer: auto-follow toggle */}
      <div className="flex items-center justify-between px-2 py-1 border-t border-border/50 shrink-0">
        <span className="text-[9px] text-muted-foreground">
          {filtered.length} {t('events')}
        </span>
        <label className="flex items-center gap-1 text-[9px] text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={autoFollow}
            onChange={(e) => setAutoFollow(e.target.checked)}
            className="w-3 h-3 rounded"
          />
          {t('autoFollow')}
        </label>
      </div>
    </div>
  );
}
