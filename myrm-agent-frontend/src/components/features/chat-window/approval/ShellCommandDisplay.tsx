'use client';

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { FolderOpen } from 'lucide-react';

import type { CommandSpan, SpanRiskLevel } from '@/lib/approval/shellCommandDisplay';
import { zipSpansWithRisks } from '@/lib/approval/shellCommandDisplay';

interface ShellCommandDisplayProps {
  command: string;
  toolName: string;
  commandSpans?: CommandSpan[];
  commandSpanRisks?: SpanRiskLevel[];
  workspaceRoot?: string;
  className?: string;
}

function spanClassName(risk: SpanRiskLevel | undefined): string {
  if (risk === 'unknown') {
    return 'rounded-sm bg-red-500/15 text-red-800 dark:text-red-200 ring-1 ring-red-500/40 px-0.5';
  }
  return 'rounded-sm bg-sky-500/15 text-sky-800 dark:text-sky-200 ring-1 ring-sky-500/30 px-0.5';
}

function renderWithSpans(
  command: string,
  spans: CommandSpan[],
  risks: SpanRiskLevel[] | undefined,
) {
  const sorted = zipSpansWithRisks(spans, risks);
  const parts: ReactNode[] = [];
  let cursor = 0;

  sorted.forEach(({ span, risk }) => {
    if (span.startIndex > cursor) {
      parts.push(
        <span key={`gap-${cursor}`} className="text-muted-foreground">
          {command.slice(cursor, span.startIndex)}
        </span>,
      );
    }
    parts.push(
      <span key={`span-${span.startIndex}`} className={spanClassName(risk)}>
        {command.slice(span.startIndex, span.endIndex)}
      </span>,
    );
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
  workspaceRoot,
  className = '',
}: ShellCommandDisplayProps) {
  const t = useTranslations('toolApproval');
  const hasSpans = commandSpans && commandSpans.length > 0;

  return (
    <div
      className={`rounded-lg border border-border overflow-hidden bg-muted/40 dark:bg-zinc-950 ${className}`}
    >
      <div className="bg-muted/70 dark:bg-zinc-900 px-3 py-1.5 border-b border-border font-mono text-xs text-muted-foreground flex items-center gap-2 min-w-0">
        <span className="text-emerald-600 dark:text-emerald-400 shrink-0">$</span>
        <span className="truncate">{toolName}</span>
      </div>
      {workspaceRoot ? (
        <div className="px-3 py-1.5 border-b border-border/60 flex items-center gap-1.5 text-xs text-muted-foreground min-w-0">
          <FolderOpen className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="font-medium shrink-0">{t('workspaceLabel')}:</span>
          <span className="font-mono truncate" title={workspaceRoot}>
            {workspaceRoot}
          </span>
        </div>
      ) : null}
      <div className="p-3 overflow-x-auto max-h-48 sm:max-h-64">
        <pre className="font-mono text-xs sm:text-sm text-foreground dark:text-gray-100 whitespace-pre-wrap break-all">
          {hasSpans ? renderWithSpans(command, commandSpans, commandSpanRisks) : command}
        </pre>
      </div>
    </div>
  );
}
