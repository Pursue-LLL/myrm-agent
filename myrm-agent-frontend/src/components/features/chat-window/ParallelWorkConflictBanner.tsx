'use client';

/**
 * [INPUT]: WorkConflictItem[] 列表与对账回调函数 (onResolveConflict)
 * [OUTPUT]: 渲染多 Bot 并行产出冲突对账与合并前拦截门横幅，支持并列对比与四策略对账解决 CTA
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/ParallelWorkConflictBanner.tsx
 */

import React, { useState } from 'react';
import {
  GitMerge,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Check,
  FileCode,
  Sliders,
  CreditCard,
  Layers,
  Ban,
} from 'lucide-react';

export type WriteMutationType = 'file' | 'artifact' | 'config' | 'card';
export type ResolutionStrategy = 'keep_worker_a' | 'keep_worker_b' | 'three_way_merge' | 'abort_both';

export interface WriteFingerprint {
  workerId: string;
  resourceId: string;
  mutationType: WriteMutationType;
  contentHash: string;
  summary?: string;
  timestamp?: string;
}

export interface WorkConflictItem {
  conflictId: string;
  sessionId: string;
  resourceId: string;
  mutationType: WriteMutationType;
  workerA: WriteFingerprint;
  workerB: WriteFingerprint;
  status: 'clean' | 'conflict_pending' | 'resolved';
  resolutionStrategy?: ResolutionStrategy | null;
  resolvedAt?: string | null;
}

export interface ParallelWorkConflictBannerProps {
  conflicts: WorkConflictItem[];
  onResolveConflict?: (conflictId: string, strategy: ResolutionStrategy) => void;
  className?: string;
}

const MUTATION_ICONS: Record<
  WriteMutationType,
  React.ComponentType<{ className?: string }>
> = {
  file: FileCode,
  artifact: Layers,
  config: Sliders,
  card: CreditCard,
};

