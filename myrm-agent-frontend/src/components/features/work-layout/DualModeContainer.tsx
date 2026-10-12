'use client';

/**
 * [INPUT]
 * - useWorkLayoutStore from @/store/useWorkLayoutStore
 * - ModeSwitchBar, TurboProTierSelector, WorkAssetSidebar from ./
 * - useTranslations from next-intl (namespace: 'workLayout')
 *
 * [OUTPUT]
 * - DualModeContainer: Responsive wrapper switching between Chat Mode and Work Mode
 *
 * [POS]
 * Dual-Mode Chat/Work Layout main container wrapper (Item 26).
 * Single file < 220 lines. Zero `any` types. Zero native emoji.
 */

import React, { type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { LayoutDashboard, MessageSquare } from 'lucide-react';
import { useWorkLayoutStore } from '@/store/useWorkLayoutStore';
import { ModeSwitchBar } from './ModeSwitchBar';
import { TurboProTierSelector } from './TurboProTierSelector';
import { WorkAssetSidebar } from './WorkAssetSidebar';

interface DualModeContainerProps {
  children: ReactNode;
  headerSlot?: ReactNode;
  className?: string;
}

export function DualModeContainer({
  children,
  headerSlot,
  className = '',
}: DualModeContainerProps) {
  const t = useTranslations('workLayout');
  const viewMode = useWorkLayoutStore((s) => s.viewMode);
  const computeTier = useWorkLayoutStore((s) => s.computeTier);

  const isWork = viewMode === 'work';

  return (
    <div
      data-testid="dual-mode-container"
      data-mode={viewMode}
      data-tier={computeTier}
      className={`relative flex flex-col w-full h-full overflow-hidden bg-background ${className}`}
    >
      {/* Top Floating / Fixed Mode & Tier Bar */}
      <header
        role="banner"
        aria-label="Mode & Compute Tier Controller"
        className="w-full px-4 py-2 border-b border-border/50 bg-background/80 backdrop-blur-md flex items-center justify-between gap-3 z-20 shrink-0"
      >
        <div className="flex items-center gap-2.5 truncate">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground truncate">
            {isWork ? (
              <>
                <LayoutDashboard className="w-4 h-4 text-primary shrink-0" />
                <span className="truncate">{t('modeWork')}</span>
              </>
            ) : (
              <>
                <MessageSquare className="w-4 h-4 text-muted-foreground shrink-0" />
                <span className="truncate">{t('modeChat')}</span>
              </>
            )}
          </div>

          {headerSlot && <div className="truncate">{headerSlot}</div>}
        </div>

        {/* Right Controls: Mode Switch Slider + Turbo/Pro Tier Selector */}
        <div className="flex items-center gap-2 shrink-0">
          <TurboProTierSelector variant="compact" />
          <ModeSwitchBar size="sm" />
        </div>
      </header>

      {/* Main Workspace Surface */}
      <main className="flex-1 flex w-full h-[calc(100%-49px)] overflow-hidden">
        {/* Work Mode Assets Sidebar */}
        {isWork && <WorkAssetSidebar />}

        {/* Content Canvas (Chat Flow / Work Flow) */}
        <div
          className={`flex-1 flex flex-col h-full overflow-hidden transition-all duration-200 ${
            isWork ? 'bg-muted/10' : 'bg-background'
          }`}
        >
          {children}
        </div>
      </main>
    </div>
  );
}
