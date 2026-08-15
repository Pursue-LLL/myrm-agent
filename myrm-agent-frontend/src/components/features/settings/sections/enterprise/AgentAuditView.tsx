'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  IconActivity,
  IconAlertTriangle,
  IconBot,
  IconCheckCircle,
  IconChevronDown,
  IconChevronRight,
  IconClock,
  IconShieldAlert,
  IconUser,
  IconWrench,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import {
  type AgentAuditEvent,
  type OrgAgentAuditResponse,
  queryOrgAgentAudit,
} from '@/services/enterprise-admin';
import { getMyOrg } from '@/services/enterprise-org';
import { cn } from '@/lib/utils/classnameUtils';
import SettingsSection from '../SettingsSection';

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
  if (type.startsWith('tool_call')) {return 'tool';}
  if (type.startsWith('approval')) {return 'approval';}
  if (type === 'security_audit') {return 'security';}
  if (type.startsWith('session')) {return 'session';}
  if (type.includes('error') || type.includes('failure')) {return 'error';}
  if (type.includes('llm')) {return 'llm';}
  return 'other';
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  tool_call_start: 'eventTypes.toolCallStart',
  tool_call_finish: 'eventTypes.toolCallFinish',
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
  return /DENY|BLOCK|BREAK|STOP|REJECT/i.test(decision);
}

function decisionDenied(decision: SecurityDecision): boolean {
  return decision.tainted === true || (decision.decision !== null && decision.decision !== undefined && isDenyDecision(decision.decision));
}

function extractDecisions(data: Record<string, unknown>): SecurityDecision[] {
  const decisions = data.decisions;
  if (!Array.isArray(decisions)) {return [];}
  return decisions.filter(
    (d): d is SecurityDecision => d !== null && d !== undefined && typeof d === 'object',
  );
}

function extractToolName(data: Record<string, unknown>): string | null {
  const name = data.tool_name;
  return typeof name === 'string' && name ? name : null;
}

function shortSessionId(sid: string): string {
  if (sid.length <= 12) {return sid;}
  return `${sid.slice(0, 8)}…${sid.slice(-4)}`;
}

function shortUserId(userId: string): string {
  if (userId.length <= 16) {return userId;}
  return `${userId.slice(0, 10)}…${userId.slice(-4)}`;
}

function eventKey(event: AgentAuditEvent): string {
  return `${event.sandbox_id ?? 'sb'}::${event.sid}-${event.seq}`;
}

