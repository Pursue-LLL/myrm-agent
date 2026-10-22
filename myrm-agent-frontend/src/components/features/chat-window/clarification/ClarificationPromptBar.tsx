import React from 'react';
import { HelpCircle, Sparkles, FastForward } from 'lucide-react';
import { useClarificationGateStore } from './useClarificationGateStore';

export interface ClarificationPromptBarProps {
  currentInput: string;
  onApplyPrompt?: (newPrompt: string) => void;
  className?: string;
}

export function ClarificationPromptBar({
  currentInput,
  onApplyPrompt,
  className = '',
}: ClarificationPromptBarProps) {
  const openGate = useClarificationGateStore((s) => s.openGate);
  const skipClarification = useClarificationGateStore((s) => s.skipClarification);

  const trimmed = currentInput.trim();
  if (!trimmed) {
    return null;
  }

  const isGrillMeCommand = trimmed.toLowerCase().startsWith('/grill-me');
  const isShortAndAmbitious = trimmed.length < 35 && trimmed.length > 2;

  if (!isGrillMeCommand && !isShortAndAmbitious) {
    return null;
  }

  function handleTriggerClarification() {
    openGate(currentInput, isGrillMeCommand ? 'command' : 'button');
  }

  function handleQuickSkip() {
    const spec = skipClarification();
    if (onApplyPrompt) {
      onApplyPrompt(spec.compiledPrompt);
    }
  }

  return (
    <section
      aria-label="苏格拉底式需求澄清建议栏"
      className={`flex items-center justify-between px-3 py-1.5 rounded-lg border border-primary/20 bg-primary/5 text-xs text-foreground animate-in fade-in-50 duration-200 select-none ${className}`}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1 mr-2">
        <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
        <span className="truncate text-[11px] text-muted-foreground">
          {isGrillMeCommand
            ? '已捕获 /grill-me 意图：开启苏格拉底式结构化提问以锁定无歧义规格'
            : '需求描述较简略：建议通过 30 秒选项澄清目标平台与产物，避免 AI 偏航'}
        </span>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          onClick={handleTriggerClarification}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-primary text-primary-foreground font-medium text-[11px] hover:bg-primary/90 transition-colors shadow-xs"
        >
          <HelpCircle className="h-3 w-3" />
          <span>理清思路规格</span>
        </button>

        <button
          type="button"
          aria-label="跳过提问采用默认假设"
          onClick={handleQuickSkip}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors text-[11px]"
          title="跳过提问，采用稳健模型假设"
        >
          <FastForward className="h-3 w-3" />
          <span className="hidden sm:inline">跳过直接做</span>
        </button>
      </div>
    </section>
  );
}
