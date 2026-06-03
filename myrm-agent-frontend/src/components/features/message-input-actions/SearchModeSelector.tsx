'use client';

import { AiNetworkIcon, InvestigationIcon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useConfigStore from '@/store/useConfigStore';
import { guardSearchServiceConfigured } from '@/store/config/searchService';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import type { ActionMode } from '@/store/chat/types';

interface SearchModeSelectorProps {
  actionMode: ActionMode;
  setActionMode: (mode: ActionMode) => void;
}

const FastSearchIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={cn('shrink-0 transition-colors duration-300', className)}
  >
    <path d="M22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22" />
    <path d="M20 5.69899C19.0653 5.76636 17.8681 6.12824 17.0379 7.20277C15.5385 9.14361 14.039 9.30556 13.0394 8.65861C11.5399 7.6882 12.8 6.11636 11.0401 5.26215C9.89313 4.70542 9.73321 3.19045 10.3716 2" />
    <path d="M2 11C2.7625 11.6621 3.83046 12.2682 5.08874 12.2682C7.68843 12.2682 8.20837 12.7649 8.20837 14.7518C8.20837 16.7387 8.20837 16.7387 8.72831 18.2288C9.06651 19.1981 9.18472 20.1674 8.5106 21" />
    <path d="M19.8988 19.9288L22 22M21.1083 17.0459C21.1083 19.2805 19.2932 21.0919 17.0541 21.0919C14.8151 21.0919 13 19.2805 13 17.0459C13 14.8114 14.8151 13 17.0541 13C19.2932 13 21.1083 14.8114 21.1083 17.0459Z" />
  </svg>
);

type ModeEntry = {
  key: ActionMode;
  icon: (props: { className?: string }) => React.ReactNode;
  featureGate?: string;
  features?: string[];
};

const ConsensusIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={cn('shrink-0 transition-colors duration-300', className)}
  >
    <circle cx="12" cy="12" r="3" />
    <circle cx="5" cy="6" r="2" />
    <circle cx="19" cy="6" r="2" />
    <circle cx="5" cy="18" r="2" />
    <circle cx="19" cy="18" r="2" />
    <line x1="6.7" y1="7.5" x2="10" y2="10" />
    <line x1="17.3" y1="7.5" x2="14" y2="10" />
    <line x1="6.7" y1="16.5" x2="10" y2="14" />
    <line x1="17.3" y1="16.5" x2="14" y2="14" />
  </svg>
);

const MODES: ModeEntry[] = [
  { key: 'fast', icon: FastSearchIcon },
  {
    key: 'agent',
    icon: ({ className }) => (
      <AiNetworkIcon size={16} className={cn('shrink-0 transition-colors duration-300', className)} />
    ),
    features: ['agentFeature1', 'agentFeature2'],
  },
  {
    key: 'deep_research',
    icon: ({ className }) => (
      <InvestigationIcon size={16} className={cn('shrink-0 transition-colors duration-300', className)} />
    ),
    featureGate: 'deep_research',
    features: ['deep_researchFeature1', 'deep_researchFeature2'],
  },
  {
    key: 'consensus',
    icon: ConsensusIcon,
    featureGate: 'consensus',
    features: ['consensusFeature1', 'consensusFeature2'],
  },
];

const SEARCH_REQUIRED_MODES: ReadonlySet<ActionMode> = new Set(['fast', 'deep_research']);

const SearchModeSelector = ({ actionMode, setActionMode }: SearchModeSelectorProps) => {
  const t = useTranslations('mode');
  const { isEnabled, initialized } = useFeatureGateStore();

  const visibleModes = initialized ? MODES.filter((m) => !m.featureGate || isEnabled(m.featureGate)) : MODES;

  const handleModeChange = (mode: ActionMode) => {
    if (SEARCH_REQUIRED_MODES.has(mode) && mode !== actionMode) {
      const { searchServiceConfigs } = useConfigStore.getState();
      if (!guardSearchServiceConfigured(searchServiceConfigs)) return;
    }
    setActionMode(mode);
  };

  return (
    <TooltipProvider delayDuration={200}>
      <div role="radiogroup" className="group relative isolate flex h-fit focus:outline-none" tabIndex={0}>
        <div className="absolute inset-0 bg-black/[0.04] dark:bg-white/[0.06] rounded-[10px] transition-colors duration-300" />

        <div className="p-0.5 flex shrink-0 items-center">
          {visibleModes.map((mode) => {
            const isActive = actionMode === mode.key;
            const Icon = mode.icon;
            return (
              <Tooltip key={mode.key}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={isActive}
                    aria-label={t(`${mode.key}Title`)}
                    onClick={() => handleModeChange(mode.key)}
                    className="group/segmented-control relative focus:outline-none"
                  >
                    {isActive && (
                      <div className="pointer-events-none absolute inset-0 z-0 block bg-white dark:bg-black dark:bg-gradient-to-b dark:from-primary/20 dark:to-primary/20 border border-primary dark:border-primary/30 rounded-lg shadow-[0_1px_3px_0] shadow-primary/30 dark:shadow-primary/5 transition-all duration-300" />
                    )}
                    <div className="relative z-10 flex h-8 min-w-9 items-center justify-center px-2.5">
                      <Icon
                        className={cn(
                          isActive
                            ? 'text-primary'
                            : 'text-black/40 dark:text-white/40 group-hover/segmented-control:text-black dark:group-hover/segmented-control:text-white',
                        )}
                      />
                    </div>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-64 p-3">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Icon className="text-primary" />
                    <span className="font-semibold text-sm">{t(`${mode.key}Title`)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{t(`${mode.key}Description`)}</p>
                  {mode.features && (
                    <ul className="mt-2 space-y-1.5">
                      {mode.features.map((featureKey) => (
                        <li key={featureKey} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-primary shrink-0" />
                          <span>{t(featureKey)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
      </div>
    </TooltipProvider>
  );
};

export default SearchModeSelector;
