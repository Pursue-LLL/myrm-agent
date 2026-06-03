'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { TaskEvent, TaskRun } from '@/services/kanban';
import { OUTCOME_STYLES, EVENT_KIND_STYLES, formatDuration, formatTime } from './kanban-styles';
import KanbanMarkdown from './KanbanMarkdown';

interface KanbanRunHistoryProps {
  runs: TaskRun[];
}

export function KanbanRunHistory({ runs }: KanbanRunHistoryProps) {
  const t = useTranslations('kanban');

  return (
    <section>
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
        {t('executionHistory')}
      </h4>
      {runs.length === 0 ? (
        <p className="text-[10px] text-muted-foreground">{t('noRuns')}</p>
      ) : (
        <div className="space-y-1.5">
          {runs.map((run) => (
            <div key={run.run_id} className="rounded border bg-muted/20 px-2 py-1.5">
              <div className="flex items-center gap-2 text-[10px]">
                <span className={cn('font-medium', OUTCOME_STYLES[run.outcome ?? ''] ?? 'text-muted-foreground')}>
                  {run.outcome ?? '...'}
                </span>
                <span className="text-muted-foreground">{formatDuration(run.duration_seconds)}</span>
                <span className="text-muted-foreground truncate max-w-[100px]" title={run.worker_id}>
                  {run.worker_id.slice(0, 12)}
                </span>
              </div>
              {run.summary && (
                <KanbanMarkdown className="text-foreground/70 mt-0.5" maxLines={2}>
                  {run.summary}
                </KanbanMarkdown>
              )}
              {run.error && (
                <p
                  className="text-[10px] font-mono text-destructive mt-0.5 line-clamp-2 whitespace-pre-wrap"
                  title={run.error}
                >
                  {run.error}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

interface KanbanEventTimelineProps {
  events: TaskEvent[];
}

export function KanbanEventTimeline({ events }: KanbanEventTimelineProps) {
  const t = useTranslations('kanban');

  return (
    <section>
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
        {t('eventTimeline')}
      </h4>
      {events.length === 0 ? (
        <p className="text-[10px] text-muted-foreground">{t('noEvents')}</p>
      ) : (
        <div className="space-y-1">
          {events.map((ev) => (
            <div key={ev.event_id} className="text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="text-muted-foreground shrink-0">{formatTime(ev.created_at)}</span>
                <span
                  className={cn(
                    'px-1 py-0.5 rounded text-[9px] font-medium shrink-0',
                    EVENT_KIND_STYLES[ev.kind] ?? 'bg-muted text-muted-foreground',
                  )}
                >
                  {t(`eventKind.${ev.kind}` as Parameters<typeof t>[0])}
                </span>
                {ev.kind === 'user_comment' && ev.payload && (
                  <span className="text-muted-foreground italic truncate">@{String(ev.payload.author ?? 'user')}</span>
                )}
              </div>
              {ev.kind === 'user_comment' && ev.payload?.body && (
                <div className="ml-[52px] mt-0.5">
                  <KanbanMarkdown className="text-foreground/80">{String(ev.payload.body)}</KanbanMarkdown>
                </div>
              )}
              {ev.kind === 'heartbeat' && ev.payload?.note && (
                <p className="ml-[52px] text-[10px] text-chart-4/80 mt-0.5">{String(ev.payload.note)}</p>
              )}
              {ev.kind === 'branch_switched' && ev.payload && (
                <p className="ml-[52px] text-[10px] text-blue-500/80 mt-0.5">
                  <span className="font-medium text-blue-500">Branch:</span> {String(ev.payload.from || 'unknown')}{' '}
                  &rarr; {String(ev.payload.to || 'unknown')}
                  {ev.payload.migrated ? ' (Migrated)' : ' (Stashed)'}
                </p>
              )}
              {ev.kind === 'verification_failed' && ev.payload?.reason && (
                <div className="ml-[52px] mt-0.5">
                  <span className="text-[10px] font-medium text-chart-5">{t('verificationReason')}:</span>
                  <KanbanMarkdown className="text-chart-5/80 mt-0.5" maxLines={4}>
                    {String(ev.payload.reason)}
                  </KanbanMarkdown>
                </div>
              )}
              {ev.kind === 'timed_out' && ev.payload && (
                <p className="ml-[52px] text-[10px] text-chart-5/80 mt-0.5">
                  {t('timedOutDetail', {
                    elapsed: Number(ev.payload.elapsed_seconds ?? 0),
                    limit: Number(ev.payload.limit_seconds ?? 0),
                  })}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
