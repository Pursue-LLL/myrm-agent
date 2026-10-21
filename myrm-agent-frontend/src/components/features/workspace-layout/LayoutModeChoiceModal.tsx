'use client';

/**
 * [INPUT]
 * - useWorkspaceLayoutMode, PresetLayoutMode from '@/hooks/ui/useWorkspaceLayoutMode'
 * - Translation strings from 'workspaceLayout' namespace
 *
 * [OUTPUT]
 * - LayoutModeChoiceModal: Semantic dialog for switching among 4 preset workspace layouts
 *
 * [POS]
 * Modal selector for Four Preset Workspace Layout Switcher.
 * Strict typing: Zero `any`. File length < 250 lines. Accessible <dialog> structure.
 */

import { useId, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconCheck,
  IconCpu,
  IconSparkles,
  IconTerminal,
  IconUsers,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import {
  useWorkspaceLayoutMode,
  type PresetLayoutMode,
} from '@/hooks/ui/useWorkspaceLayoutMode';

export interface LayoutModeChoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface LayoutModeOption {
  key: PresetLayoutMode;
  icon: React.ComponentType<{ className?: string }>;
  titleKey: string;
  descKey: string;
  badgeKey: string;
}

const LAYOUT_OPTIONS: LayoutModeOption[] = [
  {
    key: 'copilot',
    icon: IconTerminal,
    titleKey: 'copilotTitle',
    descKey: 'copilotDesc',
    badgeKey: 'copilotBadge',
  },
  {
    key: 'multi_agent',
    icon: IconUsers,
    titleKey: 'multiAgentTitle',
    descKey: 'multiAgentDesc',
    badgeKey: 'multiAgentBadge',
  },
  {
    key: 'remote_compute',
    icon: IconCpu,
    titleKey: 'remoteComputeTitle',
    descKey: 'remoteComputeDesc',
    badgeKey: 'remoteComputeBadge',
  },
  {
    key: 'easy_minimal',
    icon: IconSparkles,
    titleKey: 'easyMinimalTitle',
    descKey: 'easyMinimalDesc',
    badgeKey: 'easyMinimalBadge',
  },
];

export function LayoutModeChoiceModal({
  isOpen,
  onClose,
}: LayoutModeChoiceModalProps) {
  const t = useTranslations('workspaceLayout');
  const titleId = useId();
  const descId = useId();

  const { layoutMode, setLayoutMode } = useWorkspaceLayoutMode();

  const handleSelect = useCallback(
    (mode: PresetLayoutMode) => {
      setLayoutMode(mode);
    },
    [setLayoutMode],
  );

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <dialog
        open
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-2xl rounded-2xl bg-card border border-border shadow-2xl p-6 text-foreground flex flex-col gap-5 m-0 max-h-[90vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div>
            <h2 id={titleId} className="text-base font-semibold">
              {t('modalTitle')}
            </h2>
            <p id={descId} className="text-xs text-muted-foreground mt-0.5">
              {t('modalSubtitle')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label={t('closeAriaLabel')}
          >
            <IconX className="w-5 h-5" />
          </button>
        </div>

        {/* 4 Mode Grid Selection Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          {LAYOUT_OPTIONS.map((option) => {
            const IconComponent = option.icon;
            const isSelected = layoutMode === option.key;

            return (
              <button
                key={option.key}
                type="button"
                onClick={() => handleSelect(option.key)}
                className={`relative flex flex-col text-left p-4 rounded-xl border transition-all ${
                  isSelected
                    ? 'bg-primary/10 border-primary ring-2 ring-primary/40 text-foreground'
                    : 'bg-muted/30 border-border/70 hover:bg-muted/60 hover:border-border text-foreground'
                }`}
              >
                {/* Active check badge */}
                {isSelected && (
                  <div className="absolute top-3 right-3 w-5 h-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-sm">
                    <IconCheck className="w-3.5 h-3.5" />
                  </div>
                )}

                <div className="flex items-center gap-2.5 mb-2">
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                      isSelected
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-background text-primary border border-border/60'
                    }`}
                  >
                    <IconComponent className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold">{t(option.titleKey)}</h3>
                    <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-background/80 text-muted-foreground border border-border/40">
                      {t(option.badgeKey)}
                    </span>
                  </div>
                </div>

                <p className="text-[11px] text-muted-foreground leading-relaxed mt-1">
                  {t(option.descKey)}
                </p>
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-3 border-t border-border/60">
          <span className="text-xs text-muted-foreground">
            {t('activeLayoutPrefix')}:{' '}
            <strong className="text-foreground font-semibold">
              {t(`${layoutMode}Title` as `copilotTitle`)}
            </strong>
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
          >
            {t('doneAction')}
          </button>
        </div>
      </dialog>
    </div>
  );
}
