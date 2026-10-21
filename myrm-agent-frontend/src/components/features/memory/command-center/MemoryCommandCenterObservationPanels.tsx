'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 * ../replay/memoryLiveStream::resolveReplaySessionId (POS: Command Center 实时记忆流纯函数)
 * ../cards/EvidenceBadge::EvidenceBadge (POS: 记忆卡片与治理视图中的通用证据徽标组件)
 * ./memoryCommandCenterFormat::translateTimelineTitle (POS: 个人大脑指挥中心面板共用的枚举守卫与文案格式化)
 * ./MemoryCommandCenterPrimitives::MetricTile (POS: 个人大脑指挥中心的版块、指标块、运行时行与空态原子组件)
 *
 * [OUTPUT]
 * InfluenceRow: 单次回答的记忆影响记录行，含证据徽标。
 * EventList: 记忆事件列表，实时模式自动滚动，带会话线索的事件可点击进入回放。
 * RuntimePanel / CostPanel: 运行时状态行与 token 成本指标。
 * ReplayRow: 会话回放概览行。
 *
 * [POS]
 * 个人大脑指挥中心的只读观测面板：记忆影响行、实时事件流、运行时状态、成本与回放概览。
 */

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  MemoryCommandCenterResponse,
  MemoryCommandInfluenceItem,
  MemoryCommandReplayOverlay,
  MemoryCommandTimelineEvent,
} from '@/services/memory/commandCenter';
import { resolveReplaySessionId } from '../replay/memoryLiveStream';
import { EvidenceBadge } from '../cards/EvidenceBadge';
import {
  formatTime,
  translateMemoryType,
  translateRuntimeStatus,
  translateTimelineTitle,
  translateOperationKind,
  formatLiveStreamDescription,
  type MemoryTranslation,
} from './memoryCommandCenterFormat';
import { MetricTile, RuntimeRow, EmptyState } from './MemoryCommandCenterPrimitives';

export const InfluenceRow = ({ item, t }: { item: MemoryCommandInfluenceItem; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm font-medium text-foreground">
        {t('commandCenter.influenceRefs', { count: item.influence_refs.length })}
      </span>
      <span className="text-[11px] text-muted-foreground">{formatTime(item.occurred_at)}</span>
    </div>
    <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.answer_preview}</div>
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      {item.influence_refs.slice(0, 4).map((ref) => (
        <div key={ref.memory_id} className="flex items-center gap-1">
          <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px]">
            {translateMemoryType(ref.memory_type, t)}
            {typeof ref.score === 'number' ? ` · ${ref.score.toFixed(2)}` : ''}
          </span>
          {(ref.source_chat_id || ref.source_message_id) && (
            <EvidenceBadge
              sourceId={ref.source_chat_id}
              messageId={ref.source_message_id}
              quoteSnippet={ref.content_preview}
              t={t}
            />
          )}
        </div>
      ))}
    </div>
  </div>
);

export const EventList = ({
  events,
  t,
  emptyLabel,
  live = false,
  onEventClick,
}: {
  events: MemoryCommandTimelineEvent[];
  t: MemoryTranslation;
  emptyLabel: string;
  live?: boolean;
  onEventClick?: (event: MemoryCommandTimelineEvent) => void;
}) => {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!live || events.length === 0) {
      return;
    }
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [events, live]);

  return events.length ? (
    <div
      ref={listRef}
      className={cn('space-y-2', live && 'max-h-80 overflow-y-auto pr-1')}
      aria-live={live ? 'polite' : undefined}
    >
      {events.map((event) => {
        const replaySessionId = resolveReplaySessionId(event);
        const clickable = Boolean(onEventClick && replaySessionId);
        return (
          <button
            key={event.id}
            type="button"
            disabled={!clickable}
            onClick={() => onEventClick?.(event)}
            className={cn(
              'w-full rounded-lg border border-border/50 bg-accent/20 p-3 text-left transition-colors',
              clickable && 'cursor-pointer hover:border-primary/40 hover:bg-accent/35',
              !clickable && 'cursor-default',
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-border/60 bg-background/70 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {translateOperationKind(event.kind, t, event)}
              </span>
              <span className="text-sm font-medium text-foreground">{translateTimelineTitle(event, t)}</span>
            </div>
            <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
              {formatLiveStreamDescription(event, t)}
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">{formatTime(event.occurred_at)}</span>
              {clickable ? (
                <span className="text-[11px] font-medium text-primary/80">{t('commandCenter.openSessionReplay')}</span>
              ) : null}
            </div>
          </button>
        );
      })}
    </div>
  ) : (
    <EmptyState label={emptyLabel} />
  );
};

export const RuntimePanel = ({ snapshot, t }: { snapshot: MemoryCommandCenterResponse; t: MemoryTranslation }) => (
  <div className="grid gap-2">
    <RuntimeRow label={t('commandCenter.deployMode')} value={snapshot.runtime.deploy_mode} />
    <RuntimeRow
      label={t('commandCenter.vectorStatus')}
      value={translateRuntimeStatus(snapshot.runtime.vector_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.vectorPersistence')}
      value={translateRuntimeStatus(snapshot.runtime.vector_persistence, t)}
      alert={snapshot.runtime.vector_persistence === 'memory_fallback'}
    />
    <RuntimeRow
      label={t('commandCenter.embeddingStatus')}
      value={translateRuntimeStatus(snapshot.runtime.embedding_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.retrievalMode')}
      value={translateRuntimeStatus(snapshot.runtime.retrieval_mode, t)}
      alert={snapshot.runtime.retrieval_mode === 'keyword'}
    />
    <RuntimeRow
      label={t('commandCenter.eventLedgerStatus')}
      value={translateRuntimeStatus(snapshot.runtime.event_ledger_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.healthSnapshotStatus')}
      value={translateRuntimeStatus(snapshot.runtime.health_snapshot_status, t)}
    />
    <RuntimeRow
      label={t('commandCenter.controlPlaneStatus')}
      value={translateRuntimeStatus(snapshot.runtime.control_plane_status, t)}
    />
  </div>
);

export const CostPanel = ({ snapshot, t }: { snapshot: MemoryCommandCenterResponse; t: MemoryTranslation }) => (
  <div className="grid gap-2 sm:grid-cols-2">
    <MetricTile label={t('commandCenter.promptTokens')} value={snapshot.cost.prompt_tokens} dense />
    <MetricTile label={t('commandCenter.cachedTokens')} value={snapshot.cost.cached_tokens} dense />
    <MetricTile label={t('commandCenter.completionTokens')} value={snapshot.cost.completion_tokens} dense />
    <MetricTile
      label={t('commandCenter.cacheFriendly')}
      value={snapshot.cost.cache_friendly ? t('enabled') : t('disabled')}
      dense
    />
  </div>
);

export const ReplayRow = ({ item, t }: { item: MemoryCommandReplayOverlay; t: MemoryTranslation }) => (
  <div className="rounded-lg border border-border/50 bg-accent/20 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="truncate text-sm font-medium text-foreground">{item.chat_id}</span>
      <span className="text-[11px] text-muted-foreground">{formatTime(item.last_event_at)}</span>
    </div>
    <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.last_summary}</div>
    <div className="mt-2 text-[11px] text-muted-foreground">
      {t('commandCenter.replayMeta', { events: item.event_count, influences: item.influence_count })}
    </div>
  </div>
);
