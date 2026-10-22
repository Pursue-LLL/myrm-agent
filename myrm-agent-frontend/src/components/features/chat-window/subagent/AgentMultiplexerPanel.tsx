'use client';

/**
 * [INPUT]
 * - react::{memo, useState, useCallback}
 * - next-intl::useTranslations (POS: i18n dictionary)
 * - lucide-react::{Terminal, Send, Eye, ShieldAlert, Cpu, CheckCircle2, AlertCircle, Bot}
 * - @/lib/utils/classnameUtils::cn
 *
 * [OUTPUT]
 * - AgentMultiplexerPanel: tmux-style persistent multi-agent multiplexer & cross-agent inspect/instruct console.
 *
 * [POS]
 * Persistent Multi-Agent Multiplexer workbench. Allows humans and orchestrator agents to slice
 * across concurrent sessions, inspect recent logs/artifacts, and inject real-time steering directives.
 */

import React, { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Terminal,
  Send,
  Eye,
  ShieldAlert,
  Cpu,
  CheckCircle2,
  AlertCircle,
  Bot,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type MultiplexerState = 'idle' | 'running' | 'waiting_input' | 'blocked' | 'completed' | 'failed';

export interface MultiplexerSessionItem {
  sessionId: string;
  agentType: string;
  taskObjective: string;
  state: MultiplexerState;
  isHeadless: boolean;
  logTail?: string[];
  artifacts?: string[];
  pendingInstructionsCount?: number;
}

export interface AgentMultiplexerPanelProps {
  sessions: MultiplexerSessionItem[];
  selectedSessionId?: string;
  onSelectSession?: (sessionId: string) => void;
  onInstruct?: (sessionId: string, instruction: string) => void | Promise<void>;
  className?: string;
}

const STATE_STYLES: Record<MultiplexerState, { text: string; bg: string; border: string }> = {
  running: { text: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
  blocked: { text: 'text-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
  waiting_input: { text: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
  idle: { text: 'text-neutral-400', bg: 'bg-neutral-500/10', border: 'border-neutral-500/20' },
  completed: { text: 'text-indigo-500', bg: 'bg-indigo-500/10', border: 'border-indigo-500/20' },
  failed: { text: 'text-rose-500', bg: 'bg-rose-500/10', border: 'border-rose-500/20' },
};

export const AgentMultiplexerPanel = memo(function AgentMultiplexerPanel({
  sessions,
  selectedSessionId,
  onSelectSession,
  onInstruct,
  className,
}: AgentMultiplexerPanelProps) {
  const t = useTranslations('chat.multiplexer');
  const [internalSelectedId, setInternalSelectedId] = useState<string>(
    selectedSessionId || (sessions[0]?.sessionId ?? '')
  );
  const [instructionText, setInstructionText] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const activeId = selectedSessionId ?? internalSelectedId;
  const activeSession = sessions.find((s) => s.sessionId === activeId) ?? sessions[0];

  const handleSelect = useCallback(
    (id: string) => {
      setInternalSelectedId(id);
      onSelectSession?.(id);
    },
    [onSelectSession]
  );

  const handleSubmitInstruct = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!instructionText.trim() || !activeSession) {
        return;
      }

      setIsSubmitting(true);
      try {
        await onInstruct?.(activeSession.sessionId, instructionText.trim());
        setInstructionText('');
      } finally {
        setIsSubmitting(false);
      }
    },
    [instructionText, activeSession, onInstruct]
  );

  return (
    <div
      data-testid="agent-multiplexer-panel"
      className={cn(
        'flex flex-col md:flex-row h-full min-h-[460px] w-full rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950 shadow-xs overflow-hidden text-neutral-900 dark:text-neutral-100',
        className
      )}
    >
      {/* Left / Top: Persistent Sessions Pane (tmux style) */}
      <div className="w-full md:w-80 border-b md:border-b-0 md:border-r border-neutral-200 dark:border-neutral-800 flex flex-col shrink-0 bg-neutral-50/50 dark:bg-neutral-900/30">
        <div className="p-3 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-indigo-500" />
            <span className="text-xs font-semibold tracking-wide uppercase text-neutral-600 dark:text-neutral-400">
              {t('sessionListTitle')}
            </span>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-sm bg-neutral-200/60 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400">
            {sessions.length} {t('panesCount')}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-900">
          {sessions.map((sess) => {
            const isSelected = sess.sessionId === activeSession?.sessionId;
            const style = STATE_STYLES[sess.state] || STATE_STYLES.idle;

            return (
              <button
                key={sess.sessionId}
                type="button"
                data-testid={`session-tab-${sess.sessionId}`}
                onClick={() => handleSelect(sess.sessionId)}
                className={cn(
                  'w-full text-left p-3 transition-colors flex flex-col gap-1.5 focus:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset',
                  isSelected
                    ? 'bg-indigo-500/10 border-l-4 border-indigo-500 dark:bg-indigo-950/30'
                    : 'hover:bg-neutral-100/60 dark:hover:bg-neutral-900/60'
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Bot className="w-3.5 h-3.5 shrink-0 text-neutral-500" />
                    <span className="text-xs font-medium truncate">{sess.agentType}</span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {sess.isHeadless && (
                      <span className="text-[10px] px-1 py-0.2 rounded-xs bg-amber-500/15 text-amber-700 dark:text-amber-300 font-mono">
                        {t('headlessBadge')}
                      </span>
                    )}
                    <span
                      className={cn(
                        'text-[10px] px-1.5 py-0.5 rounded-full border font-medium uppercase',
                        style.text,
                        style.bg,
                        style.border
                      )}
                    >
                      {sess.state}
                    </span>
                  </div>
                </div>
                <p className="text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-1">
                  {sess.taskObjective}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Right / Main: Inspect & Instruct Workstation */}
      {activeSession ? (
        <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-neutral-950">
          {/* Header */}
          <div className="p-3 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2 min-w-0">
              <Eye className="w-4 h-4 text-neutral-500 shrink-0" />
              <div className="min-w-0">
                <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 truncate block">
                  {activeSession.agentType} ({activeSession.sessionId})
                </span>
                <span className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate block">
                  {activeSession.taskObjective}
                </span>
              </div>
            </div>
            {activeSession.pendingInstructionsCount ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-500/10 text-indigo-600 border border-indigo-500/20 shrink-0">
                <ShieldAlert className="w-3 h-3" />
                {activeSession.pendingInstructionsCount} {t('pendingDirectives')}
              </span>
            ) : null}
          </div>

          {/* Inspect Terminal View */}
          <div className="flex-1 p-3 overflow-y-auto font-mono text-xs bg-neutral-900 text-neutral-200 dark:bg-black/80 flex flex-col gap-1 select-text">
            <div className="text-neutral-500 text-[10px] pb-1 border-b border-neutral-800 flex items-center gap-1">
              <Terminal className="w-3 h-3" />
              <span>{t('inspectLogTitle')}</span>
            </div>
            {activeSession.logTail && activeSession.logTail.length > 0 ? (
              activeSession.logTail.map((line, idx) => (
                <div key={idx} className="leading-relaxed hover:bg-neutral-800/40 px-1 rounded-xs">
                  <span className="text-neutral-500 select-none mr-2">{idx + 1}</span>
                  {line}
                </div>
              ))
            ) : (
              <div className="text-neutral-600 italic py-4 text-center">{t('noLogs')}</div>
            )}
          </div>

          {/* Artifacts Strip */}
          {activeSession.artifacts && activeSession.artifacts.length > 0 && (
            <div className="px-3 py-2 border-t border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/50 flex items-center gap-2 flex-wrap">
              <span className="text-[11px] font-medium text-neutral-500">{t('artifactsLabel')}:</span>
              {activeSession.artifacts.map((art, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-neutral-200/50 dark:bg-neutral-800 border border-neutral-300/40 dark:border-neutral-700 font-mono"
                >
                  <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                  {art}
                </span>
              ))}
            </div>
          )}

          {/* Instruct Inject Bar */}
          <form
            onSubmit={handleSubmitInstruct}
            className="p-3 border-t border-neutral-200 dark:border-neutral-800 flex items-center gap-2 bg-neutral-50/70 dark:bg-neutral-900/40"
          >
            <input
              type="text"
              data-testid="instruct-input"
              value={instructionText}
              onChange={(e) => setInstructionText(e.target.value)}
              placeholder={t('instructPlaceholder')}
              className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 focus:outline-hidden focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="submit"
              data-testid="instruct-submit-btn"
              disabled={!instructionText.trim() || isSubmitting}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 transition-colors shrink-0"
            >
              <Send className="w-3 h-3" />
              {t('sendInstruction')}
            </button>
          </form>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-neutral-400 gap-2">
          <AlertCircle className="w-8 h-8 opacity-40" />
          <span className="text-xs">{t('noSessions')}</span>
        </div>
      )}
    </div>
  );
});

export default AgentMultiplexerPanel;
