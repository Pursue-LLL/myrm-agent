'use client';

/**
 * [INPUT]
 * - @/services/statistics::getLearningTimeline (POS: 学习时间线数据接口)
 * - @/store/useAgentStore (POS: 智能体列表，把节点的 agent_id 解析为展示名称)
 * - ./TimelineNodeCard::TimelineNodeCard (POS: 单个节点展示与行内编辑)
 * - ./useTimelineGovernance::useTimelineGovernance (POS: 行内治理动作：乐观更新、回滚、撤销)
 * - ./learningTimelineMeta (POS: 节点元数据与状态读取)
 *
 * [OUTPUT]
 * - LearningTimeline: 记忆与技能统一学习成长时间线面板，支持按类型过滤、时间跨度选择，
 *   以及带确认、乐观更新、失败回滚与撤销的行内治理（编辑/删除/归档）。
 *
 * [POS]
 * 成长与进化模块组件。在 /journey 页面提供直观的时序成长足迹展示与即时治理界面。
 */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, Brain, ChevronDown, RotateCcw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { EmptyState } from '@/components/primitives/empty-state';
import { TimelineSkeleton } from '@/components/primitives/skeleton-templates';
import { cn } from '@/lib/utils/classnameUtils';
import { showApiError } from '@/lib/api';
import { getLearningTimeline, type LearningTimelineItem } from '@/services/statistics';
import useAgentStore from '@/store/useAgentStore';
import { TimelineNodeCard } from './TimelineNodeCard';
import { useTimelineGovernance } from './useTimelineGovernance';
import { FILTER_TABS, RECOVERABLE_MEMORY_TYPES, memoryTypeOf } from './learningTimelineMeta';

const PAGE_SIZE = 20;

type PendingAction = { type: 'delete' | 'archive' | 'restore'; item: LearningTimelineItem };

interface LearningTimelineProps {
  onSelectMemoryForGraph?: (memoryId: string) => void;
  className?: string;
}

