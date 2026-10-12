'use client';

/**
 * [INPUT]
 * @/services/memory/procedureExperience::ProcedureMemoryEntryDTO
 *
 * [OUTPUT]
 * ProcedureExperienceHudBar: 4-dimension HUD status bar for procedure-shaped memories,
 * fixed-count dual-node retrieval readiness, 8-field protocol conformance, and split-over-merge status.
 *
 * [POS]
 * Subcomponent for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. Single file < 120 lines.
 */

import React from 'react';
import {
  GitPullRequest,
  CheckCircle2,
  Sliders,
  Layers,
} from 'lucide-react';
import type { ProcedureMemoryEntryDTO } from '@/services/memory/procedureExperience';

interface ProcedureExperienceHudBarProps {
  entries: ProcedureMemoryEntryDTO[];
}

export function ProcedureExperienceHudBar({
  entries,
}: ProcedureExperienceHudBarProps): React.JSX.Element {
  const totalCount = entries.length;
  const highConfidenceCount = entries.filter((e) => e.confidence >= 0.9).length;

  return (
    <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
      {/* 1. 8-Field Procedure Count */}
      <div className="rounded-lg border border-border-subtle bg-surface-subtle/50 p-2.5 text-xs">
        <div className="flex items-center justify-between text-text-secondary">
          <span>八字段过程经验</span>
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
        </div>
        <div className="mt-1 font-semibold text-text-primary text-lg">
          {totalCount} <span className="text-text-tertiary text-xs font-normal">条结构化模板</span>
        </div>
      </div>

      {/* 2. Dual-Node Retrieval Call Sites */}
      <div className="rounded-lg border border-border-subtle bg-surface-subtle/50 p-2.5 text-xs">
        <div className="flex items-center justify-between text-text-secondary">
          <span>双节点精准拦截</span>
          <GitPullRequest className="h-3.5 w-3.5 text-primary" />
        </div>
        <div className="mt-1 font-semibold text-text-primary text-sm flex items-center gap-1.5 pt-0.5">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <span>首问 + 写前双拦截</span>
        </div>
      </div>

      {/* 3. Fixed-Count TopN Policy */}
      <div className="rounded-lg border border-border-subtle bg-surface-subtle/50 p-2.5 text-xs">
        <div className="flex items-center justify-between text-text-secondary">
          <span>固定条数注入</span>
          <Sliders className="h-3.5 w-3.5 text-text-tertiary" />
        </div>
        <div className="mt-1 font-mono text-text-primary text-xs pt-1 truncate">
          Top-2 首问 / Top-1 写前 (终结截断)
        </div>
      </div>

      {/* 4. Multi-Intent Split Policy */}
      <div className="rounded-lg border border-border-subtle bg-surface-subtle/50 p-2.5 text-xs">
        <div className="flex items-center justify-between text-text-secondary">
          <span>意图治理模式</span>
          <Layers className="h-3.5 w-3.5 text-text-tertiary" />
        </div>
        <div className="mt-1 font-mono text-text-primary text-xs pt-1 truncate">
          多意图强制拆条 (Split-over-Merge)
        </div>
      </div>
    </div>
  );
}
