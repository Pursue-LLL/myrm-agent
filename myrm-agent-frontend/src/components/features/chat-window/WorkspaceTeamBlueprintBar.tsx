'use client';

import React, { useState } from 'react';
import {
  FolderGit2,
  Users,
  Repeat,
  CheckCircle2,
  AlertCircle,
  X,
  Trash2,
  Sparkles,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';

export type AutoReusePolicyType = 'always_reuse' | 'prompt_reuse' | 'manual_only';

export interface WorkspaceBlueprintBindingData {
  workspace_id: string;
  blueprint_id: string;
  team_name: string;
  auto_reuse_policy: AutoReusePolicyType;
  bound_at?: string;
  last_used_at?: string;
  member_count: number;
  total_budget_tokens: number;
  project_label?: string;
}

export interface WorkspaceBlueprintResolutionData {
  workspace_id: string;
  binding?: WorkspaceBlueprintBindingData | null;
  can_auto_instantiate: boolean;
  status_label:
    | 'auto_instantiable'
    | 'prompt_candidate'
    | 'manual_only'
    | 'unbound_recommend_recent'
    | 'unbound_no_template';
  resolution_rationale: string;
}

export interface WorkspaceTeamBlueprintBarProps {
  workspaceId: string;
  resolution?: WorkspaceBlueprintResolutionData | null;
  onInstantiateTeam?: (binding: WorkspaceBlueprintBindingData) => void;
  onUnbind?: (workspaceId: string) => void;
  onSavePolicy?: (workspaceId: string, policy: AutoReusePolicyType) => void;
  onDismiss?: () => void;
  className?: string;
}

const POLICY_META: Record<AutoReusePolicyType, { label: string; badgeClass: string }> = {
  always_reuse: {
    label: 'Auto Reuse: Always',
    badgeClass: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  },
  prompt_reuse: {
    label: 'Auto Reuse: Confirm',
    badgeClass: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  },
  manual_only: {
    label: 'Manual Only',
    badgeClass: 'text-muted-foreground bg-muted border-border',
  },
};

export function WorkspaceTeamBlueprintBar({
  workspaceId,
  resolution,
  onInstantiateTeam,
  onUnbind,
  onSavePolicy,
  onDismiss,
  className = '',
}: WorkspaceTeamBlueprintBarProps) {
  const binding = resolution?.binding;
  const isBound = Boolean(binding && resolution?.status_label !== 'unbound_recommend_recent');
  const isRecommended = resolution?.status_label === 'unbound_recommend_recent' && Boolean(binding);

  const [selectedPolicy, setSelectedPolicy] = useState<AutoReusePolicyType>(
    binding?.auto_reuse_policy || 'prompt_reuse',
  );
  const [isEditingPolicy, setIsEditingPolicy] = useState(false);
  const [instantiatedSuccess, setInstantiatedSuccess] = useState(false);

  const handleInstantiate = () => {
    if (binding) {
      onInstantiateTeam?.(binding);
      setInstantiatedSuccess(true);
      setTimeout(() => setInstantiatedSuccess(false), 2500);
    }
  };

  const handlePolicyChange = (policy: AutoReusePolicyType) => {
    setSelectedPolicy(policy);
    onSavePolicy?.(workspaceId, policy);
    setIsEditingPolicy(false);
  };

  return (
    <section
      aria-label="Workspace Team Blueprint Bar"
      className={`relative w-full max-w-xl rounded-xl border border-border bg-card/95 p-4 text-card-foreground shadow-2xl backdrop-blur-md transition-all ${className}`}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-border/60 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FolderGit2 className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-semibold tracking-tight text-foreground">
              Project Team Blueprint
            </h3>
            <p className="text-[11px] text-muted-foreground">
              Workspace: <span className="font-mono text-foreground">{workspaceId}</span>
              {binding?.project_label ? ` • ${binding.project_label}` : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {binding && (
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                POLICY_META[selectedPolicy]?.badgeClass || 'border-border text-foreground'
              }`}
            >
              <Repeat className="h-2.5 w-2.5" />
              {POLICY_META[selectedPolicy]?.label || selectedPolicy}
            </span>
          )}
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              aria-label="Dismiss Blueprint Bar"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Main Content Body */}
      <div className="mt-3">
        {isBound && binding ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border border-border/70 bg-background/50 p-2.5">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-foreground">
                  <Users className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-foreground">{binding.team_name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {binding.member_count} Members • {binding.total_budget_tokens.toLocaleString()} Tokens Budget
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={handleInstantiate}
                  disabled={instantiatedSuccess}
                  className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                >
                  {instantiatedSuccess ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" />
                      Team Reused!
                    </>
                  ) : (
                    <>
                      <ArrowRight className="h-3.5 w-3.5" />
                      Reuse Team
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Rationale explanation */}
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              {resolution?.resolution_rationale}
            </p>

            {/* Secondary Controls: Policy Setting & Unbind */}
            <div className="flex items-center justify-between border-t border-border/40 pt-2 text-xs">
              <div className="flex items-center gap-2">
                {isEditingPolicy ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] text-muted-foreground">Policy:</span>
                    <select
                      aria-label="Select auto-reuse policy"
                      value={selectedPolicy}
                      onChange={(e) => handlePolicyChange(e.target.value as AutoReusePolicyType)}
                      className="rounded border border-input bg-background px-2 py-0.5 text-[11px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      <option value="always_reuse">Always Reuse</option>
                      <option value="prompt_reuse">Confirm on Open</option>
                      <option value="manual_only">Manual Only</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => setIsEditingPolicy(false)}
                      className="text-[11px] text-muted-foreground hover:text-foreground"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setIsEditingPolicy(true)}
                    className="text-[11px] font-medium text-muted-foreground hover:text-foreground underline underline-offset-2"
                  >
                    Configure Policy
                  </button>
                )}
              </div>

              {onUnbind && (
                <button
                  type="button"
                  onClick={() => onUnbind(workspaceId)}
                  className="inline-flex items-center gap-1 text-[11px] text-rose-500 hover:text-rose-600 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Unbind
                </button>
              )}
            </div>
          </div>
        ) : isRecommended && binding ? (
          /* Recommended from recent projects */
          <div className="space-y-2.5 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="flex items-center gap-2 text-amber-500">
              <Sparkles className="h-4 w-4" />
              <span className="text-xs font-semibold">Recommended Team from Previous Workspace</span>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Workspace <span className="font-mono text-foreground">{workspaceId}</span> has no bound team yet. You can automatically adopt{' '}
              <strong className="text-foreground">{binding.team_name}</strong> ({binding.member_count} members) recently used in{' '}
              <span className="font-mono text-foreground">{binding.workspace_id}</span>.
            </p>
            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={handleInstantiate}
                className="inline-flex items-center gap-1 rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-amber-950 transition-colors hover:bg-amber-400"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                Adopt & Reuse Team
              </button>
            </div>
          </div>
        ) : (
          /* Unbound Empty State */
          <div className="flex flex-col items-center justify-center py-5 text-center text-muted-foreground">
            <AlertCircle className="h-6 w-6 text-muted-foreground/60" />
            <p className="mt-1.5 text-xs font-medium text-foreground">No Bound Team Blueprint</p>
            <p className="text-[11px] text-muted-foreground max-w-sm mt-0.5">
              Assemble a squad with El Jefe wizard in this workspace, and it will be remembered for 1-click reuse across future sessions.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

export default WorkspaceTeamBlueprintBar;
