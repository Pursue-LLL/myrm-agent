'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  Coins,
  Compass,
  AlertTriangle,
  RotateCcw,
  PlusCircle,
  Activity,
  Code2,
} from 'lucide-react';

export type ConsumptionCategory = 'routing_overhead' | 'execution_payload';
export type NudgeSeverity = 'info' | 'warning' | 'critical';

export interface RoleBudgetSpecData {
  role_name: string;
  token_ceiling: number;
  stop_condition: string;
  allow_overflow: boolean;
}

export interface DoctorNudgeAlertData {
  alert_id: string;
  severity: NudgeSeverity;
  message: string;
  handoff_count: number;
  routing_ratio: number;
  suggested_action: string;
  created_at: number;
}

export interface SharedTokenBudgetSnapshotData {
  session_id: string;
  primary_model: string;
  shared_token_ceiling: number;
  total_tokens_spent: number;
  routing_tokens_spent: number;
  execution_tokens_spent: number;
  routing_ratio: number;
  role_budgets: Record<string, RoleBudgetSpecData>;
  role_usage: Record<string, number>;
  active_alerts: DoctorNudgeAlertData[];
}

export interface SharedTokenBudgetGovernanceCardProps {
  chatId?: string;
  initialSnapshot?: SharedTokenBudgetSnapshotData | null;
  onDismiss?: () => void;
}

function createFallbackSnapshot(chatId: string): SharedTokenBudgetSnapshotData {
  return {
    session_id: chatId,
    primary_model: 'claude-3-5-sonnet',
    shared_token_ceiling: 100000,
    total_tokens_spent: 0,
    routing_tokens_spent: 0,
    execution_tokens_spent: 0,
    routing_ratio: 0.0,
    role_budgets: {
      orchestrator: {
        role_name: 'orchestrator',
        token_ceiling: 20000,
        stop_condition: 'halt_and_report',
        allow_overflow: false,
      },
      coder: {
        role_name: 'coder',
        token_ceiling: 50000,
        stop_condition: 'halt_and_report',
        allow_overflow: false,
      },
    },
    role_usage: {
      orchestrator: 0,
      coder: 0,
    },
    active_alerts: [],
  };
}

