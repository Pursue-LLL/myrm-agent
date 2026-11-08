'use client';

import { useTranslations } from 'next-intl';
import { ShieldAlert } from 'lucide-react';
import ShellCommandDisplay from '@/components/features/chat-window/approval/ShellCommandDisplay';
import ApprovalScopeNoteLine from '@/components/approval/ApprovalScopeNoteLine';
import {
  extractShellCommand,
  parseCommandSpanReasons,
  parseCommandSpanRisks,
  parseCommandSpans,
  parsePlainExplanation,
} from '@/lib/approval/shellCommandDisplay';
import type { ApprovalToolCall } from '@/store/useApprovalStore';

interface Escalation {
  command?: string;
  base_cmd?: string;
  reason?: string;
  details?: string;
}

/** The commands the sandbox policy escalated for approval, each with the reason it needs one. */
function EscalationNotice({ escalations }: { escalations: Escalation[] }) {
  const t = useTranslations('toolApproval');
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 dark:bg-amber-950/20 p-3 space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold text-amber-700 dark:text-amber-400">
        <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span>{t('escalationTitle')}</span>
      </div>
      <div className="space-y-1.5 pl-6">
        {escalations.map((esc, escIdx) => {
          const reasonKey = esc.reason || '';
          const reasonLabel =
            reasonKey && t.has(`escalationReasons.${reasonKey}`)
              ? t(`escalationReasons.${reasonKey}`)
              : reasonKey || t('escalationFallbackReason');
          return (
            <div key={escIdx} className="flex flex-wrap items-center gap-2 text-xs text-foreground/90">
              <span className="font-medium text-amber-800 dark:text-amber-300">{reasonLabel}:</span>
              <code className="rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[11px] border border-border/40 break-all max-w-full">
                {esc.command || esc.base_cmd}
              </code>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** A shell or code-execution call: its stated intent, scope, escalated commands and the annotated command itself. */
export function ShellToolCallApproval({ call, workspaceRoot }: { call: ApprovalToolCall; workspaceRoot?: string }) {
  const t = useTranslations('toolApproval');
  const tHumanize = useTranslations('humanize');
  const { args } = call;
  const command = extractShellCommand(args);
  const commandSpans = parseCommandSpans(args.command_spans ?? args.commandSpans, command.length);
  const commandSpanRisks = commandSpans
    ? parseCommandSpanRisks(args.command_span_risks ?? args.commandSpanRisks, commandSpans.length)
    : undefined;
  const commandSpanReasons = commandSpans
    ? parseCommandSpanReasons(args.command_span_reasons ?? args.commandSpanReasons, commandSpans.length)
    : undefined;
  const plainExplanation = parsePlainExplanation(args.plain_explanation ?? args.plainExplanation);
  const executionIntent =
    typeof args.execution_intent === 'string' && args.execution_intent.trim()
      ? args.execution_intent.trim()
      : typeof args.reason === 'string' && args.reason.trim()
        ? args.reason.trim()
        : undefined;
  const escalations = Array.isArray(args.escalations) ? (args.escalations as Escalation[]) : [];
  return (
    <div className="space-y-2">
      {executionIntent && (
        <div className="text-xs text-foreground/90 rounded-md border border-border/60 bg-muted/40 px-2.5 py-2">
          <span className="font-medium text-muted-foreground">{t('executionIntent')}:</span> {executionIntent}
        </div>
      )}
      <ApprovalScopeNoteLine toolName={call.name} toolInput={args} tHumanize={tHumanize} />
      {escalations.length > 0 && <EscalationNotice escalations={escalations} />}
      <ShellCommandDisplay
        toolName={call.name}
        command={command}
        commandSpans={commandSpans}
        commandSpanRisks={commandSpanRisks}
        commandSpanReasons={commandSpanReasons}
        plainExplanation={plainExplanation}
        workspaceRoot={workspaceRoot}
      />
    </div>
  );
}
