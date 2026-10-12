'use client';

/**
 * [INPUT]
 * - useWorkspaceLayoutMode from '@/hooks/ui/useWorkspaceLayoutMode'
 * - LayoutModeChoiceModal from './LayoutModeChoiceModal'
 * - Translation strings from 'workspaceLayout' namespace
 * - Global keyboard shortcuts (Cmd+Shift+L / Ctrl+Shift+L)
 *
 * [OUTPUT]
 * - WorkspaceLayoutBar: Ambient floating layout bar and shortcut trigger for 4 preset workspace modes
 *
 * [POS]
 * HUD switchbar for Four Preset Workspace Layout Switcher.
 * Strict typing: Zero `any`. File length < 120 lines.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconCpu,
  IconSparkles,
  IconTerminal,
  IconUsers,
} from '@/components/features/icons/PremiumIcons';
import { useWorkspaceLayoutMode } from '@/hooks/ui/useWorkspaceLayoutMode';
import { LayoutModeChoiceModal } from './LayoutModeChoiceModal';

const MODE_ICON_MAP = {
  copilot: IconTerminal,
  multi_agent: IconUsers,
  remote_compute: IconCpu,
  easy_minimal: IconSparkles,
} as const;

// Layout mode values are snake_case while message keys are camelCase.
const MODE_SHORT_LABEL_KEY = {
  copilot: 'copilotShortLabel',
  multi_agent: 'multiAgentShortLabel',
  remote_compute: 'remoteComputeShortLabel',
  easy_minimal: 'easyMinimalShortLabel',
} as const;

export function WorkspaceLayoutBar() {
  const t = useTranslations('workspaceLayout');
  const { layoutMode } = useWorkspaceLayoutMode();
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);

  // Keyboard shortcut listener: Cmd+Shift+L / Ctrl+Shift+L
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'l') {
        e.preventDefault();
        setIsModalOpen((prev) => !prev);
      } else if (e.key === 'Escape' && isModalOpen) {
        setIsModalOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isModalOpen]);

  const handleClose = useCallback(() => {
    setIsModalOpen(false);
  }, []);

  const ActiveIcon = MODE_ICON_MAP[layoutMode] ?? IconSparkles;

  return (
    <>
      {/* Floating Layout Mode Bar (Top Center / Accessible HUD) */}
      <aside
        aria-label={t('barAriaLabel')}
        className="fixed top-3 right-20 z-[9970] hidden md:flex items-center select-none"
      >
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium shadow-md backdrop-blur-md bg-card/85 text-foreground border border-border/80 hover:bg-card hover:border-primary/50 ring-1 ring-border/20 hover:ring-primary/30 transition-all"
          title={t('barTooltip')}
        >
          <div className="w-4 h-4 rounded-full bg-primary/10 text-primary flex items-center justify-center">
            <ActiveIcon className="w-3 h-3" />
          </div>
          <span className="font-semibold text-[11px]">
            {t(MODE_SHORT_LABEL_KEY[layoutMode])}
          </span>
          <kbd className="hidden lg:inline-block px-1 py-0.2 text-[9px] font-mono rounded bg-background/60 border border-border/40 text-muted-foreground">
            {t('shortcutHint')}
          </kbd>
        </button>
      </aside>

      {/* Layout Choice Modal */}
      <LayoutModeChoiceModal isOpen={isModalOpen} onClose={handleClose} />
    </>
  );
}