export function SharedTokenBudgetGovernanceCard({
  chatId = 'default-chat-session',
  initialSnapshot = null,
  onDismiss,
}: SharedTokenBudgetGovernanceCardProps) {
  const [snapshot, setSnapshot] = useState<SharedTokenBudgetSnapshotData>(() => {
    return initialSnapshot || createFallbackSnapshot(chatId);
  });
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    if (initialSnapshot) {
      setSnapshot(initialSnapshot);
    }
  }, [initialSnapshot]);

  const handleRecordConsumption = useCallback((category: ConsumptionCategory, tokens: number) => {
    setSnapshot((prev) => {
      const isRouting = category === 'routing_overhead';
      const newRouting = prev.routing_tokens_spent + (isRouting ? tokens : 0);
      const newExecution = prev.execution_tokens_spent + (!isRouting ? tokens : 0);
      const newTotal = prev.total_tokens_spent + tokens;
      const newRatio = newTotal > 0 ? Number((newRouting / newTotal).toFixed(4)) : 0;

      const newAlerts = [...prev.active_alerts];
      if (newTotal >= 2000 && newRatio > 0.35) {
        if (!newAlerts.some((a) => a.alert_id.startsWith('alert-routing-'))) {
          newAlerts.push({
            alert_id: `alert-routing-${Date.now()}`,
            severity: 'warning',
            message: `Routing overhead consumes ${(newRatio * 100).toFixed(1)}% of total tokens, exceeding 35% ceiling.`,
            handoff_count: isRouting ? 1 : 0,
            routing_ratio: newRatio,
            suggested_action: 'Consolidate routing prompts or bypass intermediate delegators.',
            created_at: Date.now() / 1000,
          });
        }
      }

      return {
        ...prev,
        total_tokens_spent: newTotal,
        routing_tokens_spent: newRouting,
        execution_tokens_spent: newExecution,
        routing_ratio: newRatio,
        active_alerts: newAlerts,
      };
    });

    setStatusMessage(
      `Recorded ${tokens} tokens for '${category}'. Ledger updated.`
    );
  }, []);

  const handleSimulateHandoffChurn = useCallback(() => {
    setSnapshot((prev) => {
      const addedTokens = 1200;
      const newRouting = prev.routing_tokens_spent + addedTokens;
      const newTotal = prev.total_tokens_spent + addedTokens;
      const newRatio = newTotal > 0 ? Number((newRouting / newTotal).toFixed(4)) : 0;

      const handoffAlert: DoctorNudgeAlertData = {
        alert_id: `alert-handoff-${Date.now()}`,
        severity: 'critical',
        message: 'Repetitive agent handoffs detected (5 >= 5). Subagents are bouncing tasks without execution payload.',
        handoff_count: 5,
        routing_ratio: newRatio,
        suggested_action: 'Halt delegation loop and lock primary model directly to specialist.',
        created_at: Date.now() / 1000,
      };

      return {
        ...prev,
        total_tokens_spent: newTotal,
        routing_tokens_spent: newRouting,
        routing_ratio: newRatio,
        active_alerts: [handoffAlert, ...prev.active_alerts],
      };
    });

    setStatusMessage('Doctor Nudge triggered: 5x repetitive handoff loop intercepted!');
  }, []);

  const handleSimulatePrecheckFailure = useCallback(() => {
    setStatusMessage(
      'Precheck Blocked (Fail-Closed): Requested 25,000 tokens exceeds remaining per-role ceiling for orchestrator (halt_and_report).'
    );
  }, []);

  const handleReset = useCallback(() => {
    setSnapshot(createFallbackSnapshot(chatId));
    setStatusMessage('Token budget governor reset.');
  }, [chatId]);

  return (
    <dialog
      open
      className="relative flex flex-col w-full max-w-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-lg p-5 text-zinc-900 dark:text-zinc-100 z-50 overflow-hidden"
      data-testid="token-budget-governance-card"
    >
      <div className="flex items-center justify-between pb-3 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center space-x-2">
          <Coins className="w-5 h-5 text-amber-500" />
          <h3 className="font-semibold text-base">One-Model Shared Token Budget Governance</h3>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss dialog"
            className="text-xs px-2.5 py-1 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 transition-colors"
          >
            Dismiss
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 my-4">
        <div className="flex flex-col p-3 rounded-lg bg-amber-50/60 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-800/50">
          <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
            Total Tokens Spent
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-total-tokens">
            {snapshot.total_tokens_spent.toLocaleString()}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-cyan-50/60 dark:bg-cyan-950/30 border border-cyan-200/60 dark:border-cyan-800/50">
          <span className="text-xs text-cyan-600 dark:text-cyan-400 font-medium">
            Routing Overhead %
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-routing-ratio">
            {(snapshot.routing_ratio * 100).toFixed(1)}%
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200/60 dark:border-rose-800/50">
          <span className="text-xs text-rose-600 dark:text-rose-400 font-medium">
            Doctor Nudges
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-doctor-nudges">
            {snapshot.active_alerts.length}
          </span>
        </div>
      </div>

      <div className="p-3 mb-4 rounded-lg bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-800">
        <div className="flex justify-between text-xs text-zinc-500 mb-1.5 font-medium">
          <span>Routing: {snapshot.routing_tokens_spent.toLocaleString()}</span>
          <span>Execution: {snapshot.execution_tokens_spent.toLocaleString()}</span>
        </div>
        <div className="w-full bg-zinc-200 dark:bg-zinc-700 h-2 rounded-full overflow-hidden flex">
          <div
            className="bg-cyan-500 h-full transition-all duration-300"
            style={{ width: `${Math.min(100, snapshot.routing_ratio * 100)}%` }}
            title="Routing Overhead"
          />
          <div
            className="bg-emerald-500 h-full transition-all duration-300 flex-1"
            title="Execution Payload"
          />
        </div>
      </div>

      {statusMessage && (
        <output
          className="text-xs p-2.5 rounded-lg mb-3 flex items-center space-x-2 border bg-zinc-100 dark:bg-zinc-800/60 border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300"
          data-testid="status-message"
        >
          <Activity className="w-4 h-4 text-amber-500 shrink-0" />
          <span>{statusMessage}</span>
        </output>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <button
          onClick={() => handleRecordConsumption('routing_overhead', 1200)}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-cyan-600 hover:bg-cyan-700 text-white font-medium transition-colors"
          data-testid="btn-record-routing"
        >
          <Compass className="w-3.5 h-3.5" />
          <span>+ Routing Tokens</span>
        </button>
        <button
          onClick={() => handleRecordConsumption('execution_payload', 2500)}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
          data-testid="btn-record-execution"
        >
          <Code2 className="w-3.5 h-3.5" />
          <span>+ Execution Tokens</span>
        </button>
        <button
          onClick={handleSimulateHandoffChurn}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-rose-600 hover:bg-rose-700 text-white font-medium transition-colors"
          data-testid="btn-simulate-handoffs"
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>5x Handoff Churn</span>
        </button>
        <button
          onClick={handleSimulatePrecheckFailure}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-amber-600 hover:bg-amber-700 text-white font-medium transition-colors"
          data-testid="btn-simulate-precheck"
        >
          <PlusCircle className="w-3.5 h-3.5" />
          <span>Precheck Fan-Out</span>
        </button>
        <button
          onClick={handleReset}
          className="flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded-md bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 font-medium transition-colors"
          data-testid="btn-reset"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset</span>
        </button>
      </div>

      <div className="space-y-2 mb-2 max-h-40 overflow-y-auto">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          Active Doctor Nudges ({snapshot.active_alerts.length})
        </span>
        {snapshot.active_alerts.length === 0 ? (
          <div className="text-xs text-zinc-400 py-2 text-center" data-testid="empty-alerts">
            No active budget alerts. Token routing health optimal.
          </div>
        ) : (
          <div className="space-y-1.5" data-testid="alerts-list">
            {snapshot.active_alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className={`p-2.5 rounded-md border text-xs ${
                  alert.severity === 'critical'
                    ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-300 dark:border-rose-800 text-rose-800 dark:text-rose-200'
                    : 'bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-200'
                }`}
                data-testid={`alert-item-${alert.alert_id}`}
              >
                <div className="flex items-center justify-between font-semibold mb-1">
                  <span>[{alert.severity.toUpperCase()}] Handoffs: {alert.handoff_count}</span>
                  <span>Routing: {(alert.routing_ratio * 100).toFixed(1)}%</span>
                </div>
                <div className="mb-1">{alert.message}</div>
                <div className="text-[11px] opacity-80">
                  Recommendation: {alert.suggested_action}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </dialog>
  );
}
