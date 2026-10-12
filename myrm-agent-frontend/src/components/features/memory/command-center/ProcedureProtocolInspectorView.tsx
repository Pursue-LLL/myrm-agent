'use client';

/**
 * [INPUT]
 * @/services/memory/procedureExperience::ProcedureMemoryEntryDTO, RegisterProcedureMemoryRequest
 * ./ProcedureMultiIntentSplitTool::ProcedureMultiIntentSplitTool
 * ./ProcedureRegisterForm::ProcedureRegisterForm
 *
 * [OUTPUT]
 * ProcedureProtocolInspectorView: Subview for inspecting 8-field procedure-shaped experience memories,
 * compact retrieval anchors, and hosting modular registration and split-over-merge tools.
 *
 * [POS]
 * Subcomponent for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  ShieldAlert,
  CheckCircle2,
  ListOrdered,
  PlusCircle,
  Scissors,
} from 'lucide-react';
import type {
  ProcedureMemoryEntryDTO,
  RegisterProcedureMemoryRequest,
} from '@/services/memory/procedureExperience';
import { ProcedureMultiIntentSplitTool } from './ProcedureMultiIntentSplitTool';
import { ProcedureRegisterForm } from './ProcedureRegisterForm';

interface ProcedureProtocolInspectorViewProps {
  entries: ProcedureMemoryEntryDTO[];
  onRegister: (req: RegisterProcedureMemoryRequest) => Promise<void>;
  onSplitIntents: (rawText: string) => Promise<Array<{ intent: string; body: string }>>;
  isLoading: boolean;
}

export function ProcedureProtocolInspectorView({
  entries,
  onRegister,
  onSplitIntents,
  isLoading,
}: ProcedureProtocolInspectorViewProps): React.JSX.Element {
  const [isAdding, setIsAdding] = useState<boolean>(false);
  const [showSplitTool, setShowSplitTool] = useState<boolean>(false);

  return (
    <div className="space-y-4">
      {/* Top action toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border-subtle bg-surface p-3">
        <div>
          <span className="font-semibold text-text-primary text-xs">
            八字段过程形态经验协议 (Procedure-Shaped 8-Field Protocol)
          </span>
          <p className="text-text-secondary text-[11px]">
            彻底终结流水账式轨迹，通过操作意图/不可变边界/步骤/反模式等八维度实现高泛化复用
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setShowSplitTool(!showSplitTool)}
            className="flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="多意图强制拆条工具"
          >
            <Scissors className="h-3.5 w-3.5" />
            <span>多意图拆条</span>
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => setIsAdding(!isAdding)}
            className="flex items-center gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="录入八字段过程经验"
          >
            <PlusCircle className="h-3.5 w-3.5" />
            <span>录入过程经验</span>
          </Button>
        </div>
      </div>

      {/* Modular Split-over-Merge Multi-Intent Tool */}
      <ProcedureMultiIntentSplitTool
        isOpen={showSplitTool}
        onClose={() => setShowSplitTool(false)}
        onSplitIntents={onSplitIntents}
      />

      {/* Modular Add 8-Field Procedure Form */}
      <ProcedureRegisterForm
        isOpen={isAdding}
        onClose={() => setIsAdding(false)}
        onSubmit={onRegister}
        isLoading={isLoading}
      />

      {/* List of 8-field procedure entries */}
      <div className="space-y-3">
        {entries.map((item) => (
          <div
            key={item.entry_id}
            className="rounded-xl border border-border-subtle bg-surface p-4 space-y-3 shadow-xs hover:border-border transition-colors"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="font-semibold text-text-primary text-xs">{item.name}</h4>
                  <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 border-emerald-200 text-[10px]">
                    八字段完整合规
                  </Badge>
                  <span className="font-mono text-text-tertiary text-[11px]">id: {item.entry_id}</span>
                </div>
                <p className="mt-1 text-text-secondary text-xs">{item.operation_intent}</p>
              </div>

              {/* Compact Retrieval Anchor Surface */}
              <div className="rounded bg-surface-subtle px-2 py-1 font-mono text-[10px] text-text-secondary border border-border-subtle max-w-md truncate">
                <span className="text-primary font-medium">锚点面: </span>
                {item.retrieval_anchor}
              </div>
            </div>

            {/* 8-field grid preview */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
              <div className="rounded-lg border border-border-subtle bg-surface-subtle/40 p-2.5 space-y-1">
                <span className="font-medium text-text-primary text-[11px] flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  前置条件 ({item.preconditions.length})
                </span>
                <ul className="list-disc list-inside text-text-secondary text-[11px] space-y-0.5">
                  {item.preconditions.map((p, idx) => (
                    <li key={idx} className="truncate">{p}</li>
                  ))}
                </ul>
              </div>

              <div className="rounded-lg border border-border-subtle bg-surface-subtle/40 p-2.5 space-y-1">
                <span className="font-medium text-text-primary text-[11px] flex items-center gap-1">
                  <ShieldAlert className="h-3 w-3 text-amber-600" />
                  不可变边界 ({item.immutable_boundary.length})
                </span>
                <ul className="list-disc list-inside text-text-secondary text-[11px] space-y-0.5">
                  {item.immutable_boundary.map((b, idx) => (
                    <li key={idx} className="truncate">{b}</li>
                  ))}
                </ul>
              </div>

              <div className="rounded-lg border border-border-subtle bg-surface-subtle/40 p-2.5 space-y-1">
                <span className="font-medium text-text-primary text-[11px] flex items-center gap-1">
                  <ListOrdered className="h-3 w-3 text-blue-600" />
                  执行步骤 ({item.procedure_steps.length})
                </span>
                <ul className="list-disc list-inside text-text-secondary text-[11px] space-y-0.5">
                  {item.procedure_steps.map((st, idx) => (
                    <li key={idx} className="truncate">{st}</li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Anti-patterns warning bar */}
            {item.anti_patterns.length > 0 && (
              <div className="rounded-lg border border-rose-300/40 bg-rose-500/5 px-3 py-1.5 text-[11px] text-rose-700 flex items-center gap-2">
                <span className="font-semibold">反模式警示:</span>
                <span>{item.anti_patterns.join(' · ')}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
