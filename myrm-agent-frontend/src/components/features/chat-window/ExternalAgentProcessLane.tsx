'use client';

/**
 * [INPUT]: agentConfig (ExternalAgentConfigData), receipts (ProcessReceiptData[]), onExecute, onDismiss, className
 * [OUTPUT]: ExternalAgentProcessLane: 多源异构 Agent 外部进程桥接与 CLI 标准化执行通道
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/ExternalAgentProcessLane.tsx
 */

import React, { useState } from 'react';
import {
  Terminal,
  Play,
  Clock,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  X,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Hash,
} from 'lucide-react';

export type ExternalAgentKind = 'claude-code' | 'codex-cli' | 'openclaw' | 'generic-stdio';

export type ProcessLaneStatus =
  | 'idle'
  | 'spawning'
  | 'running'
  | 'completed'
  | 'failed'
  | 'timed_out'
  | 'terminated';

export interface ExternalAgentConfigData {
  agent_id: string;
  name: string;
  kind: ExternalAgentKind;
  command: string;
  args?: string[];
  cwd?: string | null;
  max_turns?: number;
  timeout_seconds?: number;
  expected_model?: string | null;
}

export interface ProcessReceiptData {
  execution_id: string;
  agent_id: string;
  kind: ExternalAgentKind;
  status: ProcessLaneStatus;
  exit_code: number | null;
  duration_ms: number;
  stdout_summary: string;
  stderr_summary: string;
  receipt_hash: string;
  created_at?: number;
}

interface ExternalAgentProcessLaneProps {
  config: ExternalAgentConfigData;
  receipts?: ProcessReceiptData[];
  onExecute?: (inputText: string) => void;
  onDismiss?: () => void;
  className?: string;
}

export function ExternalAgentProcessLane({
  config,
  receipts = [],
  onExecute,
  onDismiss,
  className = '',
}: ExternalAgentProcessLaneProps): React.ReactElement {
  const [isExpanded, setIsExpanded] = useState(true);
  const [inputText, setInputText] = useState('');
  const [activeReceiptId, setActiveReceiptId] = useState<string | null>(
    receipts.length > 0 ? receipts[receipts.length - 1].execution_id : null
  );

  const latestReceipt = receipts.length > 0 ? receipts[receipts.length - 1] : null;
  const currentStatus: ProcessLaneStatus = latestReceipt ? latestReceipt.status : 'idle';

  const handleRun = () => {
    if (!inputText.trim()) {
      return;
    }
    onExecute?.(inputText.trim());
    setInputText('');
  };

  const getStatusBadge = (status: ProcessLaneStatus) => {
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" /> Completed
          </span>
        );
      case 'failed':
      case 'timed_out':
      case 'terminated':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-500/10 text-red-500 border border-red-500/20">
            <AlertTriangle className="w-3 h-3" /> {status}
          </span>
        );
      case 'running':
      case 'spawning':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20 animate-pulse">
            <Clock className="w-3 h-3" /> {status}
          </span>
        );
      case 'idle':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-secondary text-muted-foreground border border-border">
            Idle
          </span>
        );
    }
  };

  const selectedReceipt = receipts.find((r) => r.execution_id === activeReceiptId) || latestReceipt;

  return (
    <section
      aria-label="External Agent CLI Process Lane"
      className={`rounded-xl border border-border/60 bg-card text-card-foreground shadow-lg overflow-hidden transition-all ${className}`}
    >
      {/* Lane Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border/40">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Terminal className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold tracking-tight">{config.name}</span>
              <span className="text-xs px-1.5 py-0.5 rounded bg-muted font-mono text-muted-foreground border border-border/50">
                {config.kind}
              </span>
            </div>
            <p className="text-xs text-muted-foreground font-mono truncate max-w-xs">
              {config.command} {(config.args || []).join(' ')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {getStatusBadge(currentStatus)}
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded-md text-muted-foreground hover:bg-muted transition-colors"
            aria-label={isExpanded ? 'Collapse lane' : 'Expand lane'}
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="p-1 rounded-md text-muted-foreground hover:bg-muted transition-colors"
              aria-label="Close process lane"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Metadata bar */}
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground bg-muted/20 p-2 rounded-lg border border-border/40">
            {config.expected_model && (
              <span className="flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-primary" /> Model: {config.expected_model}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" /> Timeout: {config.timeout_seconds ?? 60}s
            </span>
            <span className="flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" /> Verifiable Receipts: SHA-256
            </span>
          </div>

          {/* Quick Execution Dispatch */}
          <div className="flex gap-2">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleRun()}
              placeholder="Dispatch instruction or input to CLI agent..."
              className="flex-1 text-xs px-3 py-2 rounded-lg bg-background border border-border focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button
              type="button"
              onClick={handleRun}
              disabled={!inputText.trim() || currentStatus === 'running'}
              className="px-3 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium flex items-center gap-1.5 hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5" /> Run
            </button>
          </div>

          {/* Execution History & Verifiable Receipt View */}
          {receipts.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
                <span>Execution Receipts ({receipts.length})</span>
                {receipts.length > 1 && (
                  <select
                    value={activeReceiptId || ''}
                    onChange={(e) => setActiveReceiptId(e.target.value)}
                    className="text-xs bg-background border border-border rounded px-2 py-0.5"
                    aria-label="Select execution receipt"
                  >
                    {receipts.map((r, idx) => (
                      <option key={r.execution_id} value={r.execution_id}>
                        #{idx + 1} [{r.status}] {r.execution_id} ({r.duration_ms}ms)
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {selectedReceipt && (
                <div className="rounded-lg border border-border/60 bg-muted/10 p-3 text-xs space-y-2">
                  <div className="flex items-center justify-between font-mono text-[11px] text-muted-foreground pb-2 border-b border-border/40">
                    <span className="flex items-center gap-1">
                      <Hash className="w-3 h-3 text-primary" /> {selectedReceipt.execution_id}
                    </span>
                    <span>
                      Exit: {selectedReceipt.exit_code ?? 'None'} · Duration: {selectedReceipt.duration_ms}ms
                    </span>
                  </div>

                  {/* Sanitized stdout */}
                  {selectedReceipt.stdout_summary ? (
                    <div>
                      <div className="text-[10px] uppercase font-semibold text-muted-foreground mb-1">
                        Standard Output
                      </div>
                      <pre className="font-mono text-xs bg-muted/40 p-2 rounded-md overflow-x-auto max-h-32 whitespace-pre-wrap">
                        {selectedReceipt.stdout_summary}
                      </pre>
                    </div>
                  ) : null}

                  {/* Sanitized stderr */}
                  {selectedReceipt.stderr_summary ? (
                    <div>
                      <div className="text-[10px] uppercase font-semibold text-red-400 mb-1">
                        Standard Error
                      </div>
                      <pre className="font-mono text-xs bg-red-500/10 text-red-400 p-2 rounded-md overflow-x-auto max-h-24 whitespace-pre-wrap">
                        {selectedReceipt.stderr_summary}
                      </pre>
                    </div>
                  ) : null}

                  {/* Cryptographic Receipt Hash */}
                  <div className="pt-1 flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                    <span className="flex items-center gap-1">
                      <ShieldCheck className="w-3 h-3 text-emerald-500" /> Receipt Hash:
                    </span>
                    <span className="truncate max-w-[240px] text-foreground/80">
                      {selectedReceipt.receipt_hash}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default ExternalAgentProcessLane;
