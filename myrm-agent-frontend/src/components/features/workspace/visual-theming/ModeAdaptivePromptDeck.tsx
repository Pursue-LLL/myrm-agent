import React from 'react';
import { ArrowUpRight, Sparkles } from 'lucide-react';
import { getModeAdaptiveSuggestions } from './workspaceThemingEngine';
import { ModeAdaptiveSuggestion } from './workspaceThemingTypes';
import { useWorkspaceThemingStore } from './useWorkspaceThemingStore';

interface ModeAdaptivePromptDeckProps {
  onSelectSuggestion?: (prompt: string, suggestion: ModeAdaptiveSuggestion) => void;
  className?: string;
}

export const ModeAdaptivePromptDeck: React.FC<ModeAdaptivePromptDeckProps> = ({
  onSelectSuggestion,
  className = '',
}) => {
  const currentMode = useWorkspaceThemingStore((state) => state.currentMode);
  const suggestions = getModeAdaptiveSuggestions(currentMode);

  const handleClick = (item: ModeAdaptiveSuggestion) => {
    if (onSelectSuggestion) {
      onSelectSuggestion(item.prompt, item);
    }
  };

  return (
    <div
      data-testid="mode-adaptive-prompt-deck"
      className={`w-full select-none ${className}`}
    >
      <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
        <Sparkles className="h-3.5 w-3.5 text-primary" />
        <span>
          {currentMode === 'coding' ? '编程极客模式预设建议' : '通用办公模式预设建议'}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {suggestions.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              handleClick(item);
            }}
            className="group flex flex-col justify-between rounded-xl border border-border/60 bg-background/80 p-3 text-left transition-all hover:border-primary/40 hover:bg-muted/40 hover:shadow-xs"
          >
            <div>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                {item.category}
              </span>
              <h4 className="mt-1.5 text-xs font-medium text-foreground group-hover:text-primary transition-colors">
                {item.title}
              </h4>
            </div>

            <div className="mt-2.5 flex items-center justify-between border-t border-border/30 pt-1.5 text-[10px] text-muted-foreground">
              <span>一键装填</span>
              <ArrowUpRight className="h-3 w-3 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};
