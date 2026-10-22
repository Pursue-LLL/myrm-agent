'use client';

/**
 * [INPUT]: isOpen, onClose, sessionId, roster, onResolveCapability, onClearErrors
 * [OUTPUT]: 渲染 Agent-Owned 多智能体协同操作体系抽屉，展示 List-form 花名册、Agent 专属 Provider/Allowlist、隔离错误栈与能力解析探针
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/AgentOwnedOperationsDrawer.tsx
 */

import React, { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Bot,
  Cpu,
  Layers,
  AlertTriangle,
  X,
  Trash2,
  CheckCircle2,
  XCircle,
  Search,
} from 'lucide-react';

export interface AgentScopedErrorItem {
  errorId: string;
  operation: string;
  errorType: string;
  message: string;
  fatal: boolean;
  timestamp?: number;
}

export interface AgentRosterEntryItem {
  agentId: string;
  role: string;
  parentAgentId?: string | null;
  providerModel: string;
  capabilities: string[];
  allowlist: string[];
  errorCount: number;
  isHealthy: boolean;
  errorStack?: AgentScopedErrorItem[];
}

export interface AgentOwnedOperationsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId?: string;
  roster?: AgentRosterEntryItem[];
  onResolveCapability?: (agentId: string, capability: string) => Promise<boolean> | boolean;
  onClearErrors?: (agentId: string) => void;
  className?: string;
}

