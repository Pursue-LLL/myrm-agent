'use client';

import React, { useState } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  X,
  CheckCircle2,
  Lock,
  Layers,
  Wrench,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export type ScopeViolationType =
  | 'forbidden_tool'
  | 'role_scope_exceeded'
  | 'fanout_limit_exceeded'
  | 'high_risk_require_hitl';

export type ScopeViolationSeverity = 'blocker' | 'warning';

export interface ScopeViolationItem {
  role_key: string;
  tool_name: string;
  violation_type: ScopeViolationType;
  severity: ScopeViolationSeverity;
  recommendation: string;
}

export interface TeamScopeAuditData {
  is_safe: boolean;
  sanitized_tools_map: Record<string, string[]>;
  violations: ScopeViolationItem[];
  fanout_capped: boolean;
  original_member_count: number;
  approved_member_count: number;
  audit_summary: string;
}

export interface SafeTeamDesignGuardrailsCardProps {
  chatId: string;
  audit: TeamScopeAuditData;
  onAdoptSanitized?: (sanitizedTools: Record<string, string[]>) => void;
  onDismiss?: () => void;
  className?: string;
}

export function SafeTeamDesignGuardrailsCard({
  chatId,
  audit,
  onAdoptSanitized,
  onDismiss,
  className = '',
}: SafeTeamDesignGuardrailsCardProps) {
  const [showViolations, setShowViolations] = useState(true);
  const [adoptedSuccess, setAdoptedSuccess] = useState(false);

  const blockers = audit.violations.filter((v) => v.severity === 'blocker');
  const warnings = audit.violations.filter((v) => v.severity === 'warning');

  const handleAdopt = () => {
    onAdoptSanitized?.(audit.sanitized_tools_map);
    setAdoptedSuccess(true);
    setTimeout(() => setAdoptedSuccess(false), 2000);
  };

  return (
    <section
      aria-label="Safe Team Design Guardrails Card"
      className={`relative w-full max-w-lg rounded-xl border border-border bg-card/95 p-4 text-card-foreground shadow-2xl backdrop-blur-md transition-all ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-lg ${
              audit.is_safe
                ? 'bg-emerald-500/10 text-emerald-500'
                : blockers.length > 0
                ? 'bg-rose-500/10 text-rose-500'
                : 'bg-amber-500/10 text-amber-500'
            }`}
          >
            {audit.is_safe ? (
              <ShieldCheck className="h-4 w-4" />
            ) : (
              <ShieldAlert className="h-4 w-4" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-1.5">
              Safe Team Design Guardrails
              {audit.is_safe ? (
                <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-500 border border-emerald-500/20">
                  Safe Mode
                </span>
              ) : (
                <span className="rounded-full bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium text-rose-500 border border-rose-500/20">
                  Guardrails Triggered
                </span>
              )}
            </h3>
            <p className="text-xs text-muted-foreground">
              Session: <span className="font-mono">{chatId.slice(0, 8)}</span> •{' '}
              {audit.approved_member_count} of {audit.original_member_count} Roles Active
            </p>
          </div>
        </div>

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Dismiss Guardrails Card"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Fanout Cap Alert */}
      {audit.fanout_capped && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-700 dark:text-amber-400">
          <Layers className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Fan-Out Cap Enforced: </span>
            <span>
              Requested {audit.original_member_count} subagents; capped to {audit.approved_member_count} roles to prevent system exhaustion.
            </span>
          </div>
        </div>
      )}

      {/* Audit Summary */}
      <div className="mt-3 rounded-md bg-muted/60 p-2.5 text-xs text-foreground leading-relaxed">
        <p className="font-medium text-muted-foreground">Audit Overview:</p>
        <p className="mt-0.5">{audit.audit_summary}</p>
      </div>

      {/* Violations Section */}
      {audit.violations.length > 0 && (
        <div className="mt-3 space-y-2">
          <button
            type="button"
            onClick={() => setShowViolations(!showViolations)}
            className="flex w-full items-center justify-between text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <span>
              Scope Violations ({blockers.length} Blockers, {warnings.length} Warnings)
            </span>
            {showViolations ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>

          {showViolations && (
            <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
              {audit.violations.map((v, i) => (
                <div
                  key={`${v.role_key}-${v.tool_name}-${i}`}
                  className={`rounded-md border p-2 text-xs ${
                    v.severity === 'blocker'
                      ? 'border-rose-500/30 bg-rose-500/5 text-rose-600 dark:text-rose-400'
                      : 'border-amber-500/30 bg-amber-500/5 text-amber-600 dark:text-amber-400'
                  }`}
                >
                  <div className="flex items-center justify-between font-mono text-[11px]">
                    <span className="font-semibold">
                      [{v.role_key}] {v.tool_name}
                    </span>
                    <span className="uppercase text-[9px] font-bold tracking-wider px-1.5 py-0.2 rounded border border-current">
                      {v.severity}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-foreground/80 leading-normal">
                    {v.recommendation}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sanitized Tools Preview */}
      <div className="mt-3 space-y-2">
        <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
          <Wrench className="h-3.5 w-3.5" />
          Sanitized Least-Privilege Tools per Role:
        </p>
        <div className="space-y-1.5 max-h-36 overflow-y-auto rounded-lg border border-border/70 bg-background/50 p-2.5">
          {Object.entries(audit.sanitized_tools_map).map(([role, tools]) => (
            <div key={role} className="text-xs">
              <span className="font-semibold font-mono text-foreground">{role}: </span>
              {tools.length > 0 ? (
                <span className="text-muted-foreground">
                  {tools.join(', ')}
                </span>
              ) : (
                <span className="italic text-muted-foreground/70">No active tools (read-only)</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center justify-end gap-2 border-t border-border/40 pt-3">
        {adoptedSuccess && (
          <span className="text-xs text-emerald-500 flex items-center gap-1 font-medium mr-auto">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Sanitized Tools Adopted!
          </span>
        )}
        <button
          type="button"
          onClick={handleAdopt}
          disabled={adoptedSuccess}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          <Lock className="h-3.5 w-3.5" />
          Adopt Sanitized Tools
        </button>
      </div>
    </section>
  );
}

export default SafeTeamDesignGuardrailsCard;
