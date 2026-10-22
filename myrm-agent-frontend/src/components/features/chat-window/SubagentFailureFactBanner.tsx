'use client';

/**
 * [INPUT]: chatId, fact, onDismiss, onApplyRemediation, className
 * [OUTPUT]: SubagentFailureFactBanner 渲染子智能体脱敏结构化失败事实、单行安全诊断 Header 与确定性自愈建议卡片
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/SubagentFailureFactBanner.tsx
 */

import React, { useState } from 'react';
import {
  AlertOctagon,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  Wrench,
  Clock,
  HardDrive,
  X,
  Sparkles,
} from 'lucide-react';

export type SubagentStage =
  | 'query-start'
  | 'thread-start'
  | 'turn-start'
  | 'turn'
  | 'process'
  | 'teardown';

export type SubagentCategory =
  | 'contextWindowExceeded'
  | 'sessionBudgetExceeded'
  | 'sandboxError'
  | 'error_max_turns'
  | 'rateLimited'
  | 'authError'
  | 'networkTimeout'
  | 'processAborted'
  | 'unknownFailure';

export type RemediationActionType =
  | 'compact_and_resume'
  | 'retry_with_backoff'
  | 'retry_once'
  | 'abort_early'
  | 'escalate_to_user'
  | 'respawn_clean_sandbox'
  | 'synthesize_partial_findings';

export interface StructuredFailureFactItem {
  product: string;
  stage: SubagentStage;
  category: SubagentCategory;
  httpStatus?: number | null;
  exitCode?: number | null;
  signal?: string | null;
  sanitizedMessage: string;
  remediation: RemediationActionType;
  safeDiagnosticHeader: string;
  byteSize: number;
  timestamp?: number;
  metadata?: Record<string, string>;
}

export interface SubagentFailureFactBannerProps {
  chatId: string;
  fact: StructuredFailureFactItem;
  onDismiss?: () => void;
  onApplyRemediation?: (action: RemediationActionType, fact: StructuredFailureFactItem) => void;
  className?: string;
}

const CATEGORY_COLORS: Record<SubagentCategory, { bg: string; text: string; border: string }> = {
  contextWindowExceeded: {
    bg: 'bg-amber-100 dark:bg-amber-950/60',
    text: 'text-amber-800 dark:text-amber-200',
    border: 'border-amber-300 dark:border-amber-800',
  },
  sessionBudgetExceeded: {
    bg: 'bg-rose-100 dark:bg-rose-950/60',
    text: 'text-rose-800 dark:text-rose-200',
    border: 'border-rose-300 dark:border-rose-800',
  },
  sandboxError: {
    bg: 'bg-red-100 dark:bg-red-950/60',
    text: 'text-red-800 dark:text-red-200',
    border: 'border-red-300 dark:border-red-800',
  },
  error_max_turns: {
    bg: 'bg-purple-100 dark:bg-purple-950/60',
    text: 'text-purple-800 dark:text-purple-200',
    border: 'border-purple-300 dark:border-purple-800',
  },
  rateLimited: {
    bg: 'bg-orange-100 dark:bg-orange-950/60',
    text: 'text-orange-800 dark:text-orange-200',
    border: 'border-orange-300 dark:border-orange-800',
  },
  authError: {
    bg: 'bg-pink-100 dark:bg-pink-950/60',
    text: 'text-pink-800 dark:text-pink-200',
    border: 'border-pink-300 dark:border-pink-800',
  },
  networkTimeout: {
    bg: 'bg-blue-100 dark:bg-blue-950/60',
    text: 'text-blue-800 dark:text-blue-200',
    border: 'border-blue-300 dark:border-blue-800',
  },
  processAborted: {
    bg: 'bg-zinc-200 dark:bg-zinc-800',
    text: 'text-zinc-800 dark:text-zinc-200',
    border: 'border-zinc-300 dark:border-zinc-700',
  },
  unknownFailure: {
    bg: 'bg-gray-100 dark:bg-gray-800',
    text: 'text-gray-800 dark:text-gray-200',
    border: 'border-gray-300 dark:border-gray-700',
  },
};

const REMEDIATION_LABELS: Record<RemediationActionType, { label: string; desc: string }> = {
  compact_and_resume: {
    label: 'Compact Context & Resume',
    desc: 'Truncate history & compact intermediate reasoning to recover tokens.',
  },
  retry_with_backoff: {
    label: 'Retry with Backoff',
    desc: 'Cool down and retry with exponential jitter to resolve rate limits.',
  },
  retry_once: {
    label: 'Retry Immediate',
    desc: 'Transient network failure; safe for a single immediate retry.',
  },
  abort_early: {
    label: 'Abort Execution',
    desc: 'Session budget exhausted; stop early to prevent further credit loss.',
  },
  escalate_to_user: {
    label: 'Escalate to User',
    desc: 'Authentication or permission denied; human credentials required.',
  },
  respawn_clean_sandbox: {
    label: 'Respawn Sandbox',
    desc: 'Sandbox crashed or OOM; spin up a clean isolated environment.',
  },
  synthesize_partial_findings: {
    label: 'Synthesize Findings',
    desc: 'Max iterations reached; synthesize available partial findings.',
  },
};

