/**
 * [OUTPUT]
 * - COLLAPSED_OPTIONS_LIMIT: option count shown before the rest fold behind the expand toggle
 * - OptionPill: one selectable option with recommended badge and inline-code description
 * - ExpandToggle: the fold/unfold control under a long option list
 *
 * [POS]
 * Option-list presentation primitives of ClarificationInput; no state and no submission logic.
 */

import React from 'react';
import { cn } from '@/lib/utils';

export const COLLAPSED_OPTIONS_LIMIT = 4;

const CheckMarkIcon = () => (
  <svg
    width="10"
    height="10"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="3"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const ChevronDownIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="m6 9 6 6 6-6" />
  </svg>
);

const RECOMMENDED_REGEX =
  /(?:\s*[(（](?:Recommended|推荐|建議|おすすめ|추천|Empfohlen)[)）]|\s*\[(?:Recommended|推荐|建議|おすすめ|추천|Empfohlen)\])$/i;

function parseOptionLabel(rawLabel: string): { displayLabel: string; isRecommended: boolean } {
  const match = rawLabel.match(RECOMMENDED_REGEX);
  if (match) {
    const cleaned = rawLabel.replace(RECOMMENDED_REGEX, '').trim();
    return {
      displayLabel: cleaned || rawLabel.trim(),
      isRecommended: true,
    };
  }
  return {
    displayLabel: rawLabel,
    isRecommended: false,
  };
}

function renderDescriptionWithCode(text: string): React.ReactNode {
  if (!text.includes('`')) {
    return text;
  }
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={index}
          className="mx-0.5 rounded border border-border/60 bg-muted/70 px-1 py-0.5 font-mono text-[11px] font-medium text-foreground"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

interface OptionPillProps {
  label: string;
  description?: string;
  selected: boolean;
  allowMultiple: boolean;
  disabled: boolean;
  onSelect: () => void;
  recommendedBadgeText?: string;
}

export const OptionPill = ({
  label,
  description,
  selected,
  allowMultiple,
  disabled,
  onSelect,
  recommendedBadgeText,
}: OptionPillProps) => {
  const { displayLabel, isRecommended } = parseOptionLabel(label);

  return (
    // oxlint-disable-next-line jsx-a11y/control-has-associated-label -- name comes from nested text beyond the rule's inspection depth
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      className={cn(
        'group max-w-full rounded-2xl border px-3 py-2 text-left text-sm transition-all duration-200 sm:px-4 sm:py-2.5',
        selected
          ? 'border-primary/70 bg-primary/10 text-primary ring-2 ring-primary/20'
          : 'border-border/70 bg-background/80 text-foreground hover:border-primary/40 hover:bg-primary/5',
      )}
    >
      <div className="flex items-start gap-2.5">
        <div
          className={cn(
            'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center border transition-colors',
            allowMultiple ? 'rounded' : 'rounded-full',
            selected ? 'border-primary bg-primary text-primary-foreground' : 'border-input bg-background',
          )}
        >
          {selected ? <CheckMarkIcon /> : null}
        </div>
        <div className="min-w-0 flex flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={cn('font-medium leading-snug', selected && 'text-primary')}>{displayLabel}</span>
            {isRecommended ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-primary shadow-sm shadow-primary/10">
                <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                {recommendedBadgeText || 'Recommended'}
              </span>
            ) : null}
          </div>
          {description ? (
            <span className="text-xs leading-relaxed text-muted-foreground">
              {renderDescriptionWithCode(description)}
            </span>
          ) : null}
        </div>
      </div>
    </button>
  );
};

interface ExpandToggleProps {
  expanded: boolean;
  label: string;
  onToggle: () => void;
}

export const ExpandToggle = ({ expanded, label, onToggle }: ExpandToggleProps) => (
  <button
    type="button"
    onClick={onToggle}
    className="inline-flex items-center gap-1.5 self-start rounded-full border border-dashed border-border/70 bg-background/50 px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent/40 hover:text-foreground"
  >
    <ChevronDownIcon className={cn('h-3.5 w-3.5 transition-transform duration-200', expanded && 'rotate-180')} />
    <span>{label}</span>
  </button>
);
