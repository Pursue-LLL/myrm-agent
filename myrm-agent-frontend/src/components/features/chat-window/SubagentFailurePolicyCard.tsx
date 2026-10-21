'use client';

import React, { useState } from 'react';
import {
  RotateCcw,
  AlertTriangle,
  RefreshCw,
  FastForward,
  ArrowUpRight,
  ShieldAlert,
  CheckCircle2,
  X,
  Settings2,
  History,
} from 'lucide-react';

export type RemediationActionType =
  | 'restart_fresh'
  | 'redeploy_specs'
  | 'escalate_parent'
  | 'skip';

export type FailureTriggerReasonType =
  | 'crash_error'
  | 'stuck_timeout'
  | 'output_spec_mismatch'
  | 'tool_quota_exhausted';

export interface RolePolicyItem {
  role_key: string;
  primary_action: RemediationActionType;
  allow_failure: boolean;
  max_retries: number;
  fallback_action: RemediationActionType;
  fresh_instructions_template?: string;
  redeploy_model_tier_downgrade?: boolean;
}

export interface RemediationDecisionItem {
  event_id: string;
  task_id: string;
  role_key: string;
  action: RemediationActionType;
  attempt_number: number;
  max_retries: number;
  rationale: string;
  redeploy_payload?: Record<string, string>;
  timestamp?: string;
}

export interface SubagentFailurePolicyCardProps {
  chatId: string;
  policy?: RolePolicyItem;
  latestDecision?: RemediationDecisionItem | null;
  onSavePolicy?: (policy: RolePolicyItem) => void;
  onResetCounter?: (taskId: string) => void;
  onManualEscalate?: (taskId: string, reason: string) => void;
  onDismiss?: () => void;
  className?: string;
}

