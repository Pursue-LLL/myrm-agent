/**
 * [INPUT] targetNode, onApplyPatch, onClose, isPatching
 * [OUTPUT] DeliverableNodePatchBar component allowing targeted selective prompt patching on single nodes
 * [POS] artifacts/deliverable-inspector/DeliverableNodePatchBar.tsx
 */

'use client';

import React, { useState, useCallback } from 'react';
import { Sparkles, Send, X, RefreshCw, SlidersHorizontal } from 'lucide-react';
import type {
  DeliverableNode,
  SelectivePatchRequest,
  PatchMode,
} from './deliverableInspectorTypes';

export interface DeliverableNodePatchBarProps {
  targetNode: DeliverableNode | null;
  onApplyPatch: (request: SelectivePatchRequest) => void;
  onClose: () => void;
  isPatching?: boolean;
  className?: string;
}

const PRESET_PROMPTS = [
  '精简文案',
  '调整图表类型',
  '纠正数据指标',
  '突出核心结论',
  '优化视觉对比',
];

export const DeliverableNodePatchBar: React.FC<DeliverableNodePatchBarProps> = ({
  targetNode,
  onApplyPatch,
  onClose,
  isPatching = false,
  className = '',
}) => {
  const [prompt, setPrompt] = useState<string>('');
  const [patchMode, setPatchMode] = useState<PatchMode>('refine_content');

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!targetNode || !prompt.trim() || isPatching) {
        return;
      }
      onApplyPatch({
        nodeId: targetNode.id,
        targetedPrompt: prompt.trim(),
        patchMode,
      });
      setPrompt('');
    },
    [targetNode, prompt, isPatching, patchMode, onApplyPatch],
  );

  if (!targetNode) {
    return null;
  }

  return (
    <div
      data-testid="deliverable-node-patch-bar"
      className={`rounded-xl border border-primary/30 bg-card/95 text-card-foreground p-3 shadow-lg backdrop-blur-md transition-all ${className}`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-border/40 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-5 items-center gap-1 rounded bg-primary/10 px-1.5 font-mono text-[11px] font-semibold text-primary">
            <Sparkles className="h-3 w-3" />
            #{targetNode.index}
          </span>
          <span className="truncate font-medium text-foreground">
            局部针对性重做：{targetNode.title}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <div className="flex items-center gap-1 text-[11px] text-muted-foreground mr-1">
            <SlidersHorizontal className="h-3 w-3" />
            <select
              value={patchMode}
              onChange={(e) => {
                setPatchMode(e.target.value as PatchMode);
              }}
              disabled={isPatching}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-[11px] outline-none"
            >
              <option value="refine_content">内容微调</option>
              <option value="regenerate_node">单页重新生成</option>
              <option value="tweak_style">样式润色</option>
            </select>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isPatching}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="关闭局部微调栏"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Preset Badges */}
      <div className="flex flex-wrap items-center gap-1.5 pt-2">
        <span className="text-[10px] text-muted-foreground">快捷需求：</span>
        {PRESET_PROMPTS.map((preset) => {
          return (
            <button
              key={preset}
              type="button"
              disabled={isPatching}
              onClick={() => {
                setPrompt((prev) => {
                  return prev ? `${prev}，${preset}` : preset;
                });
              }}
              className="rounded-md border border-border/60 bg-muted/40 hover:bg-muted px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
            >
              {preset}
            </button>
          );
        })}
      </div>

      {/* Form Input */}
      <form onSubmit={handleSubmit} className="mt-2.5 flex items-center gap-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => {
            setPrompt(e.target.value);
          }}
          disabled={isPatching}
          placeholder="输入微调要求（如：将柱状图改为折线图，突出 8 月异常峰值）..."
          className="flex-1 rounded-lg border border-input bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
        />

        <button
          type="submit"
          disabled={!prompt.trim() || isPatching}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary hover:bg-primary/90 px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isPatching ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          <span>{isPatching ? '打补丁中...' : '定向重做'}</span>
        </button>
      </form>
    </div>
  );
};
