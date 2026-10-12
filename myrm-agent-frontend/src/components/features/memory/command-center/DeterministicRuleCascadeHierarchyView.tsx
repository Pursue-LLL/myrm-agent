'use client';

/**
 * [INPUT]
 * @/services/memory/ruleCascade::CascadedRuleSetDTO, DeterministicRuleEntryDTO
 *
 * [OUTPUT]
 * DeterministicRuleCascadeHierarchyView: Subview for visualizing deterministic top-down
 * directory rules cascade, leaf overrides, and authority rankings without probabilistic vector recall.
 *
 * [POS]
 * Subcomponent for Item 99 (FiveDimPreFilteredEvidenceMemoryAndDeterministicRuleCascadeSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  FolderTree,
  ShieldCheck,
  UserCheck,
  Wrench,
  Bot,
  Search,
  CheckCircle2,
  Lock,
  CornerDownRight,
  RotateCw,
} from 'lucide-react';
import type {
  CascadedRuleSetDTO,
  DeterministicRuleEntryDTO,
} from '@/services/memory/ruleCascade';

interface DeterministicRuleCascadeHierarchyViewProps {
  currentPath: string;
  cascadedSet: CascadedRuleSetDTO | null;
  onQueryPath: (path: string) => Promise<void>;
  isLoading: boolean;
}

export function DeterministicRuleCascadeHierarchyView({
  currentPath,
  cascadedSet,
  onQueryPath,
  isLoading,
}: DeterministicRuleCascadeHierarchyViewProps): React.JSX.Element {
  const [inputPath, setInputPath] = useState<string>(currentPath);

  const handleSearch = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (inputPath.trim()) {
      await onQueryPath(inputPath.trim());
    }
  };

  const getSourceBadge = (source: string, authority: number) => {
    if (source === 'user_explicit') {
      return (
        <Badge variant="default" className="text-[10px] font-mono uppercase bg-blue-600">
          <UserCheck className="w-3 h-3 mr-1 inline" /> User Declared ({authority.toFixed(1)})
        </Badge>
      );
    }
    if (source === 'tool_verified') {
      return (
        <Badge variant="outline" className="text-[10px] font-mono uppercase text-emerald-600 border-emerald-500/40">
          <Wrench className="w-3 h-3 mr-1 inline" /> Tool Verified ({authority.toFixed(1)})
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="text-[10px] font-mono uppercase text-muted-foreground border-border">
        <Bot className="w-3 h-3 mr-1 inline" /> Inferred ({authority.toFixed(1)})
      </Badge>
    );
  };

  const getPermissionBadge = (perm: string) => {
    switch (perm) {
      case 'confidential_admin':
        return (
          <Badge variant="outline" className="text-[10px] text-destructive border-destructive/40 font-mono">
            <Lock className="w-2.5 h-2.5 mr-0.5 inline" /> Confidential
          </Badge>
        );
      case 'workspace_internal':
        return (
          <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-500/40 font-mono">
            Internal
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="text-[10px] text-muted-foreground border-border font-mono">
            Public
          </Badge>
        );
    }
  };

  const rules: DeterministicRuleEntryDTO[] = cascadedSet?.inherited_rules ?? [];

  return (
    <div className="space-y-6">
      {/* Path Search Form */}
      <div className="p-4 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <FolderTree className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              Deterministic Rule Directory Penetration
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            Claude Code 100% Deterministic Tree Cascade
          </span>
        </div>

        <form onSubmit={handleSearch} aria-label="query-path-form" className="flex items-center gap-2">
          <div className="relative flex-1">
            <label htmlFor="target-path-input" className="sr-only">
              Target Path
            </label>
            <input
              id="target-path-input"
              type="text"
              value={inputPath}
              onChange={(e) => setInputPath(e.target.value)}
              placeholder="/workspace/packages/billing/controllers"
              className="w-full text-xs font-mono px-3 py-2 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={isLoading}
            />
          </div>
          <Button
            type="submit"
            size="sm"
            disabled={isLoading || !inputPath.trim()}
            className="text-xs shrink-0 focus:ring-2 focus:ring-primary"
          >
            {isLoading ? (
              <>
                <RotateCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                Cascading...
              </>
            ) : (
              <>
                <Search className="w-3.5 h-3.5 mr-1" />
                Resolve Cascade
              </>
            )}
          </Button>
        </form>
      </div>

      {/* Hierarchy Path Tree Breakdown */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-foreground flex items-center space-x-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            <span>
              Inherited Rules for <code className="font-mono text-xs">{cascadedSet?.target_path ?? currentPath}</code>
            </span>
          </h4>
          <span className="text-xs text-muted-foreground">
            Effective Rules: {cascadedSet?.effective_rules_count ?? rules.length}
          </span>
        </div>

        {rules.length === 0 ? (
          <div className="p-8 text-center rounded-lg border border-dashed border-border text-muted-foreground text-xs">
            No deterministic rules registered along ancestor path hierarchy.
          </div>
        ) : (
          <div className="space-y-3">
            {rules.map((rule) => (
              <div
                key={rule.rule_id}
                className="p-3.5 rounded-lg border border-border bg-card/40 space-y-2 hover:border-primary/40 transition-colors"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <CornerDownRight className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span className="text-xs font-semibold text-foreground">
                      {rule.title}
                    </span>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {rule.metadata.scope}
                    </Badge>
                  </div>
                  <div className="flex items-center space-x-1.5 flex-wrap">
                    {getSourceBadge(rule.metadata.source, rule.metadata.source_authority)}
                    {getPermissionBadge(rule.metadata.permission)}
                  </div>
                </div>

                <div className="p-2.5 rounded bg-muted/40 border border-border/50 text-xs text-foreground font-mono leading-relaxed">
                  {rule.rule_content}
                </div>

                <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-0.5">
                  <span className="font-mono text-[10px]">
                    Scope Path: <span className="text-foreground">{rule.metadata.scope_path}</span>
                  </span>
                  <span className="flex items-center space-x-1 text-emerald-600 font-medium text-[10px]">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Deterministic 100% Enforced</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
