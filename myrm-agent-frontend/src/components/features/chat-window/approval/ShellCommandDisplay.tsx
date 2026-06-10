'use client';

import type { ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { FolderOpen, Info } from 'lucide-react';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/primitives/tooltip';
import type { CommandSpan, PlainExplanation, SpanRiskLevel, SpanRiskReason } from '@/lib/approval/shellCommandDisplay';
import { zipSpansWithRisks } from '@/lib/approval/shellCommandDisplay';

interface ShellCommandDisplayProps {
  command: string;
  toolName: string;
  commandSpans?: CommandSpan[];
  commandSpanRisks?: SpanRiskLevel[];
  commandSpanReasons?: SpanRiskReason[];
  plainExplanation?: PlainExplanation;
  workspaceRoot?: string;
  className?: string;
}

function spanClassName(risk: SpanRiskLevel | undefined): string {
  if (risk === 'unknown') {
    return 'rounded-sm bg-red-500/15 text-red-800 dark:text-red-200 ring-1 ring-red-500/40 px-0.5 cursor-help';
  }
  return 'rounded-sm bg-sky-500/15 text-sky-800 dark:text-sky-200 ring-1 ring-sky-500/30 px-0.5';
}

function renderWithSpans(
  command: string,
  spans: CommandSpan[],
  risks: SpanRiskLevel[] | undefined,
  reasons: SpanRiskReason[] | undefined,
  reasonLabel: (reason: SpanRiskReason) => string,
) {
  const sorted = zipSpansWithRisks(spans, risks, reasons);
  const parts: ReactNode[] = [];
  let cursor = 0;

  sorted.forEach(({ span, risk, reason }) => {
    if (span.startIndex > cursor) {
      parts.push(
        <span key={`gap-${cursor}`} className="text-muted-foreground">
          {command.slice(cursor, span.startIndex)}
        </span>,
      );
    }

    const text = command.slice(span.startIndex, span.endIndex);

    if (risk === 'unknown' && reason && reason !== 'safe') {
      parts.push(
        <Tooltip key={`span-${span.startIndex}`}>
          <TooltipTrigger asChild>
            <span className={spanClassName(risk)}>{text}</span>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            {reasonLabel(reason)}
          </TooltipContent>
        </Tooltip>,
      );
    } else {
      parts.push(
        <span key={`span-${span.startIndex}`} className={spanClassName(risk)}>
          {text}
        </span>,
      );
    }

    cursor = span.endIndex;
  });

  if (cursor < command.length) {
    parts.push(
      <span key={`tail-${cursor}`} className="text-muted-foreground">
        {command.slice(cursor)}
      </span>,
    );
  }

  return parts;
}

export default function ShellCommandDisplay({
  command,
  toolName,
  commandSpans,
  commandSpanRisks,
  commandSpanReasons,
  plainExplanation,
  workspaceRoot,
  className = '',
}: ShellCommandDisplayProps) {
  const t = useTranslations('toolApproval');
  const currentLocale = useLocale();
  const hasSpans = commandSpans && commandSpans.length > 0;
  const explanationText = plainExplanation?.[currentLocale.startsWith('zh') ? 'zh' : 'en']
    ?? plainExplanation?.en;

  const reasonLabel = (reason: SpanRiskReason) => t(`spanRiskReasons.${reason}`);

  return (
    <TooltipProvider delayDuration={200}>
      <div
        className={`rounded-lg border border-border overflow-hidden bg-muted/40 dark:bg-zinc-950 ${className}`}
      >
        <div className="bg-muted/70 dark:bg-zinc-900 px-3 py-1.5 border-b border-border font-mono text-xs text-muted-foreground flex items-center gap-2 min-w-0">
          <span className="text-emerald-600 dark:text-emerald-400 shrink-0">$</span>
          <span className="truncate">{toolName}</span>
        </div>
        <div className="px-3 py-2 font-mono text-xs sm:text-sm whitespace-pre-wrap break-all text-foreground">
          {hasSpans
            ? renderWithSpans(command, commandSpans, commandSpanRisks, commandSpanReasons, reasonLabel)
            : command}
        </div>
        {explanationText && (
          <div className="px-3 py-1.5 border-t border-border bg-amber-500/5 text-xs text-amber-800 dark:text-amber-200 flex items-center gap-1.5 min-w-0">
            <Info className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
            <span className="truncate">{explanationText}</span>
          </div>
        )}
        {workspaceRoot && (
          <div className="px-3 py-1.5 border-t border-border bg-muted/30 text-[10px] text-muted-foreground flex items-center gap-1.5 min-w-0">
            <FolderOpen className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span className="truncate">
              {t('workspaceLabel')}: {workspaceRoot}
            </span>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
