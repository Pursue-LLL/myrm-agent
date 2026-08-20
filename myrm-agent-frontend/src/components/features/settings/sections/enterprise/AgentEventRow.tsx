'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconAlertTriangle,
  IconBot,
  IconChevronDown,
  IconChevronRight,
  IconClock,
  IconShieldAlert,
  IconUser,
  IconWrench,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';
import type { AgentAuditEvent } from '@/services/enterprise-admin';
import { cn } from '@/lib/utils/classnameUtils';

interface SecurityDecision {
  tool_call_id?: string;
  decision?: string;
  reason?: string;
  tainted?: boolean;
  ts?: number;
}

type AgentEventTone = 'tool' | 'approval' | 'security' | 'session' | 'error' | 'llm' | 'other';

const TONE_STYLES: Record<AgentEventTone, { label: string; className: string }> = {
  tool: { label: 'toneTool', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/25' },
  approval: {
    label: 'toneApproval',
    className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25',
  },
  security: {
    label: 'toneSecurity',
    className: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25',
  },
  session: {
    label: 'toneSession',
    className: 'bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/25',
  },
  error: { label: 'toneError', className: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25' },
  llm: { label: 'toneLlm', className: 'bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-500/25' },
  other: {
    label: 'toneOther',
    className: 'bg-muted text-muted-foreground border-border',
  },
};

function eventTone(type: string): AgentEventTone {
  if (type === 'security_audit') {
    return 'security';
  }
  if (type.includes('approval')) {
    return 'approval';
  }
  if (type.startsWith('session')) {
    return 'session';
  }
  if (/error|failure|failed|cancelled|timeout|denied|rejected|interruption|exhausted|aborted/i.test(type)) {
    return 'error';
  }
  if (type.startsWith('tool_')) {
    return 'tool';
  }
  if (type.includes('llm')) {
    return 'llm';
  }
  return 'other';
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  tool_start: 'eventTypes.toolStart',
  tool_end: 'eventTypes.toolEnd',
  security_audit: 'eventTypes.securityAudit',
  session_start: 'eventTypes.sessionStart',
  session_end: 'eventTypes.sessionEnd',
  llm_request: 'eventTypes.llmRequest',
  tool_approval_request: 'eventTypes.approvalRequest',
  approval_intercepted: 'eventTypes.approvalIntercepted',
  tool_failure: 'eventTypes.toolFailure',
  error: 'eventTypes.error',
  user_interruption: 'eventTypes.userInterruption',
  message_end: 'eventTypes.messageEnd',
};

/** 将 harness 内部事件类型映射为人性化文案；未知类型降级为空格分隔形式。 */
function eventTypeLabel(type: string, t: (key: string) => string): string {
  const labelKey = EVENT_TYPE_LABELS[type];
  return labelKey ? t(labelKey) : type.replace(/_/g, ' ');
}

function isDenyDecision(decision: string): boolean {
  // 与 harness myrm-agent-harness/core/security/audit.py record_decision 的
  // 权威 deny 语义（policy_denial_total 口径）保持一致：BLOCK/DENY/REDACT/LEAK。
  return /BLOCK|DENY|REDACT|LEAK/i.test(decision);
}

function decisionDenied(decision: SecurityDecision): boolean {
  return (
    decision.tainted === true ||
    (decision.decision !== null && decision.decision !== undefined && isDenyDecision(decision.decision))
  );
}

function extractDecisions(data: Record<string, unknown>): SecurityDecision[] {
  const decisions = data.decisions;
  if (!Array.isArray(decisions)) {
    return [];
  }
  return decisions.filter((d): d is SecurityDecision => d !== null && d !== undefined && typeof d === 'object');
}

function extractToolName(data: Record<string, unknown>): string | null {
  const name = data.tool_name;
  return typeof name === 'string' && name ? name : null;
}

function shortSessionId(sid: string): string {
  if (sid.length <= 12) {
    return sid;
  }
  return `${sid.slice(0, 8)}…${sid.slice(-4)}`;
}

function shortUserId(userId: string): string {
  if (userId.length <= 16) {
    return userId;
  }
  return `${userId.slice(0, 10)}…${userId.slice(-4)}`;
}

function shortUserDisplay(display: string): string {
  if (display.length <= 24) {
    return display;
  }
  return `${display.slice(0, 16)}…${display.slice(-6)}`;
}

export function eventKey(event: AgentAuditEvent): string {
  return `${event.sandbox_id ?? 'sb'}::${event.sid}-${event.seq}`;
}

interface AgentEventRowProps {
  event: AgentAuditEvent;
  expanded: boolean;
  onToggle: () => void;
}

export const AgentEventRow = memo<AgentEventRowProps>(({ event, expanded, onToggle }) => {
  const t = useTranslations('settings.enterprise.audit');
  const tone = eventTone(event.type);
  const toneStyle = TONE_STYLES[tone];
  const toolName = extractToolName(event.data);
  const decisions = extractDecisions(event.data);
  const critical = decisions.length > 0 && decisions.some((d) => decisionDenied(d));
  const Chevron = expanded ? IconChevronDown : IconChevronRight;

  const ToneIcon =
    tone === 'security'
      ? IconShieldAlert
      : tone === 'error'
        ? IconXCircle
        : tone === 'tool'
          ? IconWrench
          : tone === 'approval'
            ? IconAlertTriangle
            : tone === 'session'
              ? IconClock
              : IconBot;

  return (
    <div
      className={cn(
        'rounded-lg border transition-all duration-200',
        critical ? 'border-rose-500/30 bg-rose-500/5' : 'border-border/40 bg-background/50 hover:bg-muted/30',
      )}
    >
      <button onClick={onToggle} className="w-full flex items-center gap-2.5 p-2.5 text-left">
        <Chevron className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <Badge className={cn('text-[10px] shrink-0 border', toneStyle.className)}>{t(toneStyle.label)}</Badge>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <ToneIcon className={cn('h-3.5 w-3.5 shrink-0', critical ? 'text-rose-500' : 'text-muted-foreground')} />
            {toolName ? (
              <span className="font-mono text-sm truncate">{toolName}</span>
            ) : (
              <span className="text-sm truncate">{eventTypeLabel(event.type, t)}</span>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-0.5 flex-wrap">
            {event.user_id && (
              <>
                <span
                  title={event.user_display ? `${event.user_display} (${event.user_id})` : event.user_id}
                  className="inline-flex items-center gap-1 rounded border border-border/50 bg-muted/60 px-1.5 py-px font-mono text-[10px] text-foreground/80"
                >
                  <IconUser className="h-2.5 w-2.5" />
                  {event.user_display ? shortUserDisplay(event.user_display) : shortUserId(event.user_id)}
                </span>
                <span>·</span>
              </>
            )}
            <span className="font-mono">{shortSessionId(event.sid)}</span>
            <span>·</span>
            <span>{new Date(event.ts * 1000).toLocaleString()}</span>
          </div>
        </div>
        {critical && <IconShieldAlert className="h-3.5 w-3.5 shrink-0 text-rose-500" />}
      </button>

      {expanded && (
        <div className="space-y-2 pb-2.5 px-3">
          {decisions.length > 0 && (
            <div className="px-2">
              <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {t('agentSecurityDecisions')}
              </p>
              <div className="space-y-1">
                {decisions.map((decision, idx) => (
                  <div
                    key={idx}
                    className={cn(
                      'flex items-start gap-2 rounded-md border px-2 py-1.5 text-xs',
                      decisionDenied(decision)
                        ? 'border-rose-500/25 bg-rose-500/5'
                        : 'border-amber-500/25 bg-amber-500/5',
                    )}
                  >
                    <IconShieldAlert
                      className={cn(
                        'h-3.5 w-3.5 shrink-0 mt-0.5',
                        decisionDenied(decision) ? 'text-rose-500' : 'text-amber-500',
                      )}
                    />
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">{decision.decision}</span>
                      {decision.reason && (
                        <span className="ml-2 text-muted-foreground break-words">{decision.reason}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="px-2">
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {t('agentDetails')}
            </p>
            <pre className="rounded-md bg-muted p-2 text-[11px] text-foreground overflow-x-auto whitespace-pre-wrap break-words font-mono">
              {JSON.stringify(event.data, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
});
AgentEventRow.displayName = 'AgentEventRow';