const ACTION_LABELS: Record<RemediationActionType, { label: string; color: string }> = {
  restart_fresh: { label: 'Restart Fresh', color: 'text-blue-500 bg-blue-500/10 border-blue-500/20' },
  redeploy_specs: { label: 'Redeploy Specs', color: 'text-amber-500 bg-amber-500/10 border-amber-500/20' },
  escalate_parent: { label: 'Escalate Parent', color: 'text-rose-500 bg-rose-500/10 border-rose-500/20' },
  skip: { label: 'Skip Gracefully', color: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20' },
};

export function SubagentFailurePolicyCard({
  chatId,
  policy,
  latestDecision,
  onSavePolicy,
  onResetCounter,
  onManualEscalate,
  onDismiss,
  className = '',
}: SubagentFailurePolicyCardProps) {
  const [activeTab, setActiveTab] = useState<'decision' | 'settings'>('decision');
  const [roleKey, setRoleKey] = useState(policy?.role_key || 'general_worker');
  const [primaryAction, setPrimaryAction] = useState<RemediationActionType>(
    policy?.primary_action || 'restart_fresh',
  );
  const [allowFailure, setAllowFailure] = useState(policy?.allow_failure || false);
  const [maxRetries, setMaxRetries] = useState(policy?.max_retries ?? 2);
  const [fallbackAction, setFallbackAction] = useState<RemediationActionType>(
    policy?.fallback_action || 'escalate_parent',
  );
  const [tierDowngrade, setTierDowngrade] = useState(
    policy?.redeploy_model_tier_downgrade || false,
  );
  const [freshTemplate, setFreshTemplate] = useState(
    policy?.fresh_instructions_template || '',
  );
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSave = () => {
    const updated: RolePolicyItem = {
      role_key: roleKey,
      primary_action: primaryAction,
      allow_failure: allowFailure,
      max_retries: maxRetries,
      fallback_action: fallbackAction,
      fresh_instructions_template: freshTemplate,
      redeploy_model_tier_downgrade: tierDowngrade,
    };
    onSavePolicy?.(updated);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  const isExhausted =
    latestDecision &&
    latestDecision.max_retries > 0 &&
    latestDecision.attempt_number >= latestDecision.max_retries;

  return (
    <section
      aria-label="Subagent Failure Policy Card"
      className={`relative w-full max-w-lg rounded-xl border border-border bg-card/95 p-5 text-card-foreground shadow-2xl backdrop-blur-md transition-all ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-500/10 text-rose-500">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-foreground">
              Subagent Mid-Task Failure Policy
            </h3>
            <p className="text-xs text-muted-foreground">
              Session: <span className="font-mono">{chatId.slice(0, 8)}</span> • Role:{' '}
              <span className="font-medium text-foreground">{roleKey}</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setActiveTab(activeTab === 'decision' ? 'settings' : 'decision')}
            className={`rounded-md p-1.5 text-xs transition-colors ${
              activeTab === 'settings'
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
            aria-label="Toggle Policy Settings"
          >
            <Settings2 className="h-4 w-4" />
          </button>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              aria-label="Dismiss Policy Card"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-3 flex gap-2 border-b border-border/40 pb-2">
        <button
          type="button"
          onClick={() => setActiveTab('decision')}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
            activeTab === 'decision'
              ? 'bg-secondary text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <History className="h-3.5 w-3.5" />
          Active Remediations
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('settings')}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
            activeTab === 'settings'
              ? 'bg-secondary text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <Settings2 className="h-3.5 w-3.5" />
          Declarative Policy
        </button>
      </div>

      {/* Content Area */}
      {activeTab === 'decision' ? (
        <div className="mt-4 space-y-4">
          {latestDecision ? (
            <div className="space-y-3 rounded-lg border border-border/80 bg-background/50 p-3.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-muted-foreground">
                  Task: {latestDecision.task_id}
                </span>
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                    ACTION_LABELS[latestDecision.action]?.color ||
                    'border-border text-foreground'
                  }`}
                >
                  {ACTION_LABELS[latestDecision.action]?.label || latestDecision.action}
                </span>
              </div>

              {/* Retry attempt indicator */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Retry Attempts:</span>
                  <span
                    className={`font-semibold ${
                      isExhausted ? 'text-rose-500' : 'text-foreground'
                    }`}
                  >
                    {latestDecision.attempt_number} / {latestDecision.max_retries}
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className={`h-full transition-all duration-300 ${
                      isExhausted ? 'bg-rose-500' : 'bg-primary'
                    }`}
                    style={{
                      width: `${Math.min(
                        100,
                        (latestDecision.attempt_number / Math.max(1, latestDecision.max_retries)) * 100,
                      )}%`,
                    }}
                  />
                </div>
              </div>

              {/* Rationale explanation */}
              <div className="rounded-md bg-muted/60 p-2.5 text-xs text-foreground">
                <p className="font-medium text-muted-foreground">Remediation Rationale:</p>
                <p className="mt-0.5 text-xs leading-relaxed">{latestDecision.rationale}</p>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2 pt-1">
                {onResetCounter && (
                  <button
                    type="button"
                    onClick={() => onResetCounter(latestDecision.task_id)}
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-secondary"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Reset Counter
                  </button>
                )}
                {onManualEscalate && (
                  <button
                    type="button"
                    onClick={() =>
                      onManualEscalate(
                        latestDecision.task_id,
                        'Manual intervention requested from UI',
                      )
                    }
                    className="inline-flex items-center gap-1 rounded-md bg-rose-500/10 border border-rose-500/20 px-2.5 py-1 text-xs font-medium text-rose-500 transition-colors hover:bg-rose-500/20"
                  >
                    <ArrowUpRight className="h-3 w-3" />
                    Manual Escalate
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-6 text-center text-muted-foreground">
              <CheckCircle2 className="h-8 w-8 text-emerald-500/70" />
              <p className="mt-2 text-xs font-medium text-foreground">All Subagents Running Normally</p>
              <p className="text-xs text-muted-foreground">
                No mid-task failures or retries currently recorded in this session.
              </p>
            </div>
          )}
        </div>
      ) : (
        /* Declarative Settings Form */
        <div className="mt-4 space-y-3.5 text-xs">
          <div>
            <label htmlFor="role-key-input" className="block font-medium text-foreground mb-1">
              Role Key:
            </label>
            <input
              id="role-key-input"
              type="text"
              value={roleKey}
              onChange={(e) => setRoleKey(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="primary-action-select" className="block font-medium text-foreground mb-1">
                Primary Action:
              </label>
              <select
                id="primary-action-select"
                value={primaryAction}
                onChange={(e) => setPrimaryAction(e.target.value as RemediationActionType)}
                className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="restart_fresh">Restart Fresh</option>
                <option value="redeploy_specs">Redeploy Specs</option>
                <option value="escalate_parent">Escalate Parent</option>
                <option value="skip">Skip Gracefully</option>
              </select>
            </div>

            <div>
              <label htmlFor="max-retries-input" className="block font-medium text-foreground mb-1">
                Max Retries:
              </label>
              <input
                id="max-retries-input"
                type="number"
                min={0}
                max={10}
                value={maxRetries}
                onChange={(e) => setMaxRetries(Number(e.target.value))}
                className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          </div>

          <div className="flex items-center justify-between rounded-md border border-border/60 bg-background/50 px-3 py-2">
            <div>
              <p className="font-medium text-foreground">Allow Non-fatal Failure (Skip)</p>
              <p className="text-[11px] text-muted-foreground">Permit task to complete even if worker fails</p>
            </div>
            <input
              type="checkbox"
              checked={allowFailure}
              onChange={(e) => setAllowFailure(e.target.checked)}
              className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
            />
          </div>

          <div className="flex items-center justify-between rounded-md border border-border/60 bg-background/50 px-3 py-2">
            <div>
              <p className="font-medium text-foreground">Model Tier Downgrade</p>
              <p className="text-[11px] text-muted-foreground">Downgrade tier on spec redeploy</p>
            </div>
            <input
              type="checkbox"
              checked={tierDowngrade}
              onChange={(e) => setTierDowngrade(e.target.checked)}
              className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
            />
          </div>

          <div>
            <label htmlFor="fresh-prompt-template" className="block font-medium text-foreground mb-1">
              Fresh Restart Prompt Template (Optional):
            </label>
            <textarea
              id="fresh-prompt-template"
              rows={2}
              value={freshTemplate}
              onChange={(e) => setFreshTemplate(e.target.value)}
              placeholder="e.g. Previous attempt hit error: {{error}}. Please strictly adhere to schema."
              className="w-full rounded-md border border-input bg-background p-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            {savedSuccess && (
              <span className="text-xs text-emerald-500 flex items-center gap-1 font-medium">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Policy Saved
              </span>
            )}
            <button
              type="button"
              onClick={handleSave}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Save Policy
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export default SubagentFailurePolicyCard;