export const LearningTimeline = memo<LearningTimelineProps>(({ onSelectMemoryForGraph, className }) => {
  const t = useTranslations('growthDashboard.learningTimeline');
  const [items, setItems] = useState<LearningTimelineItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [selectedKind, setSelectedKind] = useState('all');
  const [days, setDays] = useState(30);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const { saveEdit, archiveSkill, deleteMemory } = useTimelineGovernance({ setItems, setTotalCount });
  const agents = useAgentStore((s) => s.agents);
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  const agentNames = useMemo(() => new Map(agents.map((agent) => [agent.id, agent.name])), [agents]);

  const nextCursorRef = useRef<string | null>(null);
  /** Only the newest request may write state, so a slow response never overwrites a newer filter. */
  const requestSeqRef = useRef(0);

  const loadPage = useCallback(
    async (reset: boolean) => {
      const seq = ++requestSeqRef.current;
      if (reset) {
        setLoading(true);
        setLoadError(false);
        setLoadingMore(false);
      } else {
        setLoadingMore(true);
      }
      try {
        const resp = await getLearningTimeline({
          days,
          kind_filter: selectedKind === 'all' ? undefined : selectedKind,
          limit: PAGE_SIZE,
          cursor: reset ? undefined : (nextCursorRef.current ?? undefined),
        });
        if (seq !== requestSeqRef.current) {
          return;
        }
        setItems((prev) => {
          if (reset) {
            return resp.items;
          }
          const known = new Set(prev.map((it) => it.id));
          return [...prev, ...resp.items.filter((it) => !known.has(it.id))];
        });
        setTotalCount(resp.total_count);
        setHasMore(resp.has_more);
        nextCursorRef.current = resp.next_cursor;
      } catch (err) {
        if (seq !== requestSeqRef.current) {
          return;
        }
        showApiError(err);
        if (reset) {
          setLoadError(true);
          setItems([]);
          setTotalCount(0);
          setHasMore(false);
          nextCursorRef.current = null;
        }
      } finally {
        if (seq === requestSeqRef.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [days, selectedKind],
  );

  useEffect(() => {
    void loadPage(true);
  }, [loadPage]);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  const confirmPending = () => {
    if (!pending) {
      return;
    }
    const { type, item } = pending;
    setPending(null);
    if (type === 'delete') {
      void deleteMemory(item);
    } else {
      void archiveSkill(item, type === 'archive');
    }
  };

  const requestSkillToggle = useCallback(
    (item: LearningTimelineItem) =>
      setPending({ type: item.metadata?.archived === true ? 'restore' : 'archive', item }),
    [],
  );
  const requestDelete = useCallback((item: LearningTimelineItem) => setPending({ type: 'delete', item }), []);

  const dialogCopy =
    pending?.type === 'delete'
      ? {
          title: t('deleteConfirmTitle'),
          description: RECOVERABLE_MEMORY_TYPES.has(memoryTypeOf(pending.item))
            ? t('deleteConfirm')
            : t('deleteConfirmPermanent'),
        }
      : pending?.type === 'restore'
        ? { title: t('unarchiveConfirmTitle'), description: t('unarchiveConfirm') }
        : { title: t('archiveConfirmTitle'), description: t('archiveConfirm') };

  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setSelectedKind(tab.id)}
              className={cn(
                'rounded-lg px-2.5 py-1 text-xs font-medium transition-colors',
                selectedKind === tab.id
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              {t(tab.labelKey)}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="hidden tabular-nums md:inline-block">{t('stats.totalNodes', { count: totalCount })}</span>
          <div className="flex rounded-md border border-border/60 bg-muted/40 p-0.5">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDays(d)}
                className={cn(
                  'rounded px-2 py-0.5 text-xs transition-colors',
                  days === d ? 'bg-background font-medium text-foreground shadow-xs' : 'text-muted-foreground',
                )}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && <TimelineSkeleton count={4} className="my-2" />}

      {!loading && loadError && (
        <EmptyState
          variant="error"
          icon={AlertCircle}
          title={t('error.title')}
          description={t('error.description')}
          className="my-4 min-h-[260px]"
          action={
            <Button variant="outline" size="sm" onClick={() => void loadPage(true)}>
              <RotateCcw className="mr-2 h-4 w-4" />
              {t('error.retry')}
            </Button>
          }
        />
      )}

      {!loading && !loadError && items.length === 0 && (
        <EmptyState
          variant="dashed"
          icon={Brain}
          title={t('empty.title')}
          description={t('empty.description')}
          className="my-4 min-h-[260px]"
        />
      )}

      {!loading && !loadError && items.length > 0 && (
        <div className="relative space-y-4 pl-6 before:absolute before:bottom-2 before:left-2.5 before:top-2 before:w-[2px] before:bg-border/60">
          {items.map((item) => (
            <TimelineNodeCard
              key={item.id}
              item={item}
              agentName={item.agent_id ? agentNames.get(item.agent_id) : undefined}
              onSaveEdit={saveEdit}
              onRequestDelete={requestDelete}
              onRequestSkillToggle={requestSkillToggle}
              onSelectMemoryForGraph={onSelectMemoryForGraph}
            />
          ))}

          {hasMore && (
            <div className="pt-2 text-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void loadPage(false)}
                disabled={loadingMore}
                className="text-xs"
              >
                {loadingMore ? (
                  <div className="mr-2 h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                ) : (
                  <ChevronDown className="mr-1 h-3.5 w-3.5" />
                )}
                {t('loadMore')}
              </Button>
            </div>
          )}
        </div>
      )}

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{dialogCopy.title}</AlertDialogTitle>
            <AlertDialogDescription>{dialogCopy.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmPending}
              className={cn(
                pending?.type === 'delete' && 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
              )}
            >
              {t('confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
});

LearningTimeline.displayName = 'LearningTimeline';

export default LearningTimeline;
