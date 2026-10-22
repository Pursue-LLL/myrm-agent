'use client';

/**
 * [INPUT]: chatId, instances, items, onDrainBatch, onRefreshStatus, className
 * [OUTPUT]: 渲染 Subagent Report-before-Settlement 严格保序 FIFO 队列与 Active Report Wakeup Feed 组件
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/OrderedReportSettlementFeed.tsx
 */

import React, { useState } from 'react';
import {
  ListOrdered,
  BellRing,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
  Users,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Clock,
  Shield,
  FileCheck2,
  Sparkles,
} from 'lucide-react';

export interface NamedSubagentInstanceConfigItem {
  instanceName: string;
  role: string;
  modelName?: string;
  permissionMode: 'never' | 'approve-for-me' | 'dangerously-bypass-approvals-and-sandbox';
  reportDelivery: 'quiet' | 'next-step';
  toolsAllowed?: string[];
}

export interface SubagentReportPayload {
  reportId: string;
  subagentId: string;
  taskId: string;
  summary: string;
  content?: string;
  deliveryMode: string;
  severity?: 'normal' | 'critical';
  timestamp: number;
}

export interface SettlementNoticePayload {
  settlementId: string;
  subagentId: string;
  taskId: string;
  exitCode: number;
  status: string;
  summary: string;
  timestamp: number;
}

export interface FifoQueueEnvelopeItem {
  sequenceId: number;
  itemType: 'report' | 'settlement';
  taskId: string;
  subagentId: string;
  wakesParent: boolean;
  urgentInterrupt?: boolean;
  timestamp: number;
  reportPayload?: SubagentReportPayload;
  settlementPayload?: SettlementNoticePayload;
}

export interface OrderedReportSettlementFeedProps {
  chatId: string;
  instances?: NamedSubagentInstanceConfigItem[];
  items?: FifoQueueEnvelopeItem[];
  urgentInterrupt?: boolean;
  summaryRollup?: string;
  onDrainBatch?: (maxItems: number) => void;
  onRefreshStatus?: () => void;
  className?: string;
}

