'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

interface ConsensusRef {
  model: string;
  success: boolean;
  elapsed: number;
  content?: string;
}

interface ConsensusThinkingPanelProps {
  refs: ConsensusRef[];
  isStreaming: boolean;
  totalExpected?: number;
}

function formatModelName(model: string): string {
  if (model.includes('/')) {
    return model.split('/').pop() ?? model;
  }
  return model;
}

function RefCard({ ref, defaultExpanded }: { ref: ConsensusRef; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const preview = ref.content ? ref.content.slice(0, 120) + (ref.content.length > 120 ? '…' : '') : '';

  return (
    <div className="border border-border/50 rounded-md overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors"
      >
        {ref.success ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
        ) : (
          <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
        )}
        <span className="font-medium text-foreground truncate">
          {formatModelName(ref.model)}
        </span>
        <span className="text-muted-foreground ml-auto tabular-nums shrink-0">
          {ref.elapsed.toFixed(1)}s
        </span>
        {ref.content && (
          expanded
            ? <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
            : <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
        )}
      </button>
      {expanded && ref.content && (
        <div className="px-2.5 pb-2 pt-0.5 text-xs text-muted-foreground leading-relaxed border-t border-border/30 max-h-40 overflow-y-auto">
          <p className="whitespace-pre-wrap break-words">{ref.content}</p>
        </div>
      )}
      {!expanded && preview && (
        <div className="px-2.5 pb-1.5 text-[11px] text-muted-foreground/70 truncate">
          {preview}
        </div>
      )}
    </div>
  );
}

export default function ConsensusThinkingPanel({
  refs,
  isStreaming,
  totalExpected,
}: ConsensusThinkingPanelProps) {
  const t = useTranslations('messageBox');
  const [collapsed, setCollapsed] = useState(false);

  if (refs.length === 0 && !isStreaming) return null;

  const completedCount = refs.length;
  const total = totalExpected ?? refs.length;
  const allDone = !isStreaming && completedCount === total;

  return (
    <div className={cn(
      'mb-2 rounded-lg border border-border/60 bg-muted/20 overflow-hidden transition-all duration-300',
      collapsed && 'bg-transparent border-transparent',
    )}>
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {isStreaming && completedCount < total ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
        )}
        <span className="font-medium">
          {t('consensusMetaTitle', { defaultMessage: 'Multi-model Consensus' })}
        </span>
        <span className="tabular-nums">
          {completedCount}/{total}
        </span>
        {collapsed
          ? <ChevronRight className="w-3 h-3 ml-auto" />
          : <ChevronDown className="w-3 h-3 ml-auto" />
        }
      </button>
      {!collapsed && (
        <div className="px-3 pb-2 space-y-1.5">
          {refs.map((ref, i) => (
            <RefCard key={`${ref.model}-${i}`} ref={ref} defaultExpanded={false} />
          ))}
          {isStreaming && completedCount < total && (
            <div className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-muted-foreground">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>{t('consensusActive', { defaultMessage: 'Waiting for remaining models…' })}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
