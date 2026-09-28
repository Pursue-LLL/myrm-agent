// @orphan-ok Dedicated UI card for custom plugin message entries in conversation stream
import React, { useState } from 'react';
import { Puzzle, ChevronDown, ChevronRight, Clock, Layers } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export interface CustomMessageCardProps {
  customType: string;
  content: string;
  display?: boolean;
  retention?: 'ephemeral' | 'persistent';
  details?: Record<string, unknown> | null;
  timestamp?: string | number | Date;
  className?: string;
}

const formatTimestamp = (raw?: string | number | Date): string | null => {
  if (!raw) return null;
  try {
    const date = raw instanceof Date ? raw : new Date(raw);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return null;
  }
};

export const CustomMessageCard: React.FC<CustomMessageCardProps> = ({
  customType,
  content,
  display = true,
  retention = 'persistent',
  details,
  timestamp,
  className,
}) => {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const formattedTime = formatTimestamp(timestamp);

  // If display is explicitly false, do not render in the conversation stream
  if (display === false) {
    return null;
  }

  const isEphemeral = retention === 'ephemeral';

  return (
    <div
      className={cn(
        'group relative my-3 mx-auto max-w-3xl w-full rounded-xl border p-4 transition-all duration-200',
        'border-primary/20 bg-primary/5 hover:border-primary/30',
        'dark:border-primary/25 dark:bg-primary/[0.03] dark:hover:border-primary/40',
        'shadow-xs',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary dark:bg-primary/20">
            <Puzzle className="h-3.5 w-3.5" />
          </div>
          <span className="text-xs font-semibold tracking-wide uppercase text-primary/90 dark:text-primary/80">
            {customType}
          </span>
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium tracking-tight',
              isEphemeral
                ? 'bg-amber-500/10 text-amber-600 dark:bg-amber-500/15 dark:text-amber-400'
                : 'bg-muted text-muted-foreground',
            )}
            title={
              isEphemeral
                ? 'Ephemeral: will be pruned during compaction'
                : 'Persistent: retained across compaction summaries'
            }
          >
            {isEphemeral ? (
              <>
                <Clock className="h-2.5 w-2.5" />
                <span>Ephemeral</span>
              </>
            ) : (
              <>
                <Layers className="h-2.5 w-2.5" />
                <span>Persistent</span>
              </>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {formattedTime && (
            <span className="text-[10px] text-muted-foreground/70 font-mono tracking-tight">{formattedTime}</span>
          )}
          {details && Object.keys(details).length > 0 && (
            <button
              type="button"
              onClick={() => setDetailsOpen((prev) => !prev)}
              aria-expanded={detailsOpen}
              aria-controls="custom-message-details"
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted/80 hover:text-foreground transition-colors cursor-pointer"
            >
              <span>Details</span>
              {detailsOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            </button>
          )}
        </div>
      </div>

      <div className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">{content}</div>

      {detailsOpen && details && (
        <div
          id="custom-message-details"
          className="mt-3 rounded-lg border border-border/50 bg-background/80 p-3 text-xs font-mono text-muted-foreground dark:bg-background/40"
        >
          <pre className="overflow-x-auto whitespace-pre-wrap break-all">{JSON.stringify(details, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};
