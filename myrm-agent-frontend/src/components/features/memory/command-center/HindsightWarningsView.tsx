/**
 * [INPUT]
 * - @/services/memory/hindsight: PreExecutionWarningResponse
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - HindsightWarningsView: Sub-component rendering matched proactive pre-execution warnings.
 *
 * [POS]
 * Sub-component for HindsightReflectionCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import { AlertTriangle, ShieldAlert } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type { PreExecutionWarningResponse } from '@/services/memory/hindsight';

interface HindsightWarningsViewProps {
  warnings: PreExecutionWarningResponse[];
}

export function HindsightWarningsView({ warnings }: HindsightWarningsViewProps) {
  if (warnings.length === 0) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        未检测到高风险避坑警示，历史反思缓冲池评估安全
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-[11px] font-medium text-muted-foreground">
        前置避坑预警与纠偏建议 ({warnings.length})
      </div>
      <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
        {warnings.map((w) => (
          <div
            key={w.rule_id}
            className="rounded border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs transition"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                  <span className="font-mono text-[11px]">[{w.task_pattern}]</span>
                  <Badge variant="outline" className="border-amber-500/40 text-[10px] text-amber-600 dark:text-amber-300">
                    置信度: {(w.confidence * 100).toFixed(0)}%
                  </Badge>
                </div>
                <p className="mt-1 text-muted-foreground">
                  <strong>警示:</strong> {w.warning_text}
                </p>
                <div className="mt-1 flex items-start gap-1 rounded bg-accent/30 p-1.5 text-foreground">
                  <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
                  <span>
                    <strong>推荐纠偏:</strong> {w.recommended_action}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