export function SubagentFailureFactBanner({
  chatId,
  fact,
  onDismiss,
  onApplyRemediation,
  className = '',
}: SubagentFailureFactBannerProps) {
  const [copied, setCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const colors = CATEGORY_COLORS[fact.category] || CATEGORY_COLORS.unknownFailure;
  const remInfo = REMEDIATION_LABELS[fact.remediation] || {
    label: fact.remediation,
    desc: 'Follow parent orchestrator policy.',
  };

  const handleCopyHeader = async () => {
    try {
      await navigator.clipboard.writeText(fact.safeDiagnosticHeader);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      setCopied(false);
    }
  };

  return (
    <div
      data-testid="subagent-failure-fact-banner"
      className={`rounded-lg border border-rose-300 dark:border-rose-900/80 bg-rose-50/60 dark:bg-rose-950/30 p-3 text-xs shadow-xs transition-all ${className}`}
    >
      {/* Header Row */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1 font-semibold text-rose-900 dark:text-rose-200">
            <AlertOctagon className="h-4 w-4 text-rose-600 dark:text-rose-400" />
            Structured Subagent Failure Fact
          </span>

          <span
            data-testid="fact-product-badge"
            className="rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-700 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700"
          >
            {fact.product}
          </span>

          <span
            data-testid="fact-stage-badge"
            className="rounded-full bg-zinc-200/80 dark:bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-600 dark:text-zinc-300"
          >
            stage:{fact.stage}
          </span>

          <span
            data-testid="fact-category-badge"
            className={`rounded-full px-2 py-0.5 font-semibold text-[10px] border ${colors.bg} ${colors.text} ${colors.border}`}
          >
            {fact.category}
          </span>

          <span
            data-testid="fact-privacy-badge"
            className="flex items-center gap-1 rounded bg-emerald-100 dark:bg-emerald-950/60 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800"
          >
            <ShieldCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
            Privacy Scrubbed
          </span>

          <span
            data-testid="fact-bytes-badge"
            className="flex items-center gap-0.5 text-[10px] text-zinc-500 dark:text-zinc-400 font-mono"
          >
            <HardDrive className="h-2.5 w-2.5" />
            {fact.byteSize} / 4096 B
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            data-testid="toggle-fact-details-btn"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-0.5 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 px-1 py-0.5"
            aria-label="Toggle details"
          >
            {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          {onDismiss && (
            <button
              type="button"
              data-testid="dismiss-fact-btn"
              onClick={onDismiss}
              className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 p-0.5"
              aria-label="Dismiss banner"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Standard Single-Line Diagnostic Header Strip */}
      <div className="mt-2 flex items-center justify-between gap-2 rounded border border-rose-200 dark:border-rose-900/60 bg-white/80 dark:bg-zinc-900/80 px-2.5 py-1.5">
        <code
          data-testid="safe-diagnostic-header"
          className="font-mono text-[10px] text-rose-950 dark:text-rose-100 truncate select-all"
        >
          {fact.safeDiagnosticHeader}
        </code>
        <button
          type="button"
          data-testid="copy-diagnostic-header-btn"
          onClick={handleCopyHeader}
          className="flex items-center gap-1 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:text-zinc-300 shrink-0 transition-colors"
          title="Copy single-line safe diagnostic header"
        >
          {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>

      {/* Actionable Remediation Guidance Banner */}
      <div
        data-testid="remediation-guidance-card"
        className="mt-2 flex items-center justify-between gap-3 rounded border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/70 dark:bg-indigo-950/30 p-2"
      >
        <div className="flex items-start gap-1.5">
          <Wrench className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold text-indigo-950 dark:text-indigo-200">
              Recommended Self-Healing: {remInfo.label}
            </div>
            <p className="text-[10px] text-zinc-600 dark:text-zinc-400 mt-0.5">
              {remInfo.desc}
            </p>
          </div>
        </div>

        {onApplyRemediation && (
          <button
            type="button"
            data-testid="apply-remediation-btn"
            onClick={() => onApplyRemediation(fact.remediation, fact)}
            className="flex items-center gap-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-2 py-1 text-[11px] shrink-0 shadow-2xs transition-colors"
          >
            <Sparkles className="h-3 w-3" />
            Apply Action
          </button>
        )}
      </div>

      {/* Expanded Scrubbed Details Panel */}
      {isExpanded && (
        <div
          data-testid="expanded-fact-details"
          className="mt-2.5 border-t border-rose-200 dark:border-rose-900/60 pt-2 space-y-1.5"
        >
          <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
            Scrubbed Failure Trace (Secrets & Paths Masked)
          </div>
          <div className="rounded bg-zinc-950 p-2 font-mono text-[10px] text-zinc-200 max-h-40 overflow-y-auto whitespace-pre-wrap leading-relaxed">
            {fact.sanitizedMessage}
          </div>

          {fact.metadata && Object.keys(fact.metadata).length > 0 && (
            <div className="pt-1">
              <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                Sanitized Metadata
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {Object.entries(fact.metadata).map(([k, v]) => (
                  <span
                    key={k}
                    className="rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700"
                  >
                    <strong>{k}</strong>: {v}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-1 text-[9px] text-zinc-400 pt-1">
            <Clock className="h-2.5 w-2.5" />
            Session: {chatId} • Timestamp:{' '}
            {fact.timestamp ? new Date(fact.timestamp * 1000).toLocaleTimeString() : 'N/A'}
          </div>
        </div>
      )}
    </div>
  );
}
