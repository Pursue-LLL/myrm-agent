'use client';

import React from 'react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import { Layers, Loader2, Play, Sparkles } from 'lucide-react';
import type { ContextProjectionResponseDTO } from '@/services/projects/projectState';

interface ProjectFactProjectionPanelProps {
  targetTask: string;
  setTargetTask: (task: string) => void;
  targetComponents: string;
  setTargetComponents: (components: string) => void;
  projecting: boolean;
  projectionResult: ContextProjectionResponseDTO | null;
  onRunProjection: () => Promise<void>;
}

export function ProjectFactProjectionPanel({
  targetTask,
  setTargetTask,
  targetComponents,
  setTargetComponents,
  projecting,
  projectionResult,
  onRunProjection,
}: ProjectFactProjectionPanelProps): React.JSX.Element {
  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-md border border-border/80 p-3 bg-muted/10">
        <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <Layers className="h-3.5 w-3.5 text-primary" />
          <span>四层级联动态上下文投影器 (4-Tier Context Projector)</span>
        </div>
        <div className="space-y-1">
          <label htmlFor="target-task-input" className="text-[11px] text-muted-foreground font-medium">
            子任务目标 (Target Task):
          </label>
          <Input
            id="target-task-input"
            value={targetTask}
            onChange={(e) => setTargetTask(e.target.value)}
            className="h-7 text-xs"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="target-comps-input" className="text-[11px] text-muted-foreground font-medium">
            涉及组件标识 (逗号分隔):
          </label>
          <Input
            id="target-comps-input"
            value={targetComponents}
            onChange={(e) => setTargetComponents(e.target.value)}
            className="h-7 text-xs"
          />
        </div>
        <Button
          type="button"
          size="sm"
          className="h-7 text-xs w-full"
          disabled={projecting}
          onClick={onRunProjection}
        >
          {projecting ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Play className="h-3.5 w-3.5 mr-1" />}
          执行四层级联投影装配
        </Button>
      </div>

      {projectionResult ? (
        <div className="rounded-md border border-primary/40 bg-card p-3 space-y-2 text-xs">
          <div className="flex items-center justify-between border-b pb-1.5">
            <div className="font-semibold text-foreground flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              <span>
                投影装配成果 (Token 预估: {projectionResult.token_count_estimated} / {projectionResult.token_budget})
              </span>
            </div>
            <Badge variant="secondary" className="text-[10px]">
              节约 Token: {Math.max(0, projectionResult.token_budget - projectionResult.token_count_estimated)}
            </Badge>
          </div>
          <div className="grid grid-cols-3 gap-2 text-[11px]">
            <div className="rounded border p-1.5 bg-background">
              <span className="font-medium text-foreground">Rule Layer:</span> {projectionResult.rule_layer_facts.length} 项
            </div>
            <div className="rounded border p-1.5 bg-background">
              <span className="font-medium text-foreground">Dependency Layer:</span> {projectionResult.dependency_layer_facts.length} 项
            </div>
            <div className="rounded border p-1.5 bg-background">
              <span className="font-medium text-foreground">Semantic Layer:</span> {projectionResult.semantic_layer_facts.length} 项
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-[11px] font-medium text-muted-foreground">注入 Prompt 预览:</div>
            <pre className="rounded bg-muted p-2 font-mono text-[10px] overflow-x-auto whitespace-pre-wrap max-h-32">
              {projectionResult.projected_context_prompt}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}
