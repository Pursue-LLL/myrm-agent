'use client';

/**
 * [INPUT]: dispatchId, targetPeerId, coordinatorPrincipal, prestartPassed, evidenceCount, totalEvidenceBytes, journalEntries, onResumeRecovery
 * [OUTPUT]: 渲染 Hermes Fabric 确定性远程分发与持久化对等日志横幅，展示协调器鉴权、执行前策略重校验、有界证据准入水位、对等日志链与幂等恢复
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/RemoteDispatchDurableJournalBanner.tsx
 */

import React, { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Server,
  FileText,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  Activity,
  Layers,
  Clock,
  Database,
} from 'lucide-react';

export interface JournalEntryItem {
  journalId: string;
  seq: number;
  entryType: string;
  timestamp: number;
  payloadHash: string;
  metadata?: Record<string, string>;
}

export interface RemoteDispatchDurableJournalBannerProps {
  dispatchId: string;
  targetPeerId: string;
  coordinatorPrincipal?: string;
  prestartPassed?: boolean;
  evidenceCount?: number;
  totalEvidenceBytes?: number;
  maxEvidenceBytes?: number;
  journalEntries?: JournalEntryItem[];
  canResume?: boolean;
  onResumeRecovery?: (dispatchId: string) => void;
  className?: string;
}

export function RemoteDispatchDurableJournalBanner({
  dispatchId,
  targetPeerId,
  coordinatorPrincipal = 'coord_primary',
  prestartPassed = true,
  evidenceCount = 0,
  totalEvidenceBytes = 0,
  maxEvidenceBytes = 1048576, // 1MB bound
  journalEntries = [],
  canResume = false,
  onResumeRecovery,
  className = '',
}: RemoteDispatchDurableJournalBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const evidenceUsagePercent = Math.min(
    100,
    Math.round((totalEvidenceBytes / maxEvidenceBytes) * 100),
  );

  return (
    <div
      data-testid="remote-dispatch-durable-journal-banner"
      className={`rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 p-3 text-xs shadow-xs transition-all ${className}`}
    >
      {/* Top Banner Row */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1 font-semibold text-zinc-900 dark:text-zinc-100">
            <Layers className="h-4 w-4 text-indigo-500" />
            Fabric Remote Dispatch
          </span>
          <span
            data-testid="dispatch-id-badge"
            className="rounded bg-indigo-50 dark:bg-indigo-950/40 px-1.5 py-0.5 font-mono text-[11px] text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
          >
            {dispatchId}
          </span>
          <span
            data-testid="peer-target-badge"
            className="flex items-center gap-1 rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-600 dark:text-zinc-300"
          >
            <Server className="h-3 w-3" />
            {targetPeerId}
          </span>
        </div>

        {/* Right Action & Status Controls */}
        <div className="flex items-center gap-2">
          {/* Pre-start Status */}
          {prestartPassed ? (
            <span
              data-testid="prestart-status-badge"
              className="flex items-center gap-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 font-medium text-[10px] text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
            >
              <ShieldCheck className="h-3 w-3" /> Pre-start Validated
            </span>
          ) : (
            <span
              data-testid="prestart-status-badge"
              className="flex items-center gap-0.5 rounded-full bg-rose-50 dark:bg-rose-950/40 px-2 py-0.5 font-medium text-[10px] text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
            >
              <ShieldAlert className="h-3 w-3" /> Policy Fail-Closed
            </span>
          )}

          {/* Idempotent Resume CTA */}
          {canResume && onResumeRecovery && (
            <button
              type="button"
              data-testid="resume-recovery-btn"
              onClick={() => onResumeRecovery(dispatchId)}
              className="flex items-center gap-1 rounded bg-amber-600 hover:bg-amber-700 text-white font-medium px-2 py-0.5 text-[11px] transition-colors"
            >
              <RotateCcw className="h-3 w-3" /> Idempotent Resume
            </button>
          )}

          {/* Expand Toggle */}
          <button
            type="button"
            data-testid="toggle-journal-btn"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-0.5 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
            aria-label="Toggle journal details"
          >
            {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="mt-2.5 flex items-center justify-between border-t border-zinc-100 dark:border-zinc-800/80 pt-2 text-[11px] text-zinc-500 dark:text-zinc-400 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <Activity className="h-3 w-3 text-zinc-400" />
            Principal: <strong className="text-zinc-700 dark:text-zinc-300 font-mono">{coordinatorPrincipal}</strong>
          </span>
          <span className="flex items-center gap-1">
            <FileText className="h-3 w-3 text-zinc-400" />
            Admitted Evidence: <strong className="text-zinc-700 dark:text-zinc-300">{evidenceCount}</strong>
          </span>
          <span className="flex items-center gap-1">
            <Database className="h-3 w-3 text-zinc-400" />
            Journal Seq: <strong className="text-zinc-700 dark:text-zinc-300 font-mono">{journalEntries.length}</strong>
          </span>
        </div>

        {/* Evidence Watermark */}
        <div className="flex items-center gap-1.5 min-w-[120px]">
          <span className="text-[10px]">Evidence Bounds:</span>
          <div className="h-1.5 w-16 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
            <div
              className={`h-full transition-all ${
                evidenceUsagePercent > 80 ? 'bg-rose-500' : 'bg-indigo-500'
              }`}
              style={{ width: `${evidenceUsagePercent}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-zinc-600 dark:text-zinc-400">
            {evidenceUsagePercent}%
          </span>
        </div>
      </div>

      {/* Expanded Journal Ledger */}
      {isExpanded && (
        <div
          data-testid="expanded-journal-section"
          className="mt-3 border-t border-zinc-200 dark:border-zinc-800 pt-2.5 space-y-2"
        >
          <div className="flex items-center justify-between text-[11px] font-semibold text-zinc-600 dark:text-zinc-400 uppercase tracking-wider">
            <span>Durable Journal Ledger ({journalEntries.length})</span>
            <span className="text-[10px] font-normal lowercase text-zinc-400">SHA-256 tamper-proofed</span>
          </div>

          {journalEntries.length === 0 ? (
            <div className="rounded border border-dashed border-zinc-200 dark:border-zinc-800 p-2 text-center text-[11px] text-zinc-400">
              No journal records committed for this dispatch.
            </div>
          ) : (
            <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
              {journalEntries.map((entry) => (
                <div
                  key={entry.journalId}
                  data-testid={`journal-entry-${entry.seq}`}
                  className="flex items-center justify-between rounded border border-zinc-100 dark:border-zinc-800/60 bg-zinc-50/60 dark:bg-zinc-900/40 px-2 py-1.5 text-[11px]"
                >
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-zinc-200 dark:bg-zinc-800 px-1 py-0.2 font-mono text-[10px] font-bold text-zinc-700 dark:text-zinc-300">
                      #{entry.seq}
                    </span>
                    <span className="font-medium text-zinc-800 dark:text-zinc-200">
                      {entry.entryType}
                    </span>
                    <span className="font-mono text-[10px] text-zinc-400">
                      {entry.payloadHash.slice(0, 10)}...
                    </span>
                  </div>
                  <span className="flex items-center gap-0.5 text-[10px] text-zinc-400 font-mono">
                    <Clock className="h-2.5 w-2.5" />
                    {new Date(entry.timestamp * 1000).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
