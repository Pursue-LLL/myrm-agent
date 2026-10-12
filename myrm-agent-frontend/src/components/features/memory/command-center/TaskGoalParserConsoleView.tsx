/**
 * [INPUT]
 * @/services/memory::ParsedTaskGoalDTO
 * lucide-react::(Crosshair, Tag, Key, Filter, CheckCircle2)
 *
 * [OUTPUT]
 * Component: TaskGoalParserConsoleView
 *
 * [POS]
 * Visual console rendering TaskGoalParser decomposition output.
 * Deconstructs query intent, entities, keywords, metadata filters, and confidence.
 * A11y compliant: Semantic sectioning, native output labels, zero div role="status".
 * Strict typing: Zero `any`. Single file < 200 lines.
 */

import React from 'react';
import { Crosshair, Tag, Key, Filter, CheckCircle2 } from 'lucide-react';
import type { ParsedTaskGoalDTO } from '@/services/memory';

interface TaskGoalParserConsoleViewProps {
  goal: ParsedTaskGoalDTO;
}

export const TaskGoalParserConsoleView: React.FC<TaskGoalParserConsoleViewProps> = ({ goal }) => {
  return (
    <section
      aria-label="前置目标意图解构详情"
      className="p-4 rounded-lg border border-border/80 bg-card/40 space-y-3.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded bg-primary/10 text-primary">
            <Crosshair className="w-3.5 h-3.5" aria-hidden="true" />
          </div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            TaskGoalParser 解构分析
          </h4>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-primary/15 text-primary border border-primary/20">
            <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
            意图: {goal.explicit_intent}
          </span>
          <span className="px-2 py-0.5 rounded text-xs font-mono bg-muted/70 text-foreground border border-border/60">
            置信度: {(goal.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      <div className="space-y-2 text-xs">
        <div>
          <span className="font-medium text-muted-foreground">原始查询: </span>
          <span className="font-mono text-foreground bg-muted/40 px-1.5 py-0.5 rounded">
            &ldquo;{goal.original_query}&rdquo;
          </span>
        </div>

        {goal.target_entities.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="flex items-center gap-1 font-medium text-muted-foreground">
              <Tag className="w-3 h-3" aria-hidden="true" /> 实体锚点:
            </span>
            {goal.target_entities.map((entity) => (
              <span
                key={entity}
                className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 font-mono text-[11px] border border-blue-500/20"
              >
                {entity}
              </span>
            ))}
          </div>
        )}

        {goal.extracted_keywords.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="flex items-center gap-1 font-medium text-muted-foreground">
              <Key className="w-3 h-3" aria-hidden="true" /> 词法分词:
            </span>
            {goal.extracted_keywords.map((kw) => (
              <span
                key={kw}
                className="px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground font-mono text-[11px]"
              >
                {kw}
              </span>
            ))}
          </div>
        )}

        {Object.keys(goal.metadata_filters).length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="flex items-center gap-1 font-medium text-muted-foreground">
              <Filter className="w-3 h-3" aria-hidden="true" /> 元数据约束:
            </span>
            {Object.entries(goal.metadata_filters).map(([k, v]) => (
              <span
                key={k}
                className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 font-mono text-[11px] border border-amber-500/20"
              >
                {k}={v}
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
