import React from 'react';
import { ArrowRight, Compass, Sparkles } from 'lucide-react';
import { SuggestionChipItem } from './presentationToolTypes';
import { usePresentationToolStore } from './usePresentationToolStore';

interface InteractiveSuggestionChipsProps {
  chips: SuggestionChipItem[];
  onChipSelected?: (chip: SuggestionChipItem) => void;
  className?: string;
}

export const InteractiveSuggestionChips: React.FC<
  InteractiveSuggestionChipsProps
> = ({ chips, onChipSelected, className = '' }) => {
  const clickSuggestionChip = usePresentationToolStore(
    (state) => state.clickSuggestionChip,
  );

  if (!chips || chips.length === 0) {
    return null;
  }

  const handleChipClick = (chip: SuggestionChipItem) => {
    clickSuggestionChip(chip);
    if (onChipSelected) {
      onChipSelected(chip);
    }
  };

  return (
    <div
      data-testid="interactive-suggestion-chips"
      className={`my-2 flex flex-wrap items-center gap-2 ${className}`}
    >
      <div className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground mr-1">
        <Sparkles className="h-3 w-3 text-primary animate-pulse" />
        <span>建议追问:</span>
      </div>

      {chips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          onClick={() => {
            handleChipClick(chip);
          }}
          className="group flex items-center gap-1.5 rounded-full border border-primary/20 bg-background/80 px-3 py-1 text-xs text-foreground/90 shadow-2xs backdrop-blur-sm transition-all hover:border-primary hover:bg-primary/10 hover:text-primary active:scale-95"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-muted font-mono text-[10px] text-muted-foreground group-hover:bg-primary group-hover:text-primary-foreground">
            {chip.position}
          </span>
          <span>{chip.label}</span>
          <ArrowRight className="h-3 w-3 text-muted-foreground opacity-60 transition-transform group-hover:translate-x-0.5 group-hover:opacity-100 group-hover:text-primary" />
        </button>
      ))}
    </div>
  );
};
