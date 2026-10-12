'use client';

/**
 * [INPUT]
 * @/services/memory/ruleCascade::PreFilterEvidenceRequestDTO, PreFilteredEvidenceResponseDTO,
 *   DeterministicRuleEntryDTO, EvidencePermissionLevel, EvidenceScopeKind
 *
 * [OUTPUT]
 * FiveDimEvidencePreFilterAuditView: Subview for physical 5-dimensional metadata
 * boundary audit before vector recall (Scope, Source Authority, Decay Half-life, Confidence, RBAC Permission).
 *
 * [POS]
 * Subcomponent for Item 99 (FiveDimPreFilteredEvidenceMemoryAndDeterministicRuleCascadeSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  ShieldAlert,
  ShieldCheck,
  Filter,
  CheckCircle2,
  XCircle,
  Sliders,
  RotateCw,
  Lock,
} from 'lucide-react';
import type {
  DeterministicRuleEntryDTO,
  EvidencePermissionLevel,
  EvidenceScopeKind,
  PreFilterEvidenceRequestDTO,
  PreFilteredEvidenceResponseDTO,
} from '@/services/memory/ruleCascade';

interface FiveDimEvidencePreFilterAuditViewProps {
  allRules: DeterministicRuleEntryDTO[];
  auditResult: PreFilteredEvidenceResponseDTO | null;
  onRunAudit: (request: PreFilterEvidenceRequestDTO) => Promise<void>;
  isLoading: boolean;
}

export function FiveDimEvidencePreFilterAuditView({
  allRules,
  auditResult,
  onRunAudit,
  isLoading,
}: FiveDimEvidencePreFilterAuditViewProps): React.JSX.Element {
  const [scopePrefix, setScopePrefix] = useState<string>('/workspace');
  const [minAuthority, setMinAuthority] = useState<number>(0.8);
  const [minConfidence, setMinConfidence] = useState<number>(0.5);
  const [permission, setPermission] = useState<EvidencePermissionLevel>('workspace_internal');
  const [maxAgeDays, setMaxAgeDays] = useState<number>(60);
  const [auditing, setAuditing] = useState<boolean>(false);

  const handleAuditSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setAuditing(true);
    try {
      await onRunAudit({
        candidates: allRules,
        scope_path_prefix: scopePrefix.trim() || undefined,
        min_authority: minAuthority,
        min_confidence: minConfidence,
        required_permission: permission,
        max_decay_age_days: maxAgeDays,
      });
    } finally {
      setAuditing(false);
    }
  };

  const rejectionStats = auditResult?.rejection_reasons ?? {};

  return (
    <div className="space-y-6">
      {/* 5D Boundary Configuration Form */}
      <div className="p-4 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Sliders className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              Physical 5-Dimensional Pre-Filter Guard
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            Enforced BEFORE retrieval to prevent context leakage
          </span>
        </div>

        <form onSubmit={handleAuditSubmit} aria-label="pre-filter-audit-form" className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label htmlFor="filter-scope-prefix" className="block text-xs font-medium text-muted-foreground mb-1">
                Dim 1: Scope Path Prefix
              </label>
              <input
                id="filter-scope-prefix"
                type="text"
                value={scopePrefix}
                onChange={(e) => setScopePrefix(e.target.value)}
                placeholder="/workspace"
                className="w-full text-xs font-mono px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={auditing || isLoading}
              />
            </div>

            <div>
              <label htmlFor="filter-min-authority" className="block text-xs font-medium text-muted-foreground mb-1">
                Dim 2: Min Source Authority ({minAuthority.toFixed(1)})
              </label>
              <select
                id="filter-min-authority"
                value={minAuthority}
                onChange={(e) => setMinAuthority(Number(e.target.value))}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={auditing || isLoading}
              >
                <option value={0.0}>0.0 (All: User + Tool + Inferred)</option>
                <option value={0.8}>0.8 (User Explicit + Tool Verified)</option>
                <option value={1.0}>1.0 (User Explicit Declaration Only)</option>
              </select>
            </div>

            <div>
              <label htmlFor="filter-permission" className="block text-xs font-medium text-muted-foreground mb-1">
                Dim 5: Max Role Permission
              </label>
              <select
                id="filter-permission"
                value={permission}
                onChange={(e) => setPermission(e.target.value as EvidencePermissionLevel)}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={auditing || isLoading}
              >
                <option value="public">Public Only (Zero Internal)</option>
                <option value="workspace_internal">Workspace Internal</option>
                <option value="confidential_admin">Confidential Admin (Unrestricted)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            <div>
              <label htmlFor="filter-min-confidence" className="block text-xs font-medium text-muted-foreground mb-1">
                Dim 4: Min Effective Confidence ({minConfidence.toFixed(2)})
              </label>
              <input
                id="filter-min-confidence"
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value))}
                className="w-full accent-primary"
                disabled={auditing || isLoading}
              />
            </div>

            <div>
              <label htmlFor="filter-max-age" className="block text-xs font-medium text-muted-foreground mb-1">
                Dim 3: Max Age Cutoff ({maxAgeDays} Days Half-life)
              </label>
              <input
                id="filter-max-age"
                type="number"
                min="1"
                max="365"
                value={maxAgeDays}
                onChange={(e) => setMaxAgeDays(Number(e.target.value))}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={auditing || isLoading}
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-2">
            <span className="text-[11px] text-muted-foreground flex items-center space-x-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>Zero-leakage physical SQL/Graph pre-filter prior to LLM visibility</span>
            </span>
            <Button
              type="submit"
              size="sm"
              disabled={auditing || isLoading}
              className="text-xs focus:ring-2 focus:ring-primary"
            >
              {auditing ? (
                <>
                  <RotateCw className="w-3 h-3 mr-1 animate-spin" />
                  Auditing Boundary...
                </>
              ) : (
                <>
                  <Filter className="w-3 h-3 mr-1" />
                  Execute Pre-Filter Audit
                </>
              )}
            </Button>
          </div>
        </form>
      </div>

      {/* Audit Telemetry & Rejection Reason Tiles */}
      {auditResult && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 rounded-lg border border-border bg-card/40 space-y-1">
              <span className="text-[11px] text-muted-foreground">Evaluated Total</span>
              <div className="text-lg font-bold text-foreground">{auditResult.total_evaluated}</div>
            </div>
            <div className="p-3 rounded-lg border border-border bg-card/40 space-y-1">
              <span className="text-[11px] text-emerald-600 font-medium">Passed Boundary</span>
              <div className="text-lg font-bold text-emerald-600">{auditResult.passed_count}</div>
            </div>
            <div className="p-3 rounded-lg border border-border bg-card/40 space-y-1">
              <span className="text-[11px] text-destructive font-medium">Blocked/Filtered</span>
              <div className="text-lg font-bold text-destructive">
                {auditResult.total_evaluated - auditResult.passed_count}
              </div>
            </div>
            <div className="p-3 rounded-lg border border-border bg-card/40 space-y-1">
              <span className="text-[11px] text-primary font-medium">Pass Ratio</span>
              <div className="text-lg font-bold text-primary">
                {auditResult.total_evaluated > 0
                  ? `${((auditResult.passed_count / auditResult.total_evaluated) * 100).toFixed(0)}%`
                  : '100%'}
              </div>
            </div>
          </div>

          {/* Rejection Breakdown */}
          {Object.keys(rejectionStats).length > 0 && (
            <div className="p-3.5 rounded-lg border border-destructive/30 bg-destructive/5 space-y-2">
              <div className="flex items-center space-x-1.5 text-destructive text-xs font-semibold">
                <ShieldAlert className="w-4 h-4" />
                <span>Pre-Filter Rejection Breakdown (Physical Isolation Gate)</span>
              </div>
              <div className="flex items-center gap-2 flex-wrap text-xs">
                {Object.entries(rejectionStats).map(([reason, count]) => (
                  <Badge key={reason} variant="outline" className="text-destructive border-destructive/40 text-[10px] font-mono">
                    {reason}: {count}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Passed Candidate Items */}
          <div className="space-y-2">
            <h5 className="text-xs font-semibold text-foreground flex items-center space-x-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              <span>Safe Candidate Memories Permitted for Prompt Context</span>
            </h5>
            <div className="space-y-2">
              {auditResult.passed_items.map((item) => (
                <div
                  key={item.rule_id}
                  className="p-2.5 rounded-md border border-border bg-background text-xs flex items-center justify-between"
                >
                  <div className="space-y-0.5">
                    <span className="font-semibold text-foreground">{item.title}</span>
                    <p className="text-[11px] text-muted-foreground font-mono">{item.rule_content}</p>
                  </div>
                  <div className="flex items-center space-x-1">
                    <Badge variant="outline" className="text-[9px] font-mono">
                      {item.metadata.scope}
                    </Badge>
                    <Badge variant="default" className="text-[9px] bg-emerald-600">
                      Safe
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
