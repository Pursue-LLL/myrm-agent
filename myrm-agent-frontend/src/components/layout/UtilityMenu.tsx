'use client';

/**
 * [INPUT]
 * - Radix Popover/Tooltip primitives, next-intl namespaces
 * - useWorkbenchStore (POS: workbench visibility)
 * - Custom events consumed by the globally mounted panels
 *
 * [OUTPUT]
 * - UtilityMenu: one rail entry that opens the secondary tool panels
 *
 * [POS]
 * Replaces the five floating HUD capsules with a single, labelled menu in the nav rail.
 * The panels stay mounted elsewhere; this component only dispatches their open action.
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Activity, Brain, PanelRightOpen, Presentation, Wrench } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import { UTILITY_PANEL_EVENTS } from '@/lib/utilityPanelEvents';
import { cn } from '@/lib/utils/classnameUtils';

interface UtilityMenuItem {
  id: string;
  label: string;
  shortcut: string;
  icon: typeof Wrench;
  action: () => void;
}

const openPanel = (eventName: string) => {
  window.dispatchEvent(new CustomEvent(eventName));
};

export function UtilityMenu() {
  const t = useTranslations('nav');
  const tWorkbench = useTranslations('workbench');
  const tSessionMap = useTranslations('sessionMap');
  const tPresentation = useTranslations('presentation');
  const tToolPicker = useTranslations('toolPicker');
  const tAssistant = useTranslations('systemAssistant');
  const [open, setOpen] = useState(false);
  const toggleWorkbench = useWorkbenchStore((state) => state.toggleOpen);

  const run = (action: () => void) => {
    setOpen(false);
    action();
  };

  const items: UtilityMenuItem[] = [
    {
      id: 'workbench',
      icon: PanelRightOpen,
      label: tWorkbench('hudTrigger'),
      shortcut: tWorkbench('shortcutHint'),
      action: () => run(toggleWorkbench),
    },
    {
      id: 'session-map',
      icon: Activity,
      label: tSessionMap('hudTrigger'),
      shortcut: tSessionMap('shortcutHint'),
      action: () => run(() => openPanel(UTILITY_PANEL_EVENTS.sessionMap)),
    },
    {
      id: 'presentation',
      icon: Presentation,
      label: tPresentation('menuLabel'),
      shortcut: '⌥⌘P',
      action: () => run(() => openPanel(UTILITY_PANEL_EVENTS.presentation)),
    },
    {
      id: 'tool-picker',
      icon: Wrench,
      label: tToolPicker('menuLabel'),
      shortcut: '⌘⇧T',
      action: () => run(() => openPanel(UTILITY_PANEL_EVENTS.toolPicker)),
    },
    {
      id: 'assistant',
      icon: Brain,
      label: tAssistant('assistantName'),
      shortcut: tAssistant('shortcutHint'),
      action: () => run(() => openPanel(UTILITY_PANEL_EVENTS.assistant)),
    },
  ];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={t('tools')}
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200',
                open ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              <Wrench size={18} />
            </button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent side="right">{t('tools')}</TooltipContent>
      </Tooltip>
      <PopoverContent side="right" align="end" sideOffset={10} className="w-60 p-1.5">
        <p className="px-2 py-1.5 text-xs font-medium text-muted-foreground">{t('tools')}</p>
        {items.map(({ id, icon: Icon, label, shortcut, action }) => (
          <button
            key={id}
            type="button"
            onClick={action}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-foreground transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
          >
            <Icon size={16} className="shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate text-left">{label}</span>
            <kbd className="shrink-0 rounded border border-border/40 bg-background/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {shortcut}
            </kbd>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}
