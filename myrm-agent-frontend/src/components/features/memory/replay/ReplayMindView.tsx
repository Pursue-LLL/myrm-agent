'use client';

/**
 * Replay "mind" pane: LLM calls, memory events, human approvals, reasoning
 * traces, and tool rows with step-level security badges.
 */

import { useTranslations } from 'next-intl';
import {
  IconBrain,
  IconCpu,
  IconShieldAlert,
  IconShieldCheck,
  IconWrench,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  TraceHumanFeedback,
  TraceLLMCall,
  TraceMemoryEvent,
  TraceToolCall,
} from '@/services/statistics';
import type { Message } from '@/store/chat/types';
import { messageReasoning } from '@/components/features/memory/replay/replayTimeline';

interface ReplayMindViewProps {
  llmCalls: TraceLLMCall[];
  memoryEvents: TraceMemoryEvent[];
  humanFeedback: TraceHumanFeedback[];
  messages: Message[];
  tools: TraceToolCall[];
}

function isDenyDecision(decision: string): boolean {
  return /DENY|BLOCK|BREAK|STOP|REJECT/i.test(decision);
}

function ReplayMindView({ llmCalls, memoryEvents, humanFeedback, messages, tools }: ReplayMindViewProps) {
  const t = useTranslations('settings.sessionAnalytics.replay');

  return (
    <div className="flex-1 flex flex-col gap-2">
      {llmCalls.map((lc) => (
        <div
          key={`llm-${lc.sequence}`}
          className="flex items-center gap-2 text-xs p-2 rounded-full border border-border/40 bg-violet-500/5"
        >
          <IconCpu className="w-3.5 h-3.5 shrink-0 text-violet-500" />
          <span className="font-medium text-foreground truncate">{lc.model_name ?? 'LLM'}</span>
          <span className="text-muted-foreground ml-auto shrink-0 font-mono">
            {(lc.total_tokens ?? 0).toLocaleString()} tok
          </span>
        </div>
      ))}
      {memoryEvents.map((me) => (
        <div
          key={`mem-${me.id}`}
          className="flex items-center gap-2 text-xs p-2 rounded-full border border-teal-500/30 bg-teal-500/5"
        >
          <IconBrain className="w-3.5 h-3.5 shrink-0 text-teal-500" />
          <span className="font-medium text-foreground truncate">
            {me.title === 'pre_compact' ? t('preCompactEventTitle') : me.title}
          </span>
          <span className="text-muted-foreground ml-auto shrink-0 text-[10px] uppercase">{me.phase}</span>
        </div>
      ))}
      {humanFeedback.map((fb, idx) => {
        const approved = fb.approved;
        const Icon = approved ? IconShieldCheck : IconShieldAlert;
        return (
          <div
            key={`fb-${idx}-${fb.timestamp}`}
            className={cn(
              'flex items-center gap-2 text-xs p-2 rounded-full border',
              approved ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-rose-500/30 bg-rose-500/5',
            )}
          >
            <Icon className={cn('w-3.5 h-3.5 shrink-0', approved ? 'text-emerald-500' : 'text-rose-500')} />
            <span className="font-medium text-foreground truncate">{fb.tool_name ?? t('humanFeedback')}</span>
            <span className={cn('ml-auto shrink-0', approved ? 'text-emerald-600' : 'text-rose-600')}>
              {approved ? t('approved') : t('rejected')}
            </span>
          </div>
        );
      })}
      {messages.map((m) => {
        const reasoning = messageReasoning(m);
        if (!reasoning) {
          return null;
        }
        return (
          <div
            key={`reasoning-${m.messageId}`}
            className="text-xs text-muted-foreground font-mono bg-muted/30 p-2 rounded-full whitespace-pre-wrap"
          >
            {reasoning}
          </div>
        );
      })}
      {tools.map((tc) => {
        const securityLabels = tc.security_labels ?? [];
        const hasSecurity = securityLabels.length > 0;
        const critical = hasSecurity && securityLabels.some((s) => s.tainted || isDenyDecision(s.decision));
        return (
          <div
            key={`tool-${tc.sequence}-${tc.tool_name}`}
            className="flex items-center gap-2 text-xs p-2 rounded-full border border-border/40 bg-muted/10"
          >
            <IconWrench
              className={cn(
                'w-3.5 h-3.5 shrink-0',
                tc.end_time ? (tc.success ? 'text-emerald-500' : 'text-rose-500') : 'text-amber-500 animate-pulse',
              )}
            />
            <span className="font-medium text-foreground truncate">{tc.tool_name}</span>
            {!tc.end_time && <span className="text-muted-foreground ml-auto shrink-0">{t('running')}</span>}
            {hasSecurity && (
              <span
                className={cn(
                  'ml-auto shrink-0 inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-medium',
                  critical
                    ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30'
                    : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30',
                )}
                title={securityLabels.map((s) => `${s.decision}: ${s.reason ?? ''}`).join('\n')}
              >
                <IconShieldAlert className="w-3 h-3" />
                {t('securityFlag')}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default ReplayMindView;