export function ParallelWorkConflictBanner({
  conflicts,
  onResolveConflict,
  className = '',
}: ParallelWorkConflictBannerProps) {
  const [expandedConflictId, setExpandedConflictId] = useState<string | null>(
    conflicts[0]?.conflictId || null
  );

  const pendingConflicts = conflicts.filter((c) => c.status === 'conflict_pending');

  if (pendingConflicts.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="parallel-work-conflict-banner"
      className={`rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50/90 dark:bg-amber-950/40 p-3.5 shadow-sm space-y-3 ${className}`}
    >
      {/* Banner Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
          <span className="font-semibold text-xs text-amber-900 dark:text-amber-200">
            多 Bot 并行冲突拦截门 (Reconciliation Gate)
          </span>
          <span
            data-testid="conflict-count-badge"
            className="text-[11px] px-2 py-0.5 rounded-full bg-amber-200/80 dark:bg-amber-900/60 text-amber-800 dark:text-amber-300 font-medium"
          >
            {pendingConflicts.length} 处冲突待对账
          </span>
        </div>
        <span className="text-[11px] text-amber-700/80 dark:text-amber-400 font-mono">
          Fail-Closed 拦截自动合并
        </span>
      </div>

      {/* Conflicts List */}
      <div className="space-y-2.5">
        {pendingConflicts.map((conflict) => {
          const isExpanded = expandedConflictId === conflict.conflictId;
          const TypeIcon = MUTATION_ICONS[conflict.mutationType] || FileCode;

          return (
            <div
              key={conflict.conflictId}
              data-testid={`conflict-item-${conflict.conflictId}`}
              className="rounded-md border border-amber-200/80 dark:border-amber-900/50 bg-white/80 dark:bg-zinc-900/80 p-2.5 text-xs shadow-2xs"
            >
              {/* Conflict Item Header */}
              <button
                type="button"
                data-testid={`toggle-conflict-${conflict.conflictId}`}
                onClick={() => setExpandedConflictId(isExpanded ? null : conflict.conflictId)}
                className="w-full flex items-center justify-between text-left cursor-pointer"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <TypeIcon className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                  <span className="font-mono font-semibold text-zinc-800 dark:text-zinc-200 truncate">
                    {conflict.resourceId}
                  </span>
                  <span className="text-[10px] uppercase px-1.5 py-0.2 rounded bg-black/5 dark:bg-white/10 text-zinc-500">
                    {conflict.mutationType}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-zinc-400 shrink-0">
                  <span className="text-[11px]">对账解决</span>
                  {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </div>
              </button>

              {/* Expanded Comparison & Resolution Options */}
              {isExpanded && (
                <div className="mt-2.5 pt-2.5 border-t border-zinc-100 dark:border-zinc-800 space-y-2.5">
                  {/* Side-by-Side Comparison */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {/* Worker A */}
                    <div className="p-2 rounded bg-blue-50/50 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-900/40">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-[11px] text-blue-700 dark:text-blue-400">
                          Worker A: {conflict.workerA.workerId}
                        </span>
                        <span className="font-mono text-[10px] text-zinc-400">
                          {conflict.workerA.contentHash.slice(0, 8)}
                        </span>
                      </div>
                      <p className="text-[11px] text-zinc-600 dark:text-zinc-300 font-mono">
                        {conflict.workerA.summary || '无改动描述'}
                      </p>
                      {onResolveConflict && (
                        <button
                          type="button"
                          data-testid={`btn-keep-a-${conflict.conflictId}`}
                          onClick={() => onResolveConflict(conflict.conflictId, 'keep_worker_a')}
                          className="mt-2 w-full flex items-center justify-center gap-1 text-[11px] py-1 rounded bg-blue-600 text-white hover:bg-blue-700 active:scale-95 transition-all cursor-pointer font-medium"
                        >
                          <Check className="w-3 h-3" />
                          保留 Worker A 版本
                        </button>
                      )}
                    </div>

                    {/* Worker B */}
                    <div className="p-2 rounded bg-purple-50/50 dark:bg-purple-950/30 border border-purple-200/60 dark:border-purple-900/40">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-[11px] text-purple-700 dark:text-purple-400">
                          Worker B: {conflict.workerB.workerId}
                        </span>
                        <span className="font-mono text-[10px] text-zinc-400">
                          {conflict.workerB.contentHash.slice(0, 8)}
                        </span>
                      </div>
                      <p className="text-[11px] text-zinc-600 dark:text-zinc-300 font-mono">
                        {conflict.workerB.summary || '无改动描述'}
                      </p>
                      {onResolveConflict && (
                        <button
                          type="button"
                          data-testid={`btn-keep-b-${conflict.conflictId}`}
                          onClick={() => onResolveConflict(conflict.conflictId, 'keep_worker_b')}
                          className="mt-2 w-full flex items-center justify-center gap-1 text-[11px] py-1 rounded bg-purple-600 text-white hover:bg-purple-700 active:scale-95 transition-all cursor-pointer font-medium"
                        >
                          <Check className="w-3 h-3" />
                          保留 Worker B 版本
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Additional Actions */}
                  {onResolveConflict && (
                    <div className="flex items-center justify-end gap-2 pt-1">
                      <button
                        type="button"
                        data-testid={`btn-merge-${conflict.conflictId}`}
                        onClick={() => onResolveConflict(conflict.conflictId, 'three_way_merge')}
                        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 cursor-pointer"
                      >
                        <GitMerge className="w-3 h-3" />
                        发起三方对账合并
                      </button>
                      <button
                        type="button"
                        data-testid={`btn-abort-${conflict.conflictId}`}
                        onClick={() => onResolveConflict(conflict.conflictId, 'abort_both')}
                        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-rose-200 dark:border-rose-900/60 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-rose-600 dark:text-rose-400 cursor-pointer"
                      >
                        <Ban className="w-3 h-3" />
                        丢弃两方改动
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ParallelWorkConflictBanner;
