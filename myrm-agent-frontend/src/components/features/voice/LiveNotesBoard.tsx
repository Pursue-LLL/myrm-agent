/**
 * [INPUT]
 * - @/services/liveMeeting::LiveMeetingSnapshot (POS: live meeting rolling-notes DTO)
 *
 * [OUTPUT]
 * - LiveNotesBoard: in-meeting rolling structured-notes board
 *
 * [POS]
 * Live meeting deliverables board. Renders the rolling summary, decisions and action
 * items produced during a live meeting with a responsive, dual-theme layout.
 */

'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { ClipboardList, ListChecks, MessageSquareQuote } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { LiveMeetingSnapshot } from '@/services/liveMeeting';

interface LiveNotesBoardProps {
  snapshot: LiveMeetingSnapshot | null;
  className?: string;
}

const LiveNotesBoard = memo(function LiveNotesBoard({ snapshot, className }: LiveNotesBoardProps) {
  const t = useTranslations('voice.liveNotes');
  const hasContent =
    snapshot !== null &&
    (Boolean(snapshot.summary) ||
      snapshot.decisions.length > 0 ||
      snapshot.action_items.length > 0);

  return (
    <div
      className={cn(
        'flex h-full flex-col rounded-xl border border-border bg-card/60 backdrop-blur-sm',
        className,
      )}
      data-testid="live-notes-board"
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium text-foreground">{t('title')}</span>
        </div>
        {snapshot && snapshot.line_count > 0 && (
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {t('lines', { count: snapshot.line_count })}
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
        {!hasContent && <p className="py-6 text-center text-xs text-muted-foreground">{t('empty')}</p>}

        {snapshot?.summary && (
          <section className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <MessageSquareQuote className="h-3.5 w-3.5" />
              {t('summary')}
            </div>
            <p className="text-sm leading-relaxed text-foreground/90">{snapshot.summary}</p>
          </section>
        )}

        {snapshot && snapshot.decisions.length > 0 && (
          <section className="space-y-1.5">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {t('decisions')}
            </div>
            <ul className="space-y-1">
              {snapshot.decisions.map((decision, index) => (
                <li key={`${index}-${decision}`} className="flex gap-2 text-sm text-foreground/90">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" />
                  <span>{decision}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {snapshot && snapshot.action_items.length > 0 && (
          <section className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <ListChecks className="h-3.5 w-3.5" />
              {t('actionItems')}
            </div>
            <ul className="space-y-1.5">
              {snapshot.action_items.map((item, index) => (
                <li
                  key={`${index}-${item.description}`}
                  className="rounded-lg border border-border bg-background/60 px-2.5 py-1.5 text-sm text-foreground/90"
                >
                  <div>{item.description}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">
                    {t('owner')}: {item.owner || t('unassigned')}
                    {item.due_hint ? ` · ${t('due')}: ${item.due_hint}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
});

export default LiveNotesBoard;