export function OrderedReportSettlementFeed({
  chatId,
  instances = [],
  items = [],
  urgentInterrupt = false,
  summaryRollup = '',
  onDrainBatch,
  onRefreshStatus,
  className = '',
}: OrderedReportSettlementFeedProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showInstances, setShowInstances] = useState(false);

  const pendingReports = items.filter((i) => i.itemType === 'report').length;
  const pendingSettlements = items.filter((i) => i.itemType === 'settlement').length;
  const hasUrgentItem = urgentInterrupt || items.some((i) => Boolean(i.urgentInterrupt));

  return (
    <div
      data-testid="ordered-report-settlement-feed"
      className={`rounded-lg border ${
        hasUrgentItem
          ? 'border-rose-400 dark:border-rose-700 bg-rose-50/30 dark:bg-rose-950/20'
          : 'border-zinc-200 dark:border-zinc-800 bg-white/90 dark:bg-zinc-900/90'
      } p-3 text-xs shadow-xs transition-all ${className}`}
    >
      {/* Top Banner Row */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1 font-semibold text-zinc-900 dark:text-zinc-100">
            <ListOrdered className="h-4 w-4 text-emerald-500" />
            Report-before-Settlement FIFO
          </span>
          <span
            data-testid="feed-chat-badge"
            className="rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 font-mono text-[11px] text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700"
          >
            {chatId}
          </span>
          <span
            data-testid="pending-items-badge"
            className="rounded-full bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
          >
            Pending: {items.length} ({pendingReports} rep / {pendingSettlements} stl)
          </span>
          {hasUrgentItem && (
            <span
              data-testid="urgent-interrupt-badge"
              className="flex items-center gap-1 rounded bg-rose-600 text-white px-2 py-0.5 text-[10px] font-bold shadow-xs animate-pulse"
            >
              <AlertTriangle className="h-3 w-3" />
              URGENT INTERRUPT
            </span>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {onRefreshStatus && (
            <button
              type="button"
              data-testid="refresh-status-btn"
              onClick={onRefreshStatus}
              className="flex items-center gap-1 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 px-2 py-0.5 text-[11px] text-zinc-700 dark:text-zinc-300 transition-colors"
            >
              <RefreshCw className="h-3 w-3" /> Refresh
            </button>
          )}

          {onDrainBatch && (
            <button
              type="button"
              data-testid="drain-batch-btn"
              onClick={() => onDrainBatch(50)}
              className="flex items-center gap-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-2 py-0.5 text-[11px] transition-colors"
            >
              <PlayCircle className="h-3 w-3" /> Drain Step Batch
            </button>
          )}

          <button
            type="button"
            data-testid="toggle-instances-btn"
            onClick={() => setShowInstances(!showInstances)}
            className="flex items-center gap-0.5 rounded border border-zinc-200 dark:border-zinc-800 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800"
          >
            <Users className="h-3 w-3" /> Instances ({instances.length})
          </button>

          <button
            type="button"
            data-testid="toggle-feed-btn"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-0.5 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
            aria-label="Toggle feed details"
          >
            {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Aggregated Natural-Language Summary Rollup Panel */}
      {summaryRollup && (
        <div
          data-testid="summary-rollup-panel"
          className="mt-2.5 rounded border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/50 dark:bg-indigo-950/20 p-2 text-[11px] space-y-1"
        >
          <div className="flex items-center gap-1.5 font-semibold text-indigo-900 dark:text-indigo-200">
            <Sparkles className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
            <span>Aggregated Step Rollup Summary</span>
          </div>
          <p className="font-mono text-[10px] text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
            {summaryRollup}
          </p>
        </div>
      )}

      {/* Subagent Instances Roster Section */}
      {showInstances && (
        <div
          data-testid="subagents-roster-section"
          className="mt-3 border-t border-zinc-200 dark:border-zinc-800 pt-2.5 space-y-2"
        >
          <div className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-400 uppercase tracking-wider">
            Registered Subagent Instances ({instances.length})
          </div>
          {instances.length === 0 ? (
            <div className="rounded border border-dashed border-zinc-200 dark:border-zinc-800 p-2 text-center text-[11px] text-zinc-400">
              No named instances registered for this session.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {instances.map((inst) => (
                <div
                  key={inst.instanceName}
                  data-testid={`instance-card-${inst.instanceName}`}
                  className="rounded border border-zinc-100 dark:border-zinc-800/80 bg-zinc-50/70 dark:bg-zinc-900/50 p-2 text-[11px] space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-zinc-800 dark:text-zinc-200 font-mono">
                      {inst.instanceName}
                    </span>
                    <span className="rounded bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.2 text-[10px] text-zinc-600 dark:text-zinc-400">
                      {inst.role}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-zinc-500 dark:text-zinc-400">
                    <span className="flex items-center gap-0.5">
                      <Shield className="h-2.5 w-2.5" />
                      Mode: <strong className="text-zinc-700 dark:text-zinc-300 font-mono">{inst.permissionMode}</strong>
                    </span>
                    <span className="flex items-center gap-0.5">
                      <BellRing className="h-2.5 w-2.5" />
                      Delivery: <strong className="text-zinc-700 dark:text-zinc-300 font-mono">{inst.reportDelivery}</strong>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Expanded Ordered Queue Stream */}
      {isExpanded && (
        <div
          data-testid="ordered-queue-section"
          className="mt-3 border-t border-zinc-200 dark:border-zinc-800 pt-2.5 space-y-2"
        >
          <div className="flex items-center justify-between text-[11px] font-semibold text-zinc-600 dark:text-zinc-400 uppercase tracking-wider">
            <span>Ordered FIFO Queue Pipeline ({items.length})</span>
            <span className="text-[10px] font-normal lowercase text-zinc-400">Report-before-Settlement Enforced</span>
          </div>

          {items.length === 0 ? (
            <div className="rounded border border-dashed border-zinc-200 dark:border-zinc-800 p-2 text-center text-[11px] text-zinc-400">
              Queue is empty. All subagent reports and settlements have been drained.
            </div>
          ) : (
            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {items.map((envelope) => {
                const isReport = envelope.itemType === 'report';
                const isUrgent = Boolean(envelope.urgentInterrupt);
                return (
                  <div
                    key={envelope.sequenceId}
                    data-testid={`queue-envelope-${envelope.sequenceId}`}
                    className={`rounded border p-2 text-[11px] transition-all ${
                      isUrgent
                        ? 'border-rose-400 dark:border-rose-800/80 bg-rose-50/50 dark:bg-rose-950/30'
                        : isReport
                        ? 'border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/20'
                        : 'border-purple-200 dark:border-purple-900/60 bg-purple-50/40 dark:bg-purple-950/20'
                    }`}
                  >
                    {/* Header Row */}
                    <div className="flex items-center justify-between gap-1 flex-wrap">
                      <div className="flex items-center gap-1.5">
                        <span className="rounded bg-zinc-200 dark:bg-zinc-800 px-1 py-0.2 font-mono text-[10px] font-bold text-zinc-700 dark:text-zinc-300">
                          #{envelope.sequenceId}
                        </span>
                        <span
                          className={`font-semibold uppercase text-[10px] px-1 rounded ${
                            isUrgent
                              ? 'bg-rose-200 dark:bg-rose-900 text-rose-900 dark:text-rose-100 font-bold'
                              : isReport
                              ? 'bg-emerald-100 dark:bg-emerald-900 text-emerald-800 dark:text-emerald-200'
                              : 'bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200'
                          }`}
                        >
                          {envelope.itemType}
                        </span>
                        {isUrgent && (
                          <span
                            data-testid={`urgent-item-badge-${envelope.sequenceId}`}
                            className="flex items-center gap-0.5 rounded bg-rose-600 text-white font-bold text-[9px] px-1 py-0.2 shadow-2xs"
                          >
                            <AlertTriangle className="h-2.5 w-2.5" />
                            URGENT
                          </span>
                        )}
                        <span className="font-mono text-[10px] text-zinc-500">
                          {envelope.subagentId}
                        </span>
                        <span className="font-mono text-[10px] text-zinc-400">
                          task:{envelope.taskId}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Parent Wakeup Badge */}
                        {envelope.wakesParent ? (
                          <span
                            data-testid={`wakeup-badge-${envelope.sequenceId}`}
                            className="flex items-center gap-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/80 px-1.5 py-0.2 font-medium text-[9px] text-emerald-800 dark:text-emerald-200"
                          >
                            <BellRing className="h-2.5 w-2.5 text-emerald-600 dark:text-emerald-400" />
                            Next-Step Wakeup
                          </span>
                        ) : (
                          <span
                            data-testid={`wakeup-badge-${envelope.sequenceId}`}
                            className="rounded-full bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.2 text-[9px] text-zinc-500"
                          >
                            Quiet
                          </span>
                        )}

                        <span className="flex items-center gap-0.5 text-[10px] text-zinc-400 font-mono">
                          <Clock className="h-2.5 w-2.5" />
                          {new Date(envelope.timestamp * 1000).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>

                    {/* Body Summary */}
                    <div className="mt-1 text-zinc-700 dark:text-zinc-300">
                      {isReport && envelope.reportPayload ? (
                        <div className="flex items-start gap-1">
                          <FileCheck2 className="h-3.5 w-3.5 text-emerald-600 shrink-0 mt-0.5" />
                          <div>
                            <p className="font-medium">{envelope.reportPayload.summary}</p>
                            {envelope.reportPayload.content && (
                              <p className="text-[10px] text-zinc-500 dark:text-zinc-400 line-clamp-2 mt-0.5">
                                {envelope.reportPayload.content}
                              </p>
                            )}
                          </div>
                        </div>
                      ) : !isReport && envelope.settlementPayload ? (
                        <div className="flex items-start gap-1">
                          {envelope.settlementPayload.exitCode === 0 ? (
                            <CheckCircle2 className="h-3.5 w-3.5 text-purple-600 shrink-0 mt-0.5" />
                          ) : (
                            <AlertTriangle className="h-3.5 w-3.5 text-rose-500 shrink-0 mt-0.5" />
                          )}
                          <div>
                            <p className="font-medium">
                              {envelope.settlementPayload.summary ||
                                `Settlement status: ${envelope.settlementPayload.status} (exit ${envelope.settlementPayload.exitCode})`}
                            </p>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
