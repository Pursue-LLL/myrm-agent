'use client';

/**
 * [INPUT]
 * - ./useActiveComposerOptions::useActiveComposerOptions (POS: the sentence naming the modes that are on)
 * - @/components/primitives/tooltip (POS: hover hint)
 *
 * [OUTPUT]
 * - ComposerOptionsToggle: the "+" button that opens and closes the composer's options region.
 *
 * [POS]
 * Primary control of the desktop composer. A dot on the button and the sentence in its name and tooltip say that a
 * mode is on inside the closed region, so nothing that changes the next message stays out of sight.
 */

import { Plus } from '@phosphor-icons/react';
import { useTranslations } from 'next-intl';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';

import { useActiveComposerOptions } from './useActiveComposerOptions';

interface ComposerOptionsToggleProps {
  expanded: boolean;
  onToggle: () => void;
  /** Id of the options region this button controls. */
  controlsId: string;
}

export function ComposerOptionsToggle({ expanded, onToggle, controlsId }: ComposerOptionsToggleProps) {
  const t = useTranslations('chat.input');
  const activeModes = useActiveComposerOptions();

  const action = t(expanded ? 'collapseToolbar' : 'expandToolbar');
  const label = activeModes ? `${action} · ${activeModes}` : action;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid="composer-options-toggle"
            aria-expanded={expanded}
            aria-controls={controlsId}
            aria-label={label}
            onClick={onToggle}
            className={cn(
              'relative flex size-8 shrink-0 items-center justify-center rounded-full pointer-coarse:size-10',
              'text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              expanded ? 'bg-muted text-foreground' : 'bg-muted/50',
            )}
          >
            <Plus
              size={16}
              weight="bold"
              aria-hidden="true"
              className={cn('transition-transform duration-200 motion-reduce:transition-none', expanded && 'rotate-45')}
            />
            {activeModes ? (
              <span
                aria-hidden="true"
                data-testid="composer-options-active-dot"
                className="absolute right-0.5 top-0.5 size-2 rounded-full bg-primary ring-2 ring-secondary"
              />
            ) : null}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">
          <p>{label}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