export function AgentOwnedOperationsDrawer({
  isOpen,
  onClose,
  sessionId = '',
  roster = [],
  onResolveCapability,
  onClearErrors,
  className = '',
}: AgentOwnedOperationsDrawerProps) {
  const [selectedAgentId, setSelectedAgentId] = useState<string>(
    roster.length > 0 ? roster[0].agentId : '',
  );
  const [probeCapability, setProbeCapability] = useState<string>('');
  const [probeResult, setProbeResult] = useState<boolean | null>(null);

  if (!isOpen) {
    return null;
  }

  const activeAgent = roster.find((a) => a.agentId === selectedAgentId) || roster[0] || null;

  const handleTestProbe = async () => {
    if (!activeAgent || !probeCapability.trim()) {
      return;
    }
    if (onResolveCapability) {
      const allowed = await onResolveCapability(activeAgent.agentId, probeCapability.trim());
      setProbeResult(allowed);
    } else {
      // Default local fallback resolver
      const isAllowed =
        activeAgent.allowlist.includes('*') ||
        activeAgent.allowlist.includes(probeCapability.trim()) ||
        (activeAgent.allowlist.length === 0 &&
          activeAgent.capabilities.includes(probeCapability.trim()));
      setProbeResult(isAllowed);
    }
  };

  return (
    <div
      data-testid="agent-owned-operations-drawer"
      className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white dark:bg-zinc-900 border-l border-zinc-200 dark:border-zinc-800 shadow-2xl transition-transform ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 p-3.5">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Agent-Owned Operations Fabric
          </h2>
        </div>
        <button
          type="button"
          data-testid="close-drawer-btn"
          onClick={onClose}
          className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800 dark:text-zinc-400"
          aria-label="Close drawer"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Subheader info banner */}
      <div className="bg-emerald-50/60 dark:bg-emerald-950/20 px-3.5 py-2 border-b border-emerald-100 dark:border-emerald-900/30 text-[11px] text-emerald-800 dark:text-emerald-300 flex items-center justify-between">
        <span className="flex items-center gap-1">
          <ShieldCheck className="h-3.5 w-3.5" />
          All providers, capabilities & error stacks are strictly agent-owned.
        </span>
        {sessionId && <span className="opacity-75 font-mono">session: {sessionId}</span>}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
        {/* Roster List-Form Selector */}
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block">
            List-Form Agent Roster ({roster.length})
          </label>
          {roster.length === 0 ? (
            <div
              data-testid="empty-roster-msg"
              className="rounded border border-dashed border-zinc-200 dark:border-zinc-800 p-4 text-center text-xs text-zinc-500"
            >
              No active worker agents in current session fabric.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-1.5">
              {roster.map((agent) => {
                const isSelected = activeAgent?.agentId === agent.agentId;
                return (
                  <button
                    key={agent.agentId}
                    type="button"
                    data-testid={`roster-item-${agent.agentId}`}
                    onClick={() => {
                      setSelectedAgentId(agent.agentId);
                      setProbeResult(null);
                    }}
                    className={`flex items-center justify-between rounded-lg border p-2.5 text-left text-xs transition-all ${
                      isSelected
                        ? 'border-emerald-500 bg-emerald-50/30 dark:border-emerald-500/70 dark:bg-emerald-950/30'
                        : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-800">
                        <Bot className="h-3.5 w-3.5 text-zinc-600 dark:text-zinc-400" />
                      </div>
                      <div>
                        <div className="font-medium text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                          {agent.agentId}
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">
                            {agent.role}
                          </span>
                        </div>
                        <div className="text-[10px] text-zinc-500 dark:text-zinc-400 font-mono">
                          {agent.providerModel}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {agent.isHealthy ? (
                        <span className="flex items-center gap-0.5 text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
                          <CheckCircle2 className="h-3 w-3" /> Healthy
                        </span>
                      ) : (
                        <span className="flex items-center gap-0.5 text-[10px] text-rose-600 dark:text-rose-400 font-medium">
                          <ShieldAlert className="h-3 w-3" /> {agent.errorCount} Err
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Active Agent Details */}
        {activeAgent && (
          <div className="space-y-3.5 border-t border-zinc-200 dark:border-zinc-800 pt-3">
            {/* Provider and Role */}
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3 bg-zinc-50/50 dark:bg-zinc-900/50 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-zinc-800 dark:text-zinc-200 flex items-center gap-1">
                  <Cpu className="h-3.5 w-3.5 text-indigo-500" /> Owned Provider Setup
                </span>
                <span className="font-mono text-[11px] text-zinc-600 dark:text-zinc-400 bg-white dark:bg-zinc-800 px-2 py-0.5 rounded border border-zinc-200 dark:border-zinc-700">
                  {activeAgent.providerModel}
                </span>
              </div>

              {/* Allowlist & Capabilities */}
              <div className="space-y-1.5 pt-1">
                <div className="text-[10px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase">
                  Agent Allowlist ({activeAgent.allowlist.length})
                </div>
                <div className="flex flex-wrap gap-1">
                  {activeAgent.allowlist.length > 0 ? (
                    activeAgent.allowlist.map((item) => (
                      <span
                        key={item}
                        className="rounded bg-zinc-200/60 dark:bg-zinc-800 px-1.5 py-0.5 text-[10px] font-mono text-zinc-700 dark:text-zinc-300"
                      >
                        {item}
                      </span>
                    ))
                  ) : (
                    <span className="text-[11px] text-zinc-400 italic">No explicit allowlist</span>
                  )}
                </div>
              </div>
            </div>

            {/* Capability Resolver Probe */}
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3 space-y-2">
              <label
                htmlFor="probe-input"
                className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 block"
              >
                Capability Target Resolver Probe
              </label>
              <div className="flex items-center gap-1.5">
                <input
                  id="probe-input"
                  type="text"
                  data-testid="probe-input"
                  placeholder="e.g. tool_fs_write"
                  value={probeCapability}
                  onChange={(e) => {
                    setProbeCapability(e.target.value);
                    setProbeResult(null);
                  }}
                  className="flex-1 rounded border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-2 py-1 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-hidden focus:ring-1 focus:ring-emerald-500"
                />
                <button
                  type="button"
                  data-testid="probe-test-btn"
                  onClick={handleTestProbe}
                  className="rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700 flex items-center gap-1"
                >
                  <Search className="h-3 w-3" /> Test
                </button>
              </div>
              {probeResult !== null && (
                <div
                  data-testid="probe-verdict"
                  className={`flex items-center gap-1 text-[11px] font-medium p-1.5 rounded ${
                    probeResult
                      ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300'
                      : 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300'
                  }`}
                >
                  {probeResult ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5" /> Capability permitted under agent allowlist
                    </>
                  ) : (
                    <>
                      <XCircle className="h-3.5 w-3.5" /> Disallowed: Target not in agent allowlist
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Isolated Error Stack */}
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 flex items-center gap-1">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                  Isolated Error Stack ({activeAgent.errorStack?.length ?? activeAgent.errorCount})
                </span>
                {onClearErrors && (activeAgent.errorStack?.length ?? 0) > 0 && (
                  <button
                    type="button"
                    data-testid="clear-errors-btn"
                    onClick={() => onClearErrors(activeAgent.agentId)}
                    className="text-[10px] text-zinc-500 hover:text-rose-600 dark:hover:text-rose-400 flex items-center gap-0.5"
                  >
                    <Trash2 className="h-3 w-3" /> Clear
                  </button>
                )}
              </div>

              {(!activeAgent.errorStack || activeAgent.errorStack.length === 0) ? (
                <div
                  data-testid="no-errors-msg"
                  className="text-xs text-zinc-500 py-2 text-center border border-dashed border-zinc-200 dark:border-zinc-800 rounded"
                >
                  No isolated errors. Agent stack is healthy.
                </div>
              ) : (
                <div className="space-y-1.5 max-h-40 overflow-y-auto">
                  {activeAgent.errorStack.map((err) => (
                    <div
                      key={err.errorId}
                      data-testid={`error-item-${err.errorId}`}
                      className="rounded border border-rose-200 dark:border-rose-900/50 bg-rose-50/50 dark:bg-rose-950/20 p-2 text-xs space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-rose-800 dark:text-rose-300 font-mono text-[10px]">
                          {err.errorType} in {err.operation}
                        </span>
                        {err.fatal && (
                          <span className="rounded bg-rose-600 px-1 py-0.2 text-[9px] font-bold text-white uppercase">
                            Fatal
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-zinc-700 dark:text-zinc-300 break-words">
                        {err.message}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
