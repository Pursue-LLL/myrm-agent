'use client';

/**
 * [INPUT]: Roster overview 数据、选中的 subagent transcript、控制回调函数 (onSteer, onKill, onRevive, onClose)
 * [OUTPUT]: 渲染 Agent Hub 子代理实时监管抽屉 (Alt+A 快捷键唤起)，支持 Roster 概览、单 Worker Live Transcript 与 Steer/Kill/Revive 动作
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/subagent/AgentHubSupervisionDrawer.tsx
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Play,
  Pause,
  AlertOctagon,
  CheckCircle,
  XCircle,
  RefreshCw,
  Send,
  Zap,
  Clock,
  Coins,
  Bot,
  Activity,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export type SubagentWorkerStatus =
  | 'running'
  | 'parked'
  | 'stuck'
  | 'done'
  | 'failed'
  | 'interrupted';

export interface SupervisionWorkerItem {
  taskId: string;
  agentType: string;
  status: SubagentWorkerStatus;
  currentActivity: string;
  model: string;
  tokensUsed: number;
  elapsedSeconds: number;
  lastTool: string;
  canSteer: boolean;
  canKill: boolean;
  canRevive: boolean;
  description?: string;
  createdAt?: string;
}

export interface SupervisionTranscriptEntry {
  entryId: string;
  timestamp: string;
  toolName: string;
  inputSummary: string;
  outputSummary: string;
  level: 'info' | 'warn' | 'error';
  durationMs?: number;
}

export interface SupervisionRosterOverview {
  sessionId: string;
  totalWorkers: number;
  activeWorkers: number;
  parkedWorkers: number;
  stuckWorkers: number;
  totalTokens: number;
  totalDurationSeconds: number;
  workers: SupervisionWorkerItem[];
}

export interface AgentHubSupervisionDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  roster: SupervisionRosterOverview;
  transcriptEntries?: SupervisionTranscriptEntry[];
  selectedTaskId?: string;
  onSelectWorker?: (taskId: string) => void;
  onSteerWorker?: (taskId: string, message: string) => void;
  onKillWorker?: (taskId: string) => void;
  onReviveWorker?: (taskId: string) => void;
  onRefresh?: () => void;
  className?: string;
}

const STATUS_BADGES: Record<
  SubagentWorkerStatus,
  { label: string; bg: string; text: string; icon: React.ComponentType<{ className?: string }> }
> = {
  running: {
    label: '运行中',
    bg: 'bg-emerald-500/10 dark:bg-emerald-400/20',
    text: 'text-emerald-600 dark:text-emerald-400',
    icon: Play,
  },
  parked: {
    label: '已停靠',
    bg: 'bg-amber-500/10 dark:bg-amber-400/20',
    text: 'text-amber-600 dark:text-amber-400',
    icon: Pause,
  },
  stuck: {
    label: '挂死/超时',
    bg: 'bg-rose-500/10 dark:bg-rose-400/20',
    text: 'text-rose-600 dark:text-rose-400 animate-pulse',
    icon: AlertOctagon,
  },
  done: {
    label: '已完成',
    bg: 'bg-blue-500/10 dark:bg-blue-400/20',
    text: 'text-blue-600 dark:text-blue-400',
    icon: CheckCircle,
  },
  failed: {
    label: '已失败',
    bg: 'bg-zinc-500/10 dark:bg-zinc-400/20',
    text: 'text-zinc-600 dark:text-zinc-400',
    icon: XCircle,
  },
  interrupted: {
    label: '已中断',
    bg: 'bg-purple-500/10 dark:bg-purple-400/20',
    text: 'text-purple-600 dark:text-purple-400',
    icon: Pause,
  },
};

export function AgentHubSupervisionDrawer({
  isOpen,
  onClose,
  roster,
  transcriptEntries = [],
  selectedTaskId,
  onSelectWorker,
  onSteerWorker,
  onKillWorker,
  onReviveWorker,
  onRefresh,
  className = '',
}: AgentHubSupervisionDrawerProps) {
  const [activeTaskId, setActiveTaskId] = useState<string | null>(
    selectedTaskId ?? (roster.workers[0]?.taskId || null)
  );
  const [steerInput, setSteerInput] = useState('');
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);

  // Sync active task if selectedTaskId changes externally
  useEffect(() => {
    if (selectedTaskId) {
      setActiveTaskId(selectedTaskId);
    } else if (!activeTaskId && roster.workers.length > 0) {
      setActiveTaskId(roster.workers[0].taskId);
    }
  }, [selectedTaskId, roster.workers, activeTaskId]);

  const handleSelect = useCallback(
    (taskId: string) => {
      setActiveTaskId(taskId);
      onSelectWorker?.(taskId);
    },
    [onSelectWorker]
  );

  const handleSendSteer = useCallback(() => {
    if (!activeTaskId || !steerInput.trim() || !onSteerWorker) {
      return;
    }
    onSteerWorker(activeTaskId, steerInput.trim());
    setSteerInput('');
  }, [activeTaskId, steerInput, onSteerWorker]);

  if (!isOpen) {
    return null;
  }

  const currentWorker = roster.workers.find((w) => w.taskId === activeTaskId);

  return (
    <div
      data-testid="agent-hub-drawer"
      className={`fixed inset-y-0 right-0 z-50 w-full max-w-2xl bg-white dark:bg-zinc-900 border-l border-zinc-200 dark:border-zinc-800 shadow-2xl flex flex-col transition-all duration-200 ${className}`}
    >
      {/* Drawer Header */}
      <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-800 shrink-0">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Agent Hub 子代理监管抽屉
          </h2>
          <span className="text-xs px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 font-mono">
            Alt+A
          </span>
        </div>
        <div className="flex items-center gap-2">
          {onRefresh && (
            <button
              type="button"
              data-testid="refresh-btn"
              onClick={onRefresh}
              className="p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors"
              title="刷新花名册"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
          <button
            type="button"
            data-testid="close-drawer-btn"
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Roster Metrics Strip */}
      <div
        data-testid="roster-metrics-strip"
        className="px-4 py-2.5 bg-zinc-50 dark:bg-zinc-950/60 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-3 text-xs shrink-0 flex-wrap"
      >
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-zinc-700 dark:text-zinc-300 font-medium">
            <Activity className="w-3.5 h-3.5 text-zinc-400" />
            共 {roster.totalWorkers} 个 Worker
          </span>
          <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium">
            运行中 {roster.activeWorkers}
          </span>
          {roster.stuckWorkers > 0 && (
            <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-600 dark:text-rose-400 font-medium">
              挂死 {roster.stuckWorkers}
            </span>
          )}
          {roster.parkedWorkers > 0 && (
            <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium">
              停靠 {roster.parkedWorkers}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 text-zinc-500 dark:text-zinc-400">
          <span className="flex items-center gap-1">
            <Coins className="w-3.5 h-3.5" />
            {roster.totalTokens.toLocaleString()} tokens
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {roster.totalDurationSeconds}s
          </span>
        </div>
      </div>

      {/* Main Content: Split into Left Roster List & Right Detail Panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Worker Roster List */}
        <div
          data-testid="worker-roster-list"
          className="w-1/2 border-r border-zinc-200 dark:border-zinc-800 overflow-y-auto p-3 space-y-2"
        >
          {roster.workers.length === 0 ? (
            <div className="p-4 text-center text-xs text-zinc-400">暂无并发 Subagent 任务</div>
          ) : (
            roster.workers.map((w) => {
              const badge = STATUS_BADGES[w.status];
              const BadgeIcon = badge.icon;
              const isSelected = w.taskId === activeTaskId;

              return (
                <button
                  type="button"
                  key={w.taskId}
                  data-testid={`worker-card-${w.taskId}`}
                  onClick={() => handleSelect(w.taskId)}
                  className={`w-full text-left p-3 rounded-lg border text-xs cursor-pointer transition-all ${
                    isSelected
                      ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/30'
                      : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700 bg-white dark:bg-zinc-900'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-semibold text-zinc-800 dark:text-zinc-200">
                      {w.agentType}
                    </span>
                    <span
                      className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] ${badge.bg} ${badge.text}`}
                    >
                      <BadgeIcon className="w-3 h-3" />
                      {badge.label}
                    </span>
                  </div>

                  <p className="text-zinc-600 dark:text-zinc-400 line-clamp-2 mb-2 font-mono text-[11px]">
                    {w.currentActivity || '执行中...'}
                  </p>

                  <div className="flex items-center justify-between text-[11px] text-zinc-400">
                    <span className="truncate max-w-[120px]">{w.model}</span>
                    <span>{w.tokensUsed} tokens</span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Worker Live Transcript & Control Actions Panel */}
        <div className="w-1/2 flex flex-col overflow-hidden bg-zinc-50/50 dark:bg-zinc-950/40">
          {currentWorker ? (
            <>
              {/* Target Worker Header & Control Bar */}
              <div className="p-3 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shrink-0">
                <div className="flex items-center justify-between mb-2">
                  <div className="truncate">
                    <span className="font-semibold text-sm text-zinc-900 dark:text-zinc-100">
                      {currentWorker.agentType}
                    </span>
                    <span className="text-xs text-zinc-400 ml-1.5 font-mono">
                      #{currentWorker.taskId.slice(-6)}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {currentWorker.canKill && onKillWorker && (
                      <button
                        type="button"
                        data-testid="kill-worker-btn"
                        onClick={() => onKillWorker(currentWorker.taskId)}
                        className="text-xs px-2 py-1 rounded bg-rose-50 text-rose-600 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-400 border border-rose-200 dark:border-rose-900 font-medium cursor-pointer"
                        title="单点终止卡死 Worker，不中断主会话"
                      >
                        Kill
                      </button>
                    )}
                    {currentWorker.canRevive && onReviveWorker && (
                      <button
                        type="button"
                        data-testid="revive-worker-btn"
                        onClick={() => onReviveWorker(currentWorker.taskId)}
                        className="text-xs px-2 py-1 rounded bg-emerald-50 text-emerald-600 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900 font-medium cursor-pointer"
                        title="从检查点恢复 Worker"
                      >
                        Revive
                      </button>
                    )}
                  </div>
                </div>

                {/* Steering Injector */}
                {currentWorker.canSteer && onSteerWorker && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <input
                      type="text"
                      data-testid="steer-input"
                      value={steerInput}
                      onChange={(e) => setSteerInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendSteer()}
                      placeholder="输入纠偏指令 (Steering)..."
                      className="flex-1 text-xs px-2.5 py-1.5 rounded border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      type="button"
                      data-testid="send-steer-btn"
                      onClick={handleSendSteer}
                      className="p-1.5 rounded bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer transition-colors"
                      title="注入纠偏指令"
                    >
                      <Send className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>

              {/* Live Transcript Stream List */}
              <div
                data-testid="live-transcript-stream"
                className="flex-1 overflow-y-auto p-3 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between text-[11px] text-zinc-400 pb-1 border-b border-zinc-200 dark:border-zinc-800">
                  <span>实时执行轨迹 (Live Transcript)</span>
                  <span>{transcriptEntries.length} 条</span>
                </div>

                {transcriptEntries.length === 0 ? (
                  <div className="py-8 text-center text-zinc-400 text-xs">
                    暂无执行轨迹，正在等待工具调用...
                  </div>
                ) : (
                  transcriptEntries.map((trace) => {
                    const isExpanded = expandedTraceId === trace.entryId;
                    return (
                      <div
                        key={trace.entryId}
                        data-testid={`trace-entry-${trace.entryId}`}
                        className="p-2.5 rounded border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900"
                      >
                        <button
                          type="button"
                          className="w-full text-left flex items-center justify-between cursor-pointer"
                          onClick={() => setExpandedTraceId(isExpanded ? null : trace.entryId)}
                        >
                          <div className="flex items-center gap-1.5 font-mono font-medium text-zinc-800 dark:text-zinc-200 truncate">
                            <Zap className="w-3 h-3 text-amber-500 shrink-0" />
                            <span>{trace.toolName}</span>
                          </div>
                          <div className="flex items-center gap-1 text-[11px] text-zinc-400">
                            {trace.durationMs ? `${trace.durationMs}ms` : ''}
                            {isExpanded ? (
                              <ChevronUp className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5" />
                            )}
                          </div>
                        </button>

                        {/* Input summary */}
                        <div className="mt-1 text-zinc-600 dark:text-zinc-400 font-mono text-[11px] truncate">
                          入参: {trace.inputSummary}
                        </div>

                        {/* Expanded details */}
                        {isExpanded && (
                          <div className="mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800 text-[11px] space-y-1">
                            <div className="text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap font-mono max-h-36 overflow-y-auto bg-zinc-50 dark:bg-zinc-950 p-1.5 rounded">
                              {trace.outputSummary}
                            </div>
                            <div className="text-[10px] text-zinc-400">时间: {trace.timestamp}</div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-zinc-400 p-4">
              请从左侧花名册选择一个 Worker 查看实时监管详情
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AgentHubSupervisionDrawer;