const AgentAuditView = memo(() => {
  const t = useTranslations('settings.enterprise.audit');
  const [orgId, setOrgId] = useState('');
  const [data, setData] = useState<OrgAgentAuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState<number>(24);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const requestSeqRef = useRef(0);

  const loadData = useCallback(
    async (targetOrgId: string, targetHours: number) => {
      const seq = ++requestSeqRef.current;
      try {
        setLoading(true);
        const result = await queryOrgAgentAudit(targetOrgId, { hours: targetHours, limit: 200 });
        if (seq !== requestSeqRef.current) {return;}
        setData(result);
        setError(null);
      } catch (e) {
        if (seq !== requestSeqRef.current) {return;}
        setError(e instanceof Error ? e.message : 'Failed to load agent activity');
        toast.error(e instanceof Error ? e.message : 'Failed to load agent activity');
      } finally {
        if (seq === requestSeqRef.current) {setLoading(false);}
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const org = await getMyOrg();
        if (cancelled) {return;}
        setOrgId(org.id);
        await loadData(org.id, 24);
      } catch {
        if (cancelled) {return;}
        setError('Failed to load organization');
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      requestSeqRef.current += 1;
    };
  }, [loadData]);

  const onHoursChange = useCallback(
    (value: string) => {
      const next = Number(value);
      setHours(next);
      if (orgId) {
        void loadData(orgId, next);
      }
    },
    [orgId, loadData],
  );

  const toggleExpanded = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {next.delete(key);} else {next.add(key);}
      return next;
    });
  }, []);

  const events = useMemo(() => data?.events ?? [], [data]);
  const securityEvents = useMemo(() => events.filter((e) => e.type === 'security_audit'), [events]);
  const toolEvents = useMemo(
    () => events.filter((e) => e.type === 'tool_call_start' || e.type === 'tool_call_finish'),
    [events],
  );

  if (loading && !data) {
    return (
      <SettingsSection title={t('agentTitle')} description={t('agentDescription')}>
        <div className="animate-pulse space-y-4">
          <div className="h-48 bg-muted rounded" />
          <div className="h-32 bg-muted rounded" />
        </div>
      </SettingsSection>
    );
  }

  return (
    <div className="space-y-6">
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <IconBot className="h-5 w-5" />
            {t('agentTitle')}
          </span>
        }
        description={t('agentDescription')}
        action={
          <div className="flex items-center gap-2">
            <Select value={String(hours)} onValueChange={onHoursChange}>
              <SelectTrigger className="w-24 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="24">24h</SelectItem>
                <SelectItem value="168">7d</SelectItem>
                <SelectItem value="720">30d</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      >
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-700 dark:text-red-400">
            <IconAlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">{t('agentLoadFailed')}</p>
              <p className="mt-0.5 break-all">{error}</p>
            </div>
          </div>
        )}
        {data && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{data.total}</div>
                <div className="text-xs text-muted-foreground">{t('agentTotalEvents')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{toolEvents.length}</div>
                <div className="text-xs text-muted-foreground">{t('agentToolCalls')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold text-red-600">{securityEvents.length}</div>
                <div className="text-xs text-muted-foreground">{t('agentSecurityEvents')}</div>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <div className="text-2xl font-bold">{data.scanned_sandboxes}</div>
                <div className="text-xs text-muted-foreground">{t('agentScannedSandboxes')}</div>
              </div>
            </div>

            {data.failed_sandboxes.length > 0 && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
                <IconAlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium">{t('agentFailedSandboxes')}</p>
                  <p className="mt-0.5 font-mono text-amber-600/80 dark:text-amber-400/80 break-all">
                    {data.failed_sandboxes.join(', ')}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </SettingsSection>

      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <IconActivity className="h-4 w-4" />
            {t('agentEventList')}
          </span>
        }
      >
        <div className="space-y-1.5 max-h-[26rem] overflow-y-auto pr-1">
          {data && data.total > events.length && (
            <p className="pb-1 px-0.5 text-[10px] text-muted-foreground">
              {t('agentShowingLatest', { shown: events.length, total: data.total })}
            </p>
          )}
          {events.map((event) => (
            <AgentEventRow
              key={eventKey(event)}
              event={event}
              expanded={expanded.has(eventKey(event))}
              onToggle={() => toggleExpanded(eventKey(event))}
            />
          ))}
          {events.length === 0 && (
            <div className="text-center py-8 text-muted-foreground text-sm">{t('agentNoEvents')}</div>
          )}
        </div>
      </SettingsSection>
    </div>
  );
});
AgentAuditView.displayName = 'AgentAuditView';

interface AgentEventRowProps {
  event: AgentAuditEvent;
  expanded: boolean;
  onToggle: () => void;
}

const AgentEventRow = memo<AgentEventRowProps>(({ event, expanded, onToggle }) => {
  const t = useTranslations('settings.enterprise.audit');
  const tone = eventTone(event.type);
  const toneStyle = TONE_STYLES[tone];
  const toolName = extractToolName(event.data);
  const decisions = extractDecisions(event.data);
  const critical =
    decisions.length > 0 && decisions.some((d) => decisionDenied(d));
  const Chevron = expanded ? IconChevronDown : IconChevronRight;

  const ToneIcon = tone === 'security'
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
        critical
          ? 'border-rose-500/30 bg-rose-500/5'
          : 'border-border/40 bg-background/50 hover:bg-muted/30',
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
                  title={event.user_id}
                  className="inline-flex items-center gap-1 rounded border border-border/50 bg-muted/60 px-1.5 py-px font-mono text-[10px] text-foreground/80"
                >
                  <IconUser className="h-2.5 w-2.5" />
                  {shortUserId(event.user_id)}
                </span>
                <span>·</span>
              </>
            )}
            <span className="font-mono">{shortSessionId(event.sid)}</span>
            <span>·</span>
            <span>{new Date(event.ts * 1000).toLocaleString()}</span>
          </div>
        </div>
        {critical && (
          <IconShieldAlert className="h-3.5 w-3.5 shrink-0 text-rose-500" />
        )}
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
                        decisionDenied(decision)
                          ? 'text-rose-500'
                          : 'text-amber-500',
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

export default AgentAuditView;
