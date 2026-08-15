import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertCircle,
  AlertTriangle,
  Ban,
  CheckCircle2,
  Clock,
  Hand,
  Hourglass,
  Loader2,
  RotateCcw,
  ShieldCheck,
  StopCircle,
  XCircle,
} from 'lucide-react';
import type { StreamEntry, SubagentStatus } from '@/store/chat/useSubagentStore';

export const STATUS_ICON_MAP: Record<SubagentStatus, { icon: typeof Loader2; className: string; spin?: boolean }> = {
  pending: { icon: Clock, className: 'text-slate-400' },
  pending_approval: { icon: Hourglass, className: 'text-amber-500' },
  running: { icon: Loader2, className: 'text-blue-500', spin: true },
  verifying: { icon: ShieldCheck, className: 'text-amber-500', spin: true },
  completed: { icon: CheckCircle2, className: 'text-green-500' },
  failed: { icon: XCircle, className: 'text-red-500' },
  timed_out: { icon: AlertCircle, className: 'text-yellow-500' },
  cancelled: { icon: StopCircle, className: 'text-gray-500' },
  cancelled_by_budget: { icon: Ban, className: 'text-rose-500' },
  yielded: { icon: Hand, className: 'text-purple-500' },
  checkpoint: { icon: RotateCcw, className: 'text-purple-500' },
  interrupted: { icon: AlertTriangle, className: 'text-orange-500' },
};

export const StatusIcon = ({ status }: { status: SubagentStatus }) => {
  const config = STATUS_ICON_MAP[status] ?? STATUS_ICON_MAP.running;
  const Icon = config.icon;
  return <Icon className={`w-4 h-4 ${config.className} ${config.spin ? 'animate-spin' : ''}`} />;
};

const STREAM_GLYPH: Record<StreamEntry['kind'], { char: string; color: string }> = {
  tool: { char: '●', color: 'text-foreground/60' },
  progress: { char: '›', color: 'text-muted-foreground/70' },
  thinking: { char: '…', color: 'text-muted-foreground/50' },
  error: { char: '✕', color: 'text-destructive' },
};

const StreamLine = ({ entry, expanded }: { entry: StreamEntry; expanded?: boolean }) => {
  const glyph = STREAM_GLYPH[entry.kind];
  return (
    <div className="flex items-baseline gap-1.5 text-[11px] leading-relaxed min-w-0">
      <span className={`shrink-0 font-mono text-[10px] ${glyph.color}`}>{glyph.char}</span>
      <span className={`min-w-0 ${expanded ? 'break-words' : 'truncate'} ${entry.isError ? 'text-destructive' : 'text-muted-foreground/80'}`}>
        {entry.text}
      </span>
      {entry.durationMs !== null && entry.durationMs !== undefined && (
        <span className="shrink-0 text-[10px] text-muted-foreground/50 tabular-nums">
          {entry.durationMs < 1000 ? `${entry.durationMs}ms` : `${(entry.durationMs / 1000).toFixed(1)}s`}
        </span>
      )}
    </div>
  );
};

export const NodeStream = ({ stream, isRunning }: { stream: StreamEntry[]; isRunning: boolean }) => {
  const t = useTranslations('subagentDashboard');
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const visibleEntries = useMemo(() => {
    if (expanded) {return stream;}
    return isRunning ? stream.slice(-5) : stream.slice(-2);
  }, [stream, isRunning, expanded]);

  useEffect(() => {
    if (isRunning && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [visibleEntries.length, isRunning]);

  if (stream.length === 0) {return null;}

  const hasMore = stream.length > (isRunning ? 5 : 2);

  return (
    <div className="ml-7 mt-1">
      {hasMore && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="text-[10px] text-muted-foreground/60 hover:text-muted-foreground mb-0.5"
        >
          +{stream.length - visibleEntries.length} {t('streamMore')}
        </button>
      )}
      <div ref={scrollRef} className="flex flex-col gap-0.5 max-h-32 overflow-y-auto">
        {visibleEntries.map((entry, i) => (
          <StreamLine key={`${entry.timestamp}-${i}`} entry={entry} expanded={expanded} />
        ))}
      </div>
      {expanded && hasMore && (
        <button
          onClick={() => setExpanded(false)}
          className="text-[10px] text-muted-foreground/60 hover:text-muted-foreground mt-0.5"
        >
          {t('streamCollapse')}
        </button>
      )}
    </div>
  );
};
